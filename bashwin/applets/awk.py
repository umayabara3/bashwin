# -*- coding: utf-8 -*-
"""awk(POSIX awk の主要部分 + gawk のよく使う関数)。

対応: BEGIN/END、パターン(式・正規表現・範囲)、フィールド、連想配列、
if/while/do/for/for-in、関数定義、print/printf とリダイレクト(> >> |)、getline、
組み込み関数 length substr index split sub gsub match sprintf tolower toupper int
sqrt exp log sin cos atan2 rand srand system close fflush systime strftime。
未対応: gensub, 多文字/正規表現の RS, @include, 拡張機能全般。
"""
from __future__ import unicode_literals

import math
import os
import random
import re
import time

from .. import pattern, timefmt
from .common import applet

_KEYWORDS = frozenset(('BEGIN', 'END', 'function', 'func', 'if', 'else', 'while', 'for', 'do',
                       'break', 'continue', 'next', 'exit', 'return', 'delete', 'in', 'getline',
                       'print', 'printf'))
_BUILTINS = frozenset(('length', 'substr', 'index', 'split', 'sub', 'gsub', 'match', 'sprintf',
                       'tolower', 'toupper', 'int', 'sqrt', 'exp', 'log', 'sin', 'cos', 'atan2',
                       'rand', 'srand', 'system', 'close', 'fflush', 'systime', 'strftime'))
_OPS = ('**=', '+=', '-=', '*=', '/=', '%=', '^=', '==', '!=', '<=', '>=', '&&', '||', '++',
        '--', '>>', '!~', '**', '+', '-', '*', '/', '%', '^', '!', '<', '>', '=', '~', '?',
        ':', ',', ';', '(', ')', '[', ']', '{', '}', '$', '|')
_NUM_RE = re.compile(r'(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?')
_NUMSTR_RE = re.compile(r'\s*[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?\s*$')
_NUMPFX_RE = re.compile(r'\s*[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?')
_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_STR_ESC = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', '/': '/', 'a': '\a',
            'b': '\b', 'f': '\f', 'v': '\v'}
_FMT_RE = re.compile(r'%([-+ #0]*)(\*|[0-9]+)?(?:\.(\*|[0-9]*))?([a-zA-Z%])')


class AwkError(Exception):
    pass


class _Next(Exception):
    pass


class _Exit(Exception):
    def __init__(self, code):
        Exception.__init__(self)
        self.code = code


class _Return(Exception):
    def __init__(self, value):
        Exception.__init__(self)
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class StrNum(str):
    """入力由来の文字列。数値に見えれば数値として比較される。"""
    __slots__ = ()


class _Uninit(StrNum):
    __slots__ = ()


UNINIT = _Uninit('')


def unescape(s):
    if '\\' not in s:
        return s
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n:
            d = s[i + 1]
            if d in _STR_ESC:
                out.append(_STR_ESC[d])
                i += 2
                continue
            m = re.compile(r'[0-7]{1,3}').match(s, i + 1)
            if m:
                out.append(chr(int(m.group(), 8)))
                i = m.end()
                continue
            out.append('\\' + d)
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


# ---------------------------------------------------------------- lexer
def tokenize(src):
    toks = []
    i = 0
    n = len(src)
    prev = None

    def operand_end():
        if prev is None:
            return False
        k, v = prev[0], prev[1]
        return k in ('num', 'str', 'ere', 'name', 'builtin') or (k == 'op' and v in (')', ']', '++', '--'))

    while i < n:
        c = src[i]
        if c in ' \t\r':
            i += 1
            continue
        if c == '\\' and src.startswith('\\\n', i):
            i += 2
            continue
        if c == '#':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '\n':
            prev = ('nl', None)
            toks.append(prev)
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and src[j] != '"':
                if src[j] == '\\' and j + 1 < n:
                    buf.append(src[j:j + 2])
                    j += 2
                else:
                    buf.append(src[j])
                    j += 1
            if j >= n:
                raise AwkError('unterminated string')
            prev = ('str', unescape(''.join(buf)))
            toks.append(prev)
            i = j + 1
            continue
        if c == '/' and not operand_end():
            j = i + 1
            buf = []
            in_br = False
            while j < n:
                ch = src[j]
                if ch == '\\' and j + 1 < n:
                    buf.append('/' if src[j + 1] == '/' else src[j:j + 2])
                    j += 2
                    continue
                if ch == '[':
                    in_br = True
                elif ch == ']':
                    in_br = False
                elif ch == '/' and not in_br:
                    break
                elif ch == '\n':
                    raise AwkError('unterminated regexp')
                buf.append(ch)
                j += 1
            if j >= n:
                raise AwkError('unterminated regexp')
            prev = ('ere', ''.join(buf))
            toks.append(prev)
            i = j + 1
            continue
        m = _NUM_RE.match(src, i)
        if m and (c.isdigit() or c == '.'):
            prev = ('num', float(m.group()))
            toks.append(prev)
            i = m.end()
            continue
        m = _NAME_RE.match(src, i)
        if m:
            name = m.group()
            i = m.end()
            if name in _KEYWORDS:
                prev = ('kw', 'function' if name == 'func' else name)
            elif name in _BUILTINS:
                prev = ('builtin', name)
            elif i < n and src[i] == '(':
                prev = ('func', name)
            else:
                prev = ('name', name)
            toks.append(prev)
            continue
        for op in _OPS:
            if src.startswith(op, i):
                prev = ('op', '^' if op == '**' else ('^=' if op == '**=' else op))
                toks.append(prev)
                i += len(op)
                break
        else:
            raise AwkError("syntax error: unexpected character '%s'" % c)
    toks.append(('eof', None))
    return toks


# ---------------------------------------------------------------- parser
class Parser(object):
    def __init__(self, src):
        self.t = tokenize(src)
        self.i = 0
        self.funcs = {}

    def peek(self):
        return self.t[self.i]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def is_op(self, v):
        tok = self.t[self.i]
        return tok[0] == 'op' and tok[1] == v

    def is_kw(self, v):
        tok = self.t[self.i]
        return tok[0] == 'kw' and tok[1] == v

    def accept(self, v):
        if self.is_op(v):
            self.i += 1
            return True
        return False

    def expect(self, v):
        if not self.accept(v):
            tok = self.peek()
            raise AwkError("syntax error: expected '%s' near '%s'" % (v, tok[1] if tok[1] is not None
                                                                    else tok[0]))

    def skip_nl(self):
        while self.t[self.i][0] == 'nl':
            self.i += 1

    def skip_term(self):
        while self.t[self.i][0] == 'nl' or self.is_op(';'):
            self.i += 1

    def program(self):
        begin, main, end = [], [], []
        self.skip_term()
        while self.peek()[0] != 'eof':
            if self.is_kw('BEGIN'):
                self.i += 1
                self.skip_nl()
                begin.append(self.block())
            elif self.is_kw('END'):
                self.i += 1
                self.skip_nl()
                end.append(self.block())
            elif self.is_kw('function'):
                self.i += 1
                name = self.next()
                if name[0] not in ('name', 'func'):
                    raise AwkError('syntax error: function name expected')
                self.expect('(')
                params = []
                while not self.is_op(')'):
                    p = self.next()
                    if p[0] != 'name':
                        raise AwkError('syntax error in function parameters')
                    params.append(p[1])
                    self.accept(',')
                    self.skip_nl()
                self.expect(')')
                self.skip_nl()
                self.funcs[name[1]] = (params, self.block())
            else:
                pat = None
                pat2 = None
                if not self.is_op('{'):
                    pat = self.expr()
                    if self.accept(','):
                        self.skip_nl()
                        pat2 = self.expr()
                body = self.block() if self.is_op('{') else None
                main.append([pat, pat2, body, False])
            self.skip_term()
        return begin, main, end

    def block(self):
        self.expect('{')
        stmts = []
        self.skip_term()
        while not self.is_op('}'):
            if self.peek()[0] == 'eof':
                raise AwkError("syntax error: missing '}'")
            stmts.append(self.stmt())
            self.skip_term()
        self.expect('}')
        return ('block', stmts)

    def simple_or_block(self):
        self.skip_nl()
        if self.is_op('{'):
            return self.block()
        if self.accept(';'):
            return ('block', [])
        s = self.stmt()
        return s

    def end_simple(self):
        tok = self.peek()
        if tok[0] == 'nl' or self.is_op(';'):
            self.i += 1
        elif not (self.is_op('}') or tok[0] == 'eof'):
            raise AwkError("syntax error near '%s'" % (tok[1] if tok[1] is not None else tok[0]))

    def stmt(self):
        tok = self.peek()
        if tok[0] == 'op' and tok[1] == '{':
            return self.block()
        if tok[0] == 'kw':
            k = tok[1]
            if k == 'if':
                self.i += 1
                self.expect('(')
                c = self.expr()
                self.expect(')')
                a = self.simple_or_block()
                save = self.i
                self.skip_term()
                if self.is_kw('else'):
                    self.i += 1
                    return ('if', c, a, self.simple_or_block())
                self.i = save
                return ('if', c, a, None)
            if k == 'while':
                self.i += 1
                self.expect('(')
                c = self.expr()
                self.expect(')')
                if self.accept(';'):
                    return ('while', c, ('block', []))
                return ('while', c, self.simple_or_block())
            if k == 'do':
                self.i += 1
                body = self.simple_or_block()
                self.skip_term()
                if not self.is_kw('while'):
                    raise AwkError("syntax error: 'while' expected after 'do'")
                self.i += 1
                self.expect('(')
                c = self.expr()
                self.expect(')')
                self.end_simple()
                return ('do', body, c)
            if k == 'for':
                self.i += 1
                self.expect('(')
                # for (k in arr)
                if self.peek()[0] == 'name' and self.t[self.i + 1] == ('kw', 'in') \
                        and self.t[self.i + 2][0] == 'name' and self.t[self.i + 3] == ('op', ')'):
                    var = self.next()[1]
                    self.i += 1
                    arr = self.next()[1]
                    self.expect(')')
                    return ('forin', var, arr, self.simple_or_block())
                init = None if self.is_op(';') else self.simple()
                self.expect(';')
                self.skip_nl()
                cond = None if self.is_op(';') else self.expr()
                self.expect(';')
                self.skip_nl()
                incr = None if self.is_op(')') else self.simple()
                self.expect(')')
                if self.accept(';'):
                    return ('for', init, cond, incr, ('block', []))
                return ('for', init, cond, incr, self.simple_or_block())
            if k in ('break', 'continue', 'next'):
                self.i += 1
                self.end_simple()
                return (k,)
            if k in ('exit', 'return'):
                self.i += 1
                e = None
                tok2 = self.peek()
                if not (tok2[0] in ('nl', 'eof') or self.is_op(';') or self.is_op('}')):
                    e = self.expr()
                self.end_simple()
                return (k, e)
        s = self.simple()
        self.end_simple()
        return s

    def simple(self):
        tok = self.peek()
        if tok[0] == 'kw' and tok[1] == 'delete':
            self.i += 1
            name = self.next()
            if name[0] != 'name':
                raise AwkError('syntax error: array name expected after delete')
            subs = None
            if self.accept('['):
                subs = self.expr_list(']')
            return ('delete', name[1], subs)
        if tok[0] == 'kw' and tok[1] in ('print', 'printf'):
            self.i += 1
            args = []
            tok2 = self.peek()
            if not (tok2[0] in ('nl', 'eof') or (tok2[0] == 'op' and tok2[1] in (';', '}', '>', '>>', '|'))):
                args.append(self.expr(no_gt=True))
                while self.accept(','):
                    self.skip_nl()
                    args.append(self.expr(no_gt=True))
            if len(args) == 1 and args[0][0] == 'group':
                args = args[0][1]
            redir = None
            tok2 = self.peek()
            if tok2[0] == 'op' and tok2[1] in ('>', '>>', '|'):
                self.i += 1
                redir = (tok2[1], self.concat(True, True))
            return (tok[1], args, redir)
        return ('expr', self.expr())

    def expr_list(self, close):
        items = []
        self.skip_nl()
        while not self.is_op(close):
            items.append(self.expr())
            self.skip_nl()
            if not self.accept(','):
                break
            self.skip_nl()
        self.expect(close)
        return items

    # 式: 代入 > 三項 > || > && > in > ~ > 比較 > 連結 > 加減 > 乗除 > 単項 > ^ > 後置
    def expr(self, no_in=False, no_gt=False):
        left = self.ternary(no_in, no_gt)
        tok = self.peek()
        if tok[0] == 'op' and tok[1] in ('=', '+=', '-=', '*=', '/=', '%=', '^=') \
                and left[0] in ('var', 'idx', 'field'):
            self.i += 1
            self.skip_nl()
            return ('assign', tok[1], left, self.expr(no_in, no_gt))
        return left

    def ternary(self, no_in, no_gt):
        c = self.or_(no_in, no_gt)
        if self.accept('?'):
            self.skip_nl()
            a = self.expr(no_in, no_gt)
            self.skip_nl()
            self.expect(':')
            self.skip_nl()
            b = self.expr(no_in, no_gt)
            return ('?:', c, a, b)
        return c

    def or_(self, no_in, no_gt):
        left = self.and_(no_in, no_gt)
        while self.accept('||'):
            self.skip_nl()
            left = ('||', left, self.and_(no_in, no_gt))
        return left

    def and_(self, no_in, no_gt):
        left = self.in_(no_in, no_gt)
        while self.accept('&&'):
            self.skip_nl()
            left = ('&&', left, self.in_(no_in, no_gt))
        return left

    def in_(self, no_in, no_gt):
        left = self.match(no_in, no_gt)
        while not no_in and self.is_kw('in'):
            self.i += 1
            name = self.next()
            if name[0] != 'name':
                raise AwkError("syntax error: array name expected after 'in'")
            left = ('in', left[1] if left[0] == 'group' else [left], name[1])
        return left

    def match(self, no_in, no_gt):
        left = self.cmp(no_in, no_gt)
        while self.is_op('~') or self.is_op('!~'):
            neg = self.next()[1] == '!~'
            left = ('match', neg, left, self.cmp(no_in, no_gt))
        return left

    def cmp(self, no_in, no_gt):
        left = self.concat(no_in, no_gt)
        tok = self.peek()
        if tok[0] == 'op' and tok[1] in ('<', '<=', '==', '!=', '>', '>=') \
                and not (no_gt and tok[1] == '>'):
            self.i += 1
            return ('cmp', tok[1], left, self.concat(no_in, no_gt))
        return left

    def concat(self, no_in, no_gt):
        left = self.additive()
        while True:
            tok = self.peek()
            if tok[0] in ('num', 'str', 'ere', 'name', 'func', 'builtin') or \
                    (tok[0] == 'op' and tok[1] in ('$', '!', '(', '-', '+', '++', '--')) :
                if tok[0] == 'op' and tok[1] in ('-', '+'):
                    break
                left = ('cat', left, self.additive())
            elif tok == ('op', '|') and self.t[self.i + 1] == ('kw', 'getline'):
                self.i += 2
                lv = self.opt_lvalue()
                left = ('cmdgetline', left, lv)
            else:
                break
        return left

    def additive(self):
        left = self.mul()
        while self.is_op('+') or self.is_op('-'):
            op = self.next()[1]
            left = ('bin', op, left, self.mul())
        return left

    def mul(self):
        left = self.unary()
        while self.is_op('*') or self.is_op('/') or self.is_op('%'):
            op = self.next()[1]
            left = ('bin', op, left, self.unary())
        return left

    def unary(self):
        if self.accept('!'):
            return ('not', self.unary())
        if self.accept('-'):
            return ('neg', self.unary())
        if self.accept('+'):
            return ('pos', self.unary())
        return self.power()

    def power(self):
        base = self.postfix()
        if self.accept('^'):
            if self.accept('-'):
                return ('bin', '^', base, ('neg', self.power()))
            return ('bin', '^', base, self.power())
        return base

    def postfix(self):
        e = self.primary()
        if e[0] in ('var', 'idx', 'field') and (self.is_op('++') or self.is_op('--')):
            return ('post', self.next()[1], e)
        return e

    def opt_lvalue(self):
        tok = self.peek()
        if tok[0] == 'name' or (tok[0] == 'op' and tok[1] == '$'):
            return self.primary()
        return None

    def primary(self):
        tok = self.next()
        k, v = tok[0], tok[1]
        if k == 'num':
            return ('num', v)
        if k == 'str':
            return ('str', v)
        if k == 'ere':
            return ('ere', v)
        if k == 'op':
            if v == '$':
                if self.is_op('++') or self.is_op('--'):
                    op = self.next()[1]
                    return ('field', ('pre', op, self.primary()))
                return ('field', self.primary())
            if v == '(':
                items = self.expr_list(')')
                if len(items) == 1:
                    return ('paren', items[0])
                return ('group', items)
            if v in ('++', '--'):
                lv = self.primary()
                if lv[0] not in ('var', 'idx', 'field'):
                    raise AwkError('syntax error: lvalue required')
                return ('pre', v, lv)
            if v == '-':
                return ('neg', self.unary())
            if v == '!':
                return ('not', self.unary())
        if k == 'builtin':
            args = []
            if self.accept('('):
                args = self.expr_list(')')
            elif v != 'length':
                raise AwkError("syntax error: '(' expected after %s" % v)
            return ('bcall', v, args)
        if k == 'func':
            self.expect('(')
            return ('call', v, self.expr_list(')'))
        if k == 'name':
            if self.accept('['):
                return ('idx', v, self.expr_list(']'))
            return ('var', v)
        if k == 'kw' and v == 'getline':
            lv = self.opt_lvalue()
            src = None
            if self.accept('<'):
                src = self.primary()
            return ('getline', lv, src)
        raise AwkError("syntax error near '%s'" % (v if v is not None else k))


# ---------------------------------------------------------------- runtime
def looks_numeric(s):
    return _NUMSTR_RE.match(s) is not None


def to_num(v):
    if type(v) is float:
        return v
    m = _NUMPFX_RE.match(v)
    if not m:
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        return 0.0


def num_to_str(v, fmt):
    if v == int(v) and abs(v) < 1e16:
        return str(int(v))
    if v != v:
        return 'nan'
    if v in (float('inf'), float('-inf')):
        return 'inf' if v > 0 else '-inf'
    return fmt % v


class Awk(object):
    def __init__(self, sh, prog_src):
        self.sh = sh
        p = Parser(prog_src)
        self.begin, self.main, self.end = p.program()
        self.funcs = p.funcs
        self.g = {'FS': ' ', 'OFS': ' ', 'ORS': '\n', 'RS': '\n', 'NR': 0.0, 'FNR': 0.0,
                  'SUBSEP': '\x1c', 'CONVFMT': '%.6g', 'OFMT': '%.6g', 'RSTART': 0.0,
                  'RLENGTH': -1.0, 'FILENAME': '', 'ENVIRON': dict(
                      (k, StrNum(v)) for k, v in sh.export_env().items())}
        self.frames = []
        self.fields = ['']
        self.nf = 0
        self.rx_cache = {}
        self.outs = {}
        self.out = []
        self.out_size = 0
        self.inputs = {}
        self.records = None
        self.rng = random.Random(0)
        self.seed = 0.0
        self.range_on = {}

    # ---- helpers
    def rx(self, src):
        r = self.rx_cache.get(src)
        if r is None:
            try:
                r = re.compile(pattern.posix_to_py(src, ere=True))
            except re.error as e:
                raise AwkError('invalid regular expression /%s/: %s' % (src, e))
            self.rx_cache[src] = r
        return r

    def s(self, v):
        if type(v) is float:
            return num_to_str(v, self.g['CONVFMT'])
        return v

    def outstr(self, v):
        if type(v) is float:
            return num_to_str(v, self.g['OFMT'])
        return v

    def truth(self, v):
        if type(v) is float:
            return v != 0
        if isinstance(v, StrNum) and (v is UNINIT or looks_numeric(v)):
            return to_num(v) != 0
        return v != ''

    def write(self, text):
        self.out.append(text)
        self.out_size += len(text)
        if self.out_size > 65536:
            self.flush()

    def flush(self):
        if self.out:
            data = ''.join(self.out)
            self.out = []
            self.out_size = 0
            self.sh.out(data)

    # ---- records / fields
    def set_record(self, rec):
        self.fields = [rec]
        self.split_fields(rec)

    def split_fields(self, rec):
        fs = self.s(self.g['FS'])
        if fs == ' ':
            parts = rec.split()
        elif rec == '':
            parts = []
        elif len(fs) == 1 and fs != '\\':
            parts = rec.split(fs)
        elif fs == '\\t':
            parts = rec.split('\t')
        else:
            parts = self.rx(fs).split(rec)
        self.fields = [rec] + parts
        self.nf = len(parts)

    def rebuild(self):
        ofs = self.s(self.g['OFS'])
        self.fields[0] = ofs.join(self.fields[1:self.nf + 1])

    def get_field(self, i):
        if i < 0:
            raise AwkError('attempt to access field %d' % i)
        if i > self.nf:
            return UNINIT
        return StrNum(self.fields[i])

    def set_field(self, i, val):
        if i < 0:
            raise AwkError('attempt to access field %d' % i)
        if i == 0:
            self.set_record(val)
            return
        while self.nf < i:
            self.fields.append('')
            self.nf += 1
        del self.fields[self.nf + 1:]
        self.fields[i] = val
        self.rebuild()

    def set_nf(self, n):
        n = int(n)
        while self.nf < n:
            self.fields.append('')
            self.nf += 1
        self.nf = n
        del self.fields[n + 1:]
        self.rebuild()

    # ---- variables
    def scope_of(self, name):
        if self.frames and name in self.frames[-1]:
            return self.frames[-1]
        return self.g

    def getvar(self, name):
        if name == 'NF':
            return float(self.nf)
        v = self.scope_of(name).get(name)
        if v is None:
            return UNINIT
        if isinstance(v, dict):
            raise AwkError("can't use array %s in a scalar context" % name)
        return v

    def setvar(self, name, val):
        if name == 'NF':
            self.set_nf(to_num(val))
            return
        self.scope_of(name)[name] = val

    def array(self, name):
        sc = self.scope_of(name)
        a = sc.get(name)
        if a is None or a is UNINIT:
            a = {}
            sc[name] = a
        elif not isinstance(a, dict):
            raise AwkError("can't use scalar %s as an array" % name)
        return a

    def subscript(self, subs):
        if len(subs) == 1:
            return self.s(self.ev(subs[0]))
        return self.s(self.g['SUBSEP']).join(self.s(self.ev(x)) for x in subs)

    def assign(self, lv, val):
        k = lv[0]
        if k == 'var':
            self.setvar(lv[1], val)
        elif k == 'idx':
            self.array(lv[1])[self.subscript(lv[2])] = val
        elif k == 'field':
            self.set_field(int(to_num(self.ev(lv[1]))), self.s(val))
        else:
            raise AwkError('assignment to non-lvalue')

    # ---- expressions
    def compare(self, a, b):
        an = type(a) is float or (isinstance(a, StrNum) and (a is UNINIT or looks_numeric(a)))
        bn = type(b) is float or (isinstance(b, StrNum) and (b is UNINIT or looks_numeric(b)))
        if an and bn:
            x, y = to_num(a), to_num(b)
        else:
            x, y = self.s(a), self.s(b)
        return -1 if x < y else (1 if x > y else 0)

    def regex_of(self, node):
        if node[0] == 'ere':
            return self.rx(node[1])
        return self.rx(self.s(self.ev(node)))

    def ev(self, n):
        k = n[0]
        if k == 'num' or k == 'str':
            return n[1]
        if k == 'var':
            return self.getvar(n[1])
        if k == 'field':
            return self.get_field(int(to_num(self.ev(n[1]))))
        if k == 'idx':
            a = self.array(n[1])
            key = self.subscript(n[2])
            v = a.get(key)
            if v is None:
                a[key] = UNINIT
                return UNINIT
            return v
        if k == 'paren':
            return self.ev(n[1])
        if k == 'assign':
            op, lv = n[1], n[2]
            val = self.ev(n[3])
            if op != '=':
                val = self.arith(op[0], to_num(self.ev(lv)), to_num(val))
            elif isinstance(val, dict):
                raise AwkError("can't assign an array")
            self.assign(lv, val)
            return val
        if k == 'cat':
            return self.s(self.ev(n[1])) + self.s(self.ev(n[2]))
        if k == 'bin':
            return self.arith(n[1], to_num(self.ev(n[2])), to_num(self.ev(n[3])))
        if k == 'cmp':
            c = self.compare(self.ev(n[2]), self.ev(n[3]))
            op = n[1]
            r = (c < 0 if op == '<' else c <= 0 if op == '<=' else c == 0 if op == '=='
                 else c != 0 if op == '!=' else c > 0 if op == '>' else c >= 0)
            return 1.0 if r else 0.0
        if k == '&&':
            return 1.0 if (self.truth(self.ev(n[1])) and self.truth(self.ev(n[2]))) else 0.0
        if k == '||':
            return 1.0 if (self.truth(self.ev(n[1])) or self.truth(self.ev(n[2]))) else 0.0
        if k == 'not':
            return 0.0 if self.truth(self.ev(n[1])) else 1.0
        if k == 'neg':
            return -to_num(self.ev(n[1]))
        if k == 'pos':
            return to_num(self.ev(n[1]))
        if k == '?:':
            return self.ev(n[2]) if self.truth(self.ev(n[1])) else self.ev(n[3])
        if k == 'ere':
            return 1.0 if self.rx(n[1]).search(self.fields[0]) else 0.0
        if k == 'match':
            m = self.regex_of(n[3]).search(self.s(self.ev(n[2]))) is not None
            return 1.0 if (m != n[1]) else 0.0
        if k == 'in':
            return 1.0 if self.subscript(n[1]) in self.array(n[2]) else 0.0
        if k == 'pre' or k == 'post':
            lv = n[2]
            old = to_num(self.ev(lv))
            new = old + (1 if n[1] == '++' else -1)
            self.assign(lv, new)
            return new if k == 'pre' else old
        if k == 'bcall':
            return self.builtin(n[1], n[2])
        if k == 'call':
            return self.call(n[1], n[2])
        if k == 'group':
            return self.s(self.g['SUBSEP']).join(self.s(self.ev(x)) for x in n[1])
        if k == 'getline':
            return self.getline(n[1], n[2])
        if k == 'cmdgetline':
            return self.cmd_getline(self.s(self.ev(n[1])), n[2])
        raise AwkError('internal: unknown node %s' % k)

    def arith(self, op, a, b):
        if op == '+':
            return a + b
        if op == '-':
            return a - b
        if op == '*':
            return a * b
        if op == '/':
            if b == 0:
                raise AwkError('division by zero')
            return a / b
        if op == '%':
            if b == 0:
                raise AwkError('division by zero in %')
            return math.fmod(a, b)
        if op == '^':
            try:
                return float(a ** b)
            except (OverflowError, ZeroDivisionError):
                return float('inf')
        raise AwkError('bad operator ' + op)

    def call(self, name, args):
        fn = self.funcs.get(name)
        if fn is None:
            raise AwkError('function %s not defined' % name)
        params, body = fn
        if len(args) > len(params):
            raise AwkError('function %s called with too many arguments' % name)
        if len(self.frames) > 800:
            raise AwkError('function call nesting too deep')
        frame = {}
        refs = []
        for i, p in enumerate(params):
            frame[p] = UNINIT
            if i >= len(args):
                continue
            a = args[i]
            if a[0] == 'var' and a[1] != 'NF':
                sc = self.scope_of(a[1])
                v = sc.get(a[1])
                if v is None or v is UNINIT:
                    # 未初期化のまま渡された変数は、呼び出し先で配列として使われうる
                    refs.append((p, sc, a[1]))
                else:
                    frame[p] = v            # 配列は参照渡し、スカラーは値渡し
            else:
                frame[p] = self.ev(a)
        self.frames.append(frame)
        try:
            self.run_stmt(body)
            ret = UNINIT
        except _Return as r:
            ret = r.value
        finally:
            self.frames.pop()
            for p, sc, nm in refs:
                if isinstance(frame.get(p), dict):
                    sc[nm] = frame[p]
        return ret

    # ---- builtins
    def builtin(self, name, args):
        ev = self.ev
        s = self.s
        if name == 'length':
            if not args:
                return float(len(self.fields[0]))
            a = args[0]
            if a[0] == 'var':
                v = self.scope_of(a[1]).get(a[1])
                if isinstance(v, dict):
                    return float(len(v))
            return float(len(s(ev(a))))
        if name == 'substr':
            # gawk と同じ規則: 開始位置と長さは小数点以下切り捨て、開始位置 < 1 は 1 とみなす
            text = s(ev(args[0]))
            start = int(to_num(ev(args[1])))
            if start < 1:
                start = 1
            if len(args) > 2:
                ln = int(to_num(ev(args[2])))
                if ln <= 0:
                    return ''
                return text[start - 1:start - 1 + ln]
            return text[start - 1:]
        if name == 'index':
            return float(s(ev(args[0])).find(s(ev(args[1]))) + 1)
        if name == 'split':
            text = s(ev(args[0]))
            if args[1][0] != 'var':
                raise AwkError('split: second argument must be an array')
            arr = self.array(args[1][1])
            arr.clear()
            if len(args) > 2:
                fs = args[2][1] if args[2][0] == 'ere' else s(ev(args[2]))
            else:
                fs = s(self.g['FS'])
            if text == '':
                parts = []
            elif fs == ' ':
                parts = text.split()
            elif fs == '':
                parts = list(text)
            elif len(fs) == 1 and fs != '\\':
                parts = text.split(fs)
            else:
                parts = self.rx(fs).split(text)
            for i, p in enumerate(parts):
                arr[str(i + 1)] = StrNum(p)
            return float(len(parts))
        if name in ('sub', 'gsub'):
            rx = self.regex_of(args[0])
            repl = s(ev(args[1]))
            target = args[2] if len(args) > 2 else ('field', ('num', 0.0))
            text = s(ev(target))
            count = [0]

            def rep(m):
                count[0] += 1
                out = []
                i = 0
                while i < len(repl):
                    c = repl[i]
                    if c == '\\' and i + 1 < len(repl) and repl[i + 1] in '&\\':
                        out.append(repl[i + 1])
                        i += 2
                    elif c == '&':
                        out.append(m.group(0))
                        i += 1
                    else:
                        out.append(c)
                        i += 1
                return ''.join(out)

            new = rx.sub(rep, text, count=0 if name == 'gsub' else 1)
            if count[0]:
                self.assign(target, new)
            return float(count[0])
        if name == 'match':
            m = self.regex_of(args[1]).search(s(ev(args[0])))
            if m:
                self.g['RSTART'] = float(m.start() + 1)
                self.g['RLENGTH'] = float(m.end() - m.start())
            else:
                self.g['RSTART'] = 0.0
                self.g['RLENGTH'] = -1.0
            return self.g['RSTART']
        if name == 'sprintf':
            vals = [ev(a) for a in args]
            return self.format(s(vals[0]), vals[1:]) if vals else ''
        if name == 'tolower':
            return s(ev(args[0])).lower()
        if name == 'toupper':
            return s(ev(args[0])).upper()
        if name == 'int':
            v = to_num(ev(args[0]))
            return float(int(v)) if v == v and v not in (float('inf'), float('-inf')) else v
        if name in ('sqrt', 'exp', 'log', 'sin', 'cos'):
            v = to_num(ev(args[0]))
            try:
                return float(getattr(math, name)(v))
            except (ValueError, OverflowError):
                return float('nan') if name in ('sqrt', 'log') else float('inf')
        if name == 'atan2':
            return math.atan2(to_num(ev(args[0])), to_num(ev(args[1])))
        if name == 'rand':
            return self.rng.random()
        if name == 'srand':
            old = self.seed
            self.seed = to_num(ev(args[0])) if args else float(int(time.time()))
            self.rng.seed(self.seed)
            return old
        if name == 'systime':
            return float(int(time.time()))
        if name == 'strftime':
            fmt = s(ev(args[0])) if args else '%a %b %e %H:%M:%S %Z %Y'
            ts = to_num(ev(args[1])) if len(args) > 1 else time.time()
            return timefmt.strftime(fmt, ts, len(args) > 2 and self.truth(ev(args[2])))
        if name == 'system':
            self.flush()
            for o in self.outs.values():
                o.flush()
            sub = self.sh.clone()
            return float(sub.run_isolated_code(s(ev(args[0]))))
        if name == 'close':
            key = s(ev(args[0]))
            st = 0.0
            o = self.outs.pop(key, None)
            if o is not None:
                st = float(o.close())
            self.inputs.pop(key, None)
            return st
        if name == 'fflush':
            self.flush()
            for o in self.outs.values():
                o.flush()
            return 0.0
        raise AwkError('function %s not supported' % name)

    def format(self, fmt, vals):
        idx = [0]

        def take():
            i = idx[0]
            idx[0] = i + 1
            return vals[i] if i < len(vals) else UNINIT

        def rep(m):
            flags, width, prec, conv = m.groups()
            if conv == '%':
                return '%'
            if width == '*':
                width = str(int(to_num(take())))
            if prec == '*':
                prec = str(int(to_num(take())))
            spec = '%' + flags + (width or '') + ('.' + prec if prec is not None else '')
            v = take()
            if conv in 'di':
                x = to_num(v)
                if x != x or x in (float('inf'), float('-inf')):
                    return (spec + 's') % ('nan' if x != x else ('inf' if x > 0 else '-inf'))
                return (spec + 'd') % int(x)
            if conv in 'ouxX':
                x = int(to_num(v))
                if x < 0:
                    x += 1 << 64
                return (spec + ('d' if conv == 'u' else conv)) % x
            if conv in 'eEfFgG':
                return (spec + conv) % to_num(v)
            if conv == 'c':
                if type(v) is float:
                    return (spec + 's') % chr(int(v) & 0x10FFFF)
                t = self.s(v)
                return (spec + 's') % t[:1]
            if conv == 's':
                return (spec + 's') % self.s(v)
            return m.group(0)

        return _FMT_RE.sub(rep, fmt)

    # ---- getline
    def next_record(self):
        if self.records is None:
            return None
        try:
            return next(self.records)
        except StopIteration:
            return None

    def getline(self, lv, src):
        if src is None:
            rec = self.next_record()
            if rec is None:
                return 0.0
            self.g['NR'] = to_num(self.g['NR']) + 1
            self.g['FNR'] = to_num(self.g['FNR']) + 1
            if lv is None:
                self.set_record(rec)
            else:
                self.assign(lv, StrNum(rec))
            return 1.0
        name = self.s(self.ev(src))
        it = self.inputs.get(name)
        if it is None:
            try:
                if name == '-' or name == '/dev/stdin':
                    data = self.sh.read_all(0)
                else:
                    with open(self.sh.abspath(name), 'rb') as f:
                        data = f.read()
            except OSError:
                return -1.0
            it = iter(_records(self.sh.dec(data), self.s(self.g['RS'])))
            self.inputs[name] = it
        try:
            rec = next(it)
        except StopIteration:
            return 0.0
        if lv is None:
            self.set_record(rec)
        else:
            self.assign(lv, StrNum(rec))
        return 1.0

    def cmd_getline(self, cmd, lv):
        it = self.inputs.get(cmd)
        if it is None:
            self.flush()
            text = self.sh.clone().command_subst_code(cmd)
            it = iter(_records(text + ('\n' if text else ''), self.s(self.g['RS'])))
            self.inputs[cmd] = it
        try:
            rec = next(it)
        except StopIteration:
            return 0.0
        self.g['NR'] = to_num(self.g['NR']) + 1
        if lv is None:
            self.set_record(rec)
        else:
            self.assign(lv, StrNum(rec))
        return 1.0

    # ---- statements
    def output(self, text, redir):
        if redir is None:
            self.write(text)
            return
        kind = redir[0]
        name = self.s(self.ev(redir[1]))
        o = self.outs.get(name)
        if o is None:
            self.flush()
            o = _Sink(self.sh, kind, name)
            self.outs[name] = o
        o.write(text)

    def run_stmt(self, n):
        k = n[0]
        if k == 'block':
            for st in n[1]:
                self.run_stmt(st)
        elif k == 'expr':
            self.ev(n[1])
        elif k == 'print':
            if n[1]:
                text = self.s(self.g['OFS']).join(self.outstr(self.ev(a)) for a in n[1])
            else:
                text = self.fields[0]
            self.output(text + self.s(self.g['ORS']), n[2])
        elif k == 'printf':
            if not n[1]:
                raise AwkError('printf: no format')
            vals = [self.ev(a) for a in n[1]]
            self.output(self.format(self.s(vals[0]), vals[1:]), n[2])
        elif k == 'if':
            if self.truth(self.ev(n[1])):
                self.run_stmt(n[2])
            elif n[3] is not None:
                self.run_stmt(n[3])
        elif k == 'while':
            while self.truth(self.ev(n[1])):
                try:
                    self.run_stmt(n[2])
                except _Break:
                    break
                except _Continue:
                    continue
        elif k == 'do':
            while True:
                try:
                    self.run_stmt(n[1])
                except _Break:
                    break
                except _Continue:
                    pass
                if not self.truth(self.ev(n[2])):
                    break
        elif k == 'for':
            if n[1] is not None:
                self.run_stmt(n[1])
            while n[2] is None or self.truth(self.ev(n[2])):
                try:
                    self.run_stmt(n[4])
                except _Break:
                    break
                except _Continue:
                    pass
                if n[3] is not None:
                    self.run_stmt(n[3])
        elif k == 'forin':
            for key in list(self.array(n[2]).keys()):
                self.setvar(n[1], StrNum(key))
                try:
                    self.run_stmt(n[3])
                except _Break:
                    break
                except _Continue:
                    continue
        elif k == 'delete':
            a = self.array(n[1])
            if n[2] is None:
                a.clear()
            else:
                a.pop(self.subscript(n[2]), None)
        elif k == 'next':
            raise _Next()
        elif k == 'exit':
            raise _Exit(int(to_num(self.ev(n[1]))) if n[1] is not None else None)
        elif k == 'return':
            raise _Return(self.ev(n[1]) if n[1] is not None else UNINIT)
        elif k == 'break':
            raise _Break()
        elif k == 'continue':
            raise _Continue()
        else:
            raise AwkError('internal: unknown statement %s' % k)

    def run_main_rules(self):
        for idx, rule in enumerate(self.main):
            pat, pat2, body = rule[0], rule[1], rule[2]
            if pat is None:
                hit = True
            elif pat2 is None:
                hit = self.truth(self.ev(pat))
            elif self.range_on.get(idx):
                hit = True
                if self.truth(self.ev(pat2)):
                    self.range_on[idx] = False
            elif self.truth(self.ev(pat)):
                hit = True
                self.range_on[idx] = not self.truth(self.ev(pat2))
            else:
                hit = False
            if hit:
                if body is None:
                    self.write(self.fields[0] + self.s(self.g['ORS']))
                else:
                    self.run_stmt(body)

    def run(self, operands):
        code = 0
        try:
            try:
                for b in self.begin:
                    self.run_stmt(b)
                if self.main or self.end:
                    self.records = self.record_stream(operands)
                    while True:
                        rec = self.next_record()
                        if rec is None:
                            break
                        self.g['NR'] = to_num(self.g['NR']) + 1
                        self.g['FNR'] = to_num(self.g['FNR']) + 1
                        self.set_record(rec)
                        try:
                            self.run_main_rules()
                        except _Next:
                            pass
            except _Exit as e:
                code = e.code or 0
            try:
                for b in self.end:
                    self.run_stmt(b)
            except _Exit as e:
                if e.code is not None:
                    code = e.code
        finally:
            self.flush()
            for o in list(self.outs.values()):
                o.close()
        return code

    def record_stream(self, operands):
        used = False
        for op in operands:
            m = re.match(r'([A-Za-z_][A-Za-z0-9_]*)=(.*)$', op)
            if m:
                self.g[m.group(1)] = StrNum(unescape(m.group(2)))
                continue
            used = True
            self.g['FILENAME'] = op
            self.g['FNR'] = 0.0
            if op == '-':
                data = self.sh.read_all(0)
            else:
                try:
                    with open(self.sh.abspath(op), 'rb') as f:
                        data = f.read()
                except OSError as e:
                    self.flush()
                    self.sh.err("awk: cannot open %s (%s)\n" % (op, e.strerror or e))
                    self.status_err = 2
                    continue
            for rec in _records(self.sh.dec(data), self.s(self.g['RS'])):
                yield rec
        if not used:
            f = self.sh.fds.get(0)
            if f is None:
                return
            rs = self.s(self.g['RS'])
            if rs == '\n':
                from .common import iter_lines
                for line, nl in iter_lines(self.sh, f):
                    yield line
                    if self.out:
                        self.flush()
            else:
                for rec in _records(self.sh.dec(self.sh.read_all(0)), rs):
                    yield rec


def _records(text, rs):
    if rs == '\n':
        if not text:
            return []
        lines = text.split('\n')
        if lines[-1] == '':
            lines.pop()
        return lines
    if rs == '':
        return [p.strip('\n') for p in re.split(r'\n\n+', text.strip('\n')) if p != '']
    parts = text.split(rs[0])
    if parts and parts[-1] in ('', '\n'):
        parts.pop()
    return parts


class _Sink(object):
    """print > file / >> file / | cmd の出力先。"""

    def __init__(self, sh, kind, name):
        self.sh = sh
        self.kind = kind
        self.name = name
        self.buf = []
        self.f = None
        if kind != '|':
            if name == '/dev/stdout':
                self.fd = 1
            elif name == '/dev/stderr':
                self.fd = 2
            else:
                self.fd = None
                self.f = open(sh.abspath(name), 'ab' if kind == '>>' else 'wb')

    def write(self, text):
        if self.kind == '|':
            self.buf.append(text)
        elif self.f is not None:
            self.f.write(self.sh.enc(text))
        else:
            self.sh.write_fd(self.fd, self.sh.enc(text))

    def flush(self):
        if self.f is not None:
            self.f.flush()

    def close(self):
        if self.kind == '|':
            data = self.sh.enc(''.join(self.buf))
            self.buf = []
            sub = self.sh.clone()
            f = sub._data_file(data)
            sub.fds[0] = f
            try:
                return sub.run_isolated_code(self.name)
            finally:
                f.close()
        if self.f is not None:
            self.f.close()
            self.f = None
        return 0


@applet(usage=2)
def a_awk(sh, argv):
    args = argv[1:]
    assigns = []
    fs = None
    prog = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--':
            i += 1
            break
        if a == '-F' and i + 1 < len(args):
            i += 1
            fs = args[i]
        elif a.startswith('-F') and len(a) > 2:
            fs = a[2:]
        elif a == '-v' and i + 1 < len(args):
            i += 1
            assigns.append(args[i])
        elif a.startswith('-v') and len(a) > 2:
            assigns.append(a[2:])
        elif a == '-f' and i + 1 < len(args):
            i += 1
            try:
                with open(sh.abspath(args[i]), 'rb') as f:
                    prog = (prog or '') + sh.dec(f.read()) + '\n'
            except OSError as e:
                sh.err('awk: %s: %s\n' % (args[i], e.strerror or e))
                return 2
        elif a.startswith('-') and len(a) > 1 and a not in ('-',):
            sh.err('awk: unsupported option %s\n' % a)
            return 2
        else:
            break
        i += 1
    rest = args[i:]
    if prog is None:
        if not rest:
            sh.err('usage: awk [-F fs] [-v var=value] [-f progfile | \'prog\'] [file ...]\n')
            return 2
        prog = rest[0]
        rest = rest[1:]
    try:
        awk = Awk(sh, prog)
        if fs is not None:
            awk.g['FS'] = '\t' if fs == 't' else unescape(fs)
        for a in assigns:
            name, eq, val = a.partition('=')
            if not eq or not _NAME_RE.match(name):
                sh.err("awk: invalid -v argument '%s'\n" % a)
                return 2
            awk.g[name] = StrNum(unescape(val))
        awk.status_err = 0
        code = awk.run(rest)
        return code or awk.status_err
    except AwkError as e:
        sh.err('awk: %s\n' % e)
        return 2
    except RecursionError:
        sh.err('awk: recursion too deep\n')
        return 2
