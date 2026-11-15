# -*- coding: utf-8 -*-
"""Bash 文法のレキサ兼・再帰下降パーサ。

設計メモ:
  * スクリプト全体を先に構文解析してから実行する(bash は逐次)。
    => 構文エラーは 1 行も実行する前に検出される(バッチ運用上は安全側)。
  * 文字列 s と位置 i を共有し、$( ) の中は同じストリーム上で再帰的に解析する。
  * 予約語はコマンド位置かつ無引用の単独語のときだけ予約語として扱う。
"""
from __future__ import unicode_literals

import bisect
import re

from .nodes import (Lit, Esc, SQ, DQ, Param, CmdSub, Arith, ProcSub, Word, ArrayLit,
                    Redir, Simple, Pipeline, AndOr, List, If, While, For, CFor, Case,
                    Group, Subshell, FuncDef, Cond, ArithCmd)


class ParseError(Exception):
    def __init__(self, msg, line=0):
        Exception.__init__(self, msg)
        self.msg = msg
        self.line = line


_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_DIGITS_RE = re.compile(r'[0-9]+')
_ASSIGN_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(\[[^\]\n]*\])?(\+)?=')
_IONUM_RE = re.compile(r'[0-9]+(?=[<>])')
_OPS = ('&&', '||', ';;&', ';;', ';&', '|&', '<<<', '<<-', '<<', '>>', '<&', '>&',
        '&>>', '&>', '>|', '<>', '(', ')', ';', '&', '|', '<', '>')
_REDIR_OPS = frozenset(('<', '>', '>>', '>|', '<>', '<&', '>&', '&>', '&>>', '<<', '<<-', '<<<'))
_META = frozenset(' \t\n;&|()<>')
_RBRACE = frozenset('}')
_SLASH_RBRACE = frozenset('/}')
_COLON_RBRACE = frozenset(':}')
_NOSTOP = frozenset()
_SPECIAL_PARAMS = '@*#?$!-'
_STOP_WORDS = frozenset(('then', 'else', 'elif', 'fi', 'do', 'done', 'esac', '}'))
_COND_BINOPS = frozenset(('==', '=', '!=', '=~', '-eq', '-ne', '-lt', '-le', '-gt', '-ge',
                          '-nt', '-ot', '-ef'))
_UNARY_RE = re.compile(r'-[a-zA-Z]$')
_ANSI_SIMPLE = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', "'": "'", '"': '"', 'a': '\a',
                'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f', 'v': '\v', '?': '?'}


class Tok(object):
    __slots__ = ('kind', 'value', 'text', 'line')

    def __init__(self, kind, value, line):
        self.kind = kind      # WORD OP NL EOF IONUM
        self.value = value
        self.text = None      # 無引用の単独リテラル語ならその文字列
        self.line = line

    def describe(self):
        if self.kind == 'EOF':
            return 'end of file'
        if self.kind == 'NL':
            return 'newline'
        if self.kind == 'WORD':
            return self.text if self.text is not None else 'word'
        return str(self.value)


def decode_ansi_c(body):
    """$'...' の中身をデコードする。"""
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c != '\\' or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        d = body[i + 1]
        if d in _ANSI_SIMPLE:
            out.append(_ANSI_SIMPLE[d])
            i += 2
        elif d == 'x':
            m = re.compile(r'[0-9a-fA-F]{1,2}').match(body, i + 2)
            if m:
                out.append(chr(int(m.group(), 16)))
                i = m.end()
            else:
                out.append('\\x')
                i += 2
        elif d == 'u' or d == 'U':
            m = re.compile(r'[0-9a-fA-F]{1,%d}' % (4 if d == 'u' else 8)).match(body, i + 2)
            if m:
                out.append(chr(int(m.group(), 16)))
                i = m.end()
            else:
                out.append('\\' + d)
                i += 2
        elif d in '01234567':
            m = re.compile(r'[0-7]{1,3}').match(body, i + 1)
            out.append(chr(int(m.group(), 8) & 0xFF))
            i = m.end()
        elif d == 'c' and i + 2 < n:
            out.append(chr(ord(body[i + 2].upper()) ^ 0x40))
            i += 3
        else:
            out.append('\\' + d)
            i += 2
    return ''.join(out)


class Parser(object):
    def __init__(self, src, lineno_base=1):
        self.s = src
        self.n = len(src)
        self.i = 0
        self.tok = None
        self.pending = []      # 未読のヒアドキュメント
        self._nl = None
        self.base = lineno_base
        self._ctok = None

    # ------------------------------------------------------------ utilities
    def lineno(self, pos=None):
        if self._nl is None:
            self._nl = [m.start() for m in re.finditer('\n', self.s)]
        return self.base + bisect.bisect_left(self._nl, self.i if pos is None else pos)

    def error(self, msg):
        raise ParseError(msg, self.lineno())

    def _unexpected(self, t):
        raise ParseError("syntax error near unexpected token `%s'" % t.describe(), t.line)

    # ------------------------------------------------------------ lexer
    def lex(self):
        s = self.s
        n = self.n
        while self.i < n:
            c = s[self.i]
            if c == ' ' or c == '\t' or c == '\r':
                self.i += 1
            elif c == '\\' and self.i + 1 < n and s[self.i + 1] == '\n':
                self.i += 2
            elif c == '#':
                j = s.find('\n', self.i)
                self.i = n if j < 0 else j
            else:
                break
        line = self.lineno()
        if self.i >= n:
            return Tok('EOF', None, line)
        c = s[self.i]
        if c == '\n':
            self.i += 1
            if self.pending:
                self._read_heredocs()
            return Tok('NL', None, line)
        m = _IONUM_RE.match(s, self.i)
        if m:
            self.i = m.end()
            return Tok('IONUM', int(m.group()), line)
        if c in '&|;()<>':
            if c in '<>' and self.i + 1 < n and s[self.i + 1] == '(':
                return self._lex_word(line)
            for op in _OPS:
                if s.startswith(op, self.i):
                    self.i += len(op)
                    return Tok('OP', op, line)
        return self._lex_word(line)

    def peek(self):
        if self.tok is None:
            self.tok = self.lex()
        return self.tok

    def next(self):
        t = self.peek()
        self.tok = None
        return t

    def _skip_nl(self):
        while self.peek().kind == 'NL':
            self.tok = None

    def _lex_word(self, line):
        s = self.s
        start = self.i
        m = _ASSIGN_RE.match(s, start)
        if m:
            name = m.group(1)
            sub = m.group(2)
            append = bool(m.group(3))
            self.i = m.end()
            if self.i < self.n and s[self.i] == '(' and sub is None:
                self.i += 1
                elems = self._read_array_literal()
                w = Word([Lit(s[start:self.i])])
                w.assign = (name, None, append, ArrayLit(elems))
                return Tok('WORD', w, line)
            vparts = self._read_parts()
            idx = None
            if sub is not None:
                idx = Parser(sub[1:-1], self.lineno()).parse_word_all()
            w = Word([Lit(s[start:m.end()])] + vparts)
            w.assign = (name, idx, append, Word(vparts))
            return Tok('WORD', w, line)
        parts = self._read_parts()
        if not parts:
            self.error("syntax error near unexpected token `%s'" % s[self.i:self.i + 1])
        t = Tok('WORD', Word(parts), line)
        if len(parts) == 1 and type(parts[0]) is Lit:
            t.text = parts[0].text
        return t

    # ------------------------------------------------------------ word readers
    def _read_parts(self, stops=_META, regex=False, sq_literal=False):
        s = self.s
        n = self.n
        parts = []
        buf = []
        depth = 0

        def flush():
            if buf:
                parts.append(Lit(''.join(buf)))
                del buf[:]

        while self.i < n:
            c = s[self.i]
            if regex:
                if c == '(':
                    depth += 1
                    buf.append(c)
                    self.i += 1
                    continue
                if c == ')':
                    if depth == 0:
                        break
                    depth -= 1
                    buf.append(c)
                    self.i += 1
                    continue
                if c == '|' or (depth > 0 and c in ' \t'):
                    buf.append(c)
                    self.i += 1
                    continue
                if c in ' \t\n':
                    break
                if c == '&' and s.startswith('&&', self.i):
                    break
            elif c in stops:
                if c in '<>' and stops is _META and self.i + 1 < n and s[self.i + 1] == '(' \
                        and not parts and not buf:
                    parts.append(self._read_procsub())
                    continue
                break
            if c == '\\':
                if self.i + 1 >= n:
                    buf.append('\\')
                    self.i += 1
                    continue
                d = s[self.i + 1]
                if d == '\n':
                    self.i += 2
                    continue
                flush()
                parts.append(Esc(d))
                self.i += 2
            elif c == "'" and not sq_literal:
                j = s.find("'", self.i + 1)
                if j < 0:
                    self.error("unexpected EOF while looking for matching `''")
                flush()
                parts.append(SQ(s[self.i + 1:j]))
                self.i = j + 1
            elif c == '"':
                self.i += 1
                flush()
                parts.append(DQ(self._read_dq()))
            elif c == '$':
                p = self._read_dollar(False)
                if p is None:
                    buf.append('$')
                    self.i += 1
                else:
                    flush()
                    parts.append(p)
            elif c == '`':
                flush()
                parts.append(self._read_backtick(False))
            elif c == '\r' and self.i + 1 < n and s[self.i + 1] == '\n':
                self.i += 1
            else:
                buf.append(c)
                self.i += 1
        flush()
        return parts

    def _read_dq(self, heredoc=False):
        s = self.s
        n = self.n
        parts = []
        buf = []

        def flush():
            if buf:
                parts.append(Lit(''.join(buf)))
                del buf[:]

        while True:
            if self.i >= n:
                if heredoc:
                    break
                self.error("unexpected EOF while looking for matching `\"'")
            c = s[self.i]
            if c == '"' and not heredoc:
                self.i += 1
                break
            if c == '\\':
                d = s[self.i + 1] if self.i + 1 < n else ''
                if d == '\n':
                    self.i += 2
                elif d and (d in '$`\\' or (d == '"' and not heredoc)):
                    buf.append(d)
                    self.i += 2
                else:
                    buf.append('\\')
                    self.i += 1
            elif c == '$':
                p = self._read_dollar(True)
                if p is None:
                    buf.append('$')
                    self.i += 1
                else:
                    flush()
                    parts.append(p)
            elif c == '`':
                flush()
                parts.append(self._read_backtick(True))
            else:
                buf.append(c)
                self.i += 1
        flush()
        return parts

    def _read_dollar(self, in_dq):
        """self.i は '$' を指している。展開でなければ None(位置は動かさない)。"""
        s = self.s
        i = self.i
        n = self.n
        if i + 1 >= n:
            return None
        c = s[i + 1]
        if c == '(':
            if s.startswith('((', i + 1):
                save = self.i
                try:
                    self.i = i + 3
                    return Arith(self._read_arith())
                except ParseError:
                    self.i = save
            self.i = i + 2
            return CmdSub(self._parse_nested())
        if c == '{':
            self.i = i + 2
            return self._read_brace_param(in_dq)
        if c == "'" and not in_dq:
            j = i + 2
            while j < n and s[j] != "'":
                j += 2 if s[j] == '\\' else 1
            if j >= n:
                self.error("unexpected EOF while looking for matching `''")
            self.i = j + 1
            return SQ(decode_ansi_c(s[i + 2:j]))
        if c == '"' and not in_dq:
            self.i = i + 2
            return DQ(self._read_dq())
        m = _NAME_RE.match(s, i + 1)
        if m:
            self.i = m.end()
            return Param(m.group())
        if c.isdigit() or c in _SPECIAL_PARAMS:
            self.i = i + 2
            return Param(c)
        return None

    def _read_arith(self):
        """'((' の直後から '))' までを Word として読む('))' は消費する)。"""
        s = self.s
        n = self.n
        parts = []
        buf = []
        depth = 0

        def flush():
            if buf:
                parts.append(Lit(''.join(buf)))
                del buf[:]

        while True:
            if self.i >= n:
                self.error("unexpected EOF while looking for matching `))'")
            c = s[self.i]
            if c == '(':
                depth += 1
                buf.append(c)
                self.i += 1
            elif c == ')':
                if depth == 0:
                    if s.startswith('))', self.i):
                        self.i += 2
                        break
                    self.error('syntax error in arithmetic expression')
                depth -= 1
                buf.append(c)
                self.i += 1
            elif c == '$':
                p = self._read_dollar(True)
                if p is None:
                    buf.append('$')
                    self.i += 1
                else:
                    flush()
                    parts.append(p)
            elif c == '`':
                flush()
                parts.append(self._read_backtick(True))
            elif c == '"':
                self.i += 1
                flush()
                parts.extend(self._read_dq())
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    self.error("unexpected EOF while looking for matching `''")
                buf.append(s[self.i + 1:j])
                self.i = j + 1
            elif c == '\\' and self.i + 1 < n and s[self.i + 1] == '\n':
                self.i += 2
            else:
                buf.append(c)
                self.i += 1
        flush()
        return Word(parts)

    def _find_bracket(self, i):
        """s[i]=='[' に対応する ']' の位置。"""
        s = self.s
        n = self.n
        depth = 0
        j = i
        while j < n:
            c = s[j]
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return j
            elif c == '\\':
                j += 1
            elif c == '\n':
                break
            elif c == '"' or c == "'":
                k = s.find(c, j + 1)
                if k < 0:
                    break
                j = k
            j += 1
        return -1

    def _read_brace_param(self, in_dq):
        """'${' の直後から '}' まで。"""
        s = self.s
        n = self.n
        if self.i >= n:
            self.error('bad substitution')
        p = Param(None)
        nxt = s[self.i + 1] if self.i + 1 < n else ''
        if s[self.i] == '#' and nxt != '}':
            p.length = True
            self.i += 1
        elif s[self.i] == '!' and nxt != '}':
            p.indirect = True
            self.i += 1
        m = _NAME_RE.match(s, self.i)
        if m:
            p.name = m.group()
            self.i = m.end()
        elif self.i < n and s[self.i].isdigit():
            m = _DIGITS_RE.match(s, self.i)
            p.name = m.group()
            self.i = m.end()
        elif self.i < n and s[self.i] in _SPECIAL_PARAMS:
            p.name = s[self.i]
            self.i += 1
        else:
            self.error('bad substitution')
        if self.i < n and s[self.i] == '[':
            j = self._find_bracket(self.i)
            if j < 0:
                self.error('bad substitution')
            sub = s[self.i + 1:j]
            self.i = j + 1
            if sub == '@' or sub == '*':
                p.index = sub
            else:
                p.index = Parser(sub, self.lineno()).parse_word_all()
        if self.i >= n:
            self.error("unexpected EOF while looking for matching `}'")
        c = s[self.i]
        if p.indirect and p.index is None and c in '*@' and s[self.i + 1:self.i + 2] == '}':
            p.op = 'prefix'
            self.i += 2
            return p
        if c == '}':
            self.i += 1
            return p
        if p.length:
            self.error('bad substitution')
        sq = in_dq
        if c == ':':
            d = s[self.i + 1] if self.i + 1 < n else ''
            if d and d in '-=?+':
                p.op = ':' + d
                self.i += 2
                p.arg = Word(self._read_parts(_RBRACE, sq_literal=sq))
            else:
                p.op = 'substr'
                self.i += 1
                p.arg = Word(self._read_parts(_COLON_RBRACE, sq_literal=sq))
                if self.i < n and s[self.i] == ':':
                    self.i += 1
                    p.arg2 = Word(self._read_parts(_RBRACE, sq_literal=sq))
        elif c in '-=?+':
            p.op = c
            self.i += 1
            p.arg = Word(self._read_parts(_RBRACE, sq_literal=sq))
        elif c in '#%':
            if s[self.i + 1:self.i + 2] == c:
                p.op = c + c
                self.i += 2
            else:
                p.op = c
                self.i += 1
            p.arg = Word(self._read_parts(_RBRACE))
        elif c == '/':
            p.op = '/'
            self.i += 1
            if self.i < n and s[self.i] in '/#%':
                p.op += s[self.i]
                self.i += 1
            p.arg = Word(self._read_parts(_SLASH_RBRACE))
            if self.i < n and s[self.i] == '/':
                self.i += 1
                p.arg2 = Word(self._read_parts(_RBRACE))
        elif c in '^,':
            if s[self.i + 1:self.i + 2] == c:
                p.op = c + c
                self.i += 2
            else:
                p.op = c
                self.i += 1
            p.arg = Word(self._read_parts(_RBRACE))
        elif c == '@' and self.i + 1 < n:
            p.op = '@' + s[self.i + 1]
            self.i += 2
        else:
            self.error('bad substitution')
        if self.i >= n or s[self.i] != '}':
            self.error('bad substitution')
        self.i += 1
        return p

    def _read_backtick(self, in_dq):
        s = self.s
        n = self.n
        i = self.i + 1
        buf = []
        while True:
            if i >= n:
                self.error("unexpected EOF while looking for matching ``'")
            c = s[i]
            if c == '`':
                break
            if c == '\\' and i + 1 < n and (s[i + 1] in '$`\\' or (in_dq and s[i + 1] == '"')):
                buf.append(s[i + 1])
                i += 2
            else:
                buf.append(c)
                i += 1
        line = self.lineno()
        self.i = i + 1
        return CmdSub(Parser(''.join(buf), line).parse_program())

    def _read_procsub(self):
        kind = self.s[self.i]
        self.i += 2
        return ProcSub(kind, self._parse_nested())

    def _parse_nested(self):
        """'$(' の直後から対応する ')' までを同じストリーム上で解析する。"""
        saved_tok, saved_pending, saved_ctok = self.tok, self.pending, self._ctok
        self.tok = None
        self.pending = []
        self._ctok = None
        node = self.parse_list()
        t = self.next()
        if not (t.kind == 'OP' and t.value == ')'):
            self._unexpected(t)
        self.tok, self.pending, self._ctok = saved_tok, saved_pending, saved_ctok
        return node

    def _read_array_literal(self):
        s = self.s
        n = self.n
        elems = []
        while True:
            while self.i < n:
                c = s[self.i]
                if c in ' \t\n\r':
                    self.i += 1
                elif c == '#':
                    j = s.find('\n', self.i)
                    self.i = n if j < 0 else j
                elif c == '\\' and s.startswith('\\\n', self.i):
                    self.i += 2
                else:
                    break
            if self.i >= n:
                self.error("unexpected EOF while looking for matching `)'")
            if s[self.i] == ')':
                self.i += 1
                break
            key = None
            if s[self.i] == '[':
                j = self._find_bracket(self.i)
                if j > 0 and s[j + 1:j + 2] == '=':
                    key = Parser(s[self.i + 1:j], self.lineno()).parse_word_all()
                    self.i = j + 2
            parts = self._read_parts()
            if not parts and key is None:
                self.error("syntax error near unexpected token `%s'" % s[self.i:self.i + 1])
            elems.append((key, Word(parts)))
        return elems

    def parse_word_all(self):
        """ソース全体を 1 語として読む(添字・算術式など)。"""
        return Word(self._read_parts(_NOSTOP))

    def _read_heredocs(self):
        s = self.s
        n = self.n
        pending = self.pending
        self.pending = []
        for (redir, delim, strip, quoted) in pending:
            lines = []
            base_line = self.lineno()
            while self.i < n:
                j = s.find('\n', self.i)
                if j < 0:
                    j = n
                line = s[self.i:j]
                self.i = min(j + 1, n)
                if line.endswith('\r'):
                    line = line[:-1]
                if strip:
                    line = line.lstrip('\t')
                if line == delim:
                    break
                lines.append(line)
            body = ''.join(l + '\n' for l in lines)
            if quoted:
                redir.target = Word([SQ(body)])
            else:
                redir.target = Word([DQ(Parser(body, base_line)._read_dq(heredoc=True))])

    # ------------------------------------------------------------ grammar
    def parse_program(self):
        node = self.parse_list()
        t = self.peek()
        if t.kind != 'EOF':
            self._unexpected(t)
        return node

    def parse_list(self):
        items = []
        breaks = []
        while True:
            self._skip_nl()
            t = self.peek()
            if t.kind == 'EOF':
                break
            if t.kind == 'OP' and t.value in (')', ';;', ';&', ';;&'):
                break
            if t.kind == 'WORD' and t.text in _STOP_WORDS:
                break
            node = self.parse_andor()
            t = self.peek()
            if t.kind == 'OP' and t.value == ';':
                self.tok = None
                items.append((node, False))
                breaks.append(self.peek().kind in ('NL', 'EOF'))
            elif t.kind == 'OP' and t.value == '&':
                self.tok = None
                items.append((node, True))
                breaks.append(self.peek().kind in ('NL', 'EOF'))
            else:
                items.append((node, False))
                breaks.append(True)
                if t.kind != 'NL':
                    break
        return List(items, breaks)

    def parse_andor(self):
        first = self.parse_pipeline()
        rest = []
        while True:
            t = self.peek()
            if t.kind == 'OP' and t.value in ('&&', '||'):
                self.tok = None
                self._skip_nl()
                rest.append((t.value, self.parse_pipeline()))
            else:
                break
        if not rest:
            return first
        return AndOr(first, rest)

    def parse_pipeline(self):
        negate = False
        t = self.peek()
        while t.kind == 'WORD' and t.text in ('!', 'time'):
            self.tok = None
            if t.text == '!':
                negate = not negate
            t = self.peek()
        cmds = [self.parse_command()]
        stderr_too = []
        while True:
            t = self.peek()
            if t.kind == 'OP' and t.value in ('|', '|&'):
                self.tok = None
                self._skip_nl()
                stderr_too.append(t.value == '|&')
                cmds.append(self.parse_command())
            else:
                break
        if len(cmds) == 1 and not negate:
            return cmds[0]
        return Pipeline(cmds, negate, stderr_too)

    def _expect_word(self, text):
        t = self.next()
        if not (t.kind == 'WORD' and t.text == text):
            raise ParseError("syntax error near unexpected token `%s' (expected `%s')"
                             % (t.describe(), text), t.line)

    def _parse_redirs_into(self, node):
        while True:
            t = self.peek()
            if t.kind == 'IONUM' or (t.kind == 'OP' and t.value in _REDIR_OPS):
                node.redirs.append(self._parse_redir())
            else:
                break
        return node

    def parse_command(self):
        t = self.peek()
        if t.kind == 'OP' and t.value == '(':
            if self.i < self.n and self.s[self.i] == '(':
                self.tok = None
                self.i += 1
                return self._parse_redirs_into(ArithCmd(self._read_arith(), t.line))
            self.tok = None
            body = self.parse_list()
            c = self.next()
            if not (c.kind == 'OP' and c.value == ')'):
                self._unexpected(c)
            return self._parse_redirs_into(Subshell(body))
        if t.kind == 'WORD' and t.text is not None:
            w = t.text
            if w == '{':
                self.tok = None
                body = self.parse_list()
                self._expect_word('}')
                return self._parse_redirs_into(Group(body))
            if w == 'if':
                self.tok = None
                return self._parse_redirs_into(self._parse_if())
            if w == 'while' or w == 'until':
                self.tok = None
                cond = self.parse_list()
                self._expect_word('do')
                body = self.parse_list()
                self._expect_word('done')
                return self._parse_redirs_into(While(cond, body, w == 'until'))
            if w == 'for':
                self.tok = None
                return self._parse_redirs_into(self._parse_for())
            if w == 'case':
                self.tok = None
                return self._parse_redirs_into(self._parse_case())
            if w == '[[':
                self.tok = None
                expr = self._parse_cond_or()
                e = self._cnext()
                if e[0] != 'END':
                    self.error("syntax error in conditional expression")
                return self._parse_redirs_into(Cond(expr, t.line))
            if w == 'function':
                self.tok = None
                nt = self.next()
                if nt.kind != 'WORD' or nt.text is None:
                    self._unexpected(nt)
                p = self.peek()
                if p.kind == 'OP' and p.value == '(':
                    self.tok = None
                    c = self.next()
                    if not (c.kind == 'OP' and c.value == ')'):
                        self._unexpected(c)
                self._skip_nl()
                return FuncDef(nt.text, self.parse_command(), nt.line)
            if w in ('select', 'coproc'):
                raise ParseError("`%s' is not supported by bashwin" % w, t.line)
            if w in _STOP_WORDS or w in ('in', 'do', ']]'):
                self._unexpected(t)
        if t.kind in ('EOF', 'NL') or (t.kind == 'OP' and t.value not in _REDIR_OPS):
            self._unexpected(t)
        return self._parse_simple()

    def _parse_if(self):
        clauses = []
        cond = self.parse_list()
        self._expect_word('then')
        clauses.append((cond, self.parse_list()))
        else_body = None
        while True:
            t = self.next()
            if t.kind == 'WORD' and t.text == 'elif':
                cond = self.parse_list()
                self._expect_word('then')
                clauses.append((cond, self.parse_list()))
            elif t.kind == 'WORD' and t.text == 'else':
                else_body = self.parse_list()
                self._expect_word('fi')
                break
            elif t.kind == 'WORD' and t.text == 'fi':
                break
            else:
                self._unexpected(t)
        return If(clauses, else_body)

    def _split_arith(self, word):
        """for ((a;b;c)) の式を ';' で 3 分割する。"""
        segs = [[]]
        for p in word.parts:
            if type(p) is Lit and ';' in p.text:
                pieces = p.text.split(';')
                for k, piece in enumerate(pieces):
                    if k > 0:
                        segs.append([])
                    if piece:
                        segs[-1].append(Lit(piece))
            else:
                segs[-1].append(p)
        if len(segs) != 3:
            self.error('syntax error: arithmetic for requires three expressions')
        return [Word(x) if x else None for x in segs]

    def _parse_for(self):
        t = self.peek()
        if t.kind == 'OP' and t.value == '(' and self.i < self.n and self.s[self.i] == '(':
            self.tok = None
            self.i += 1
            init, cond, step = self._split_arith(self._read_arith())
            t = self.peek()
            if t.kind == 'OP' and t.value == ';':
                self.tok = None
            self._skip_nl()
            self._expect_word('do')
            body = self.parse_list()
            self._expect_word('done')
            return CFor(init, cond, step, body)
        t = self.next()
        if t.kind != 'WORD' or t.text is None or not _NAME_RE.match(t.text):
            self._unexpected(t)
        var = t.text
        words = None
        self._skip_nl()
        t = self.peek()
        if t.kind == 'WORD' and t.text == 'in':
            self.tok = None
            words = []
            while True:
                t = self.peek()
                if t.kind == 'WORD':
                    self.tok = None
                    words.append(t.value)
                else:
                    break
        t = self.peek()
        if t.kind == 'OP' and t.value == ';':
            self.tok = None
        self._skip_nl()
        self._expect_word('do')
        body = self.parse_list()
        self._expect_word('done')
        return For(var, words, body)

    def _parse_case(self):
        t = self.next()
        if t.kind != 'WORD':
            self._unexpected(t)
        word = t.value
        self._skip_nl()
        self._expect_word('in')
        items = []
        while True:
            self._skip_nl()
            t = self.peek()
            if t.kind == 'WORD' and t.text == 'esac':
                self.tok = None
                break
            if t.kind == 'EOF':
                self._unexpected(t)
            if t.kind == 'OP' and t.value == '(':
                self.tok = None
            pats = []
            while True:
                t = self.next()
                if t.kind != 'WORD':
                    self._unexpected(t)
                pats.append(t.value)
                t = self.next()
                if t.kind == 'OP' and t.value == '|':
                    continue
                if t.kind == 'OP' and t.value == ')':
                    break
                self._unexpected(t)
            body = self.parse_list()
            term = ';;'
            t = self.peek()
            if t.kind == 'OP' and t.value in (';;', ';&', ';;&'):
                self.tok = None
                term = t.value
            items.append((pats, body, term))
        return Case(word, items)

    def _parse_redir(self):
        t = self.next()
        fd = None
        if t.kind == 'IONUM':
            fd = t.value
            t = self.next()
            if not (t.kind == 'OP' and t.value in _REDIR_OPS):
                self._unexpected(t)
        op = t.value
        if op in ('<<', '<<-'):
            s = self.s
            while self.i < self.n and s[self.i] in ' \t':
                self.i += 1
            parts = self._read_parts()
            if not parts:
                self.error('syntax error: here-document delimiter expected')
            quoted = any(type(p) is not Lit for p in parts)
            delim = []
            for p in parts:
                if type(p) is DQ:
                    delim.extend(getattr(q, 'text', '') for q in p.parts)
                else:
                    delim.append(getattr(p, 'text', ''))
            r = Redir(fd, op, None)
            r.heredoc_quoted = quoted
            self.pending.append((r, ''.join(delim), op == '<<-', quoted))
            return r
        wt = self.next()
        if wt.kind != 'WORD':
            self._unexpected(wt)
        return Redir(fd, op, wt.value)

    def _parse_simple(self):
        assigns = []
        words = []
        redirs = []
        line = self.peek().line
        while True:
            t = self.peek()
            if t.kind == 'IONUM' or (t.kind == 'OP' and t.value in _REDIR_OPS):
                redirs.append(self._parse_redir())
            elif t.kind == 'WORD':
                self.tok = None
                if not words and t.value.assign is not None:
                    assigns.append(t.value.assign)
                    continue
                words.append(t.value)
                if len(words) == 1 and not assigns and not redirs and t.text is not None:
                    p = self.peek()
                    if p.kind == 'OP' and p.value == '(':
                        self.tok = None
                        c = self.next()
                        if not (c.kind == 'OP' and c.value == ')'):
                            self._unexpected(c)
                        self._skip_nl()
                        return FuncDef(t.text, self.parse_command(), t.line)
            else:
                break
        return Simple(assigns, words, redirs, line)

    # ------------------------------------------------------------ [[ ... ]]
    def _cond_lex(self):
        s = self.s
        n = self.n
        while self.i < n:
            c = s[self.i]
            if c in ' \t\n\r':
                self.i += 1
            elif c == '\\' and s.startswith('\\\n', self.i):
                self.i += 2
            else:
                break
        if self.i >= n:
            self.error("unexpected EOF while looking for `]]'")
        if s.startswith(']]', self.i) and (self.i + 2 >= n or s[self.i + 2] in _META):
            self.i += 2
            return ('END', None, None)
        for op in ('&&', '||', '(', ')', '<', '>'):
            if s.startswith(op, self.i):
                self.i += len(op)
                return ('OP', op, None)
        parts = self._read_parts()
        if not parts:
            self.error("syntax error in conditional expression")
        text = parts[0].text if (len(parts) == 1 and type(parts[0]) is Lit) else None
        return ('WORD', Word(parts), text)

    def _cpeek(self):
        if self._ctok is None:
            self._ctok = self._cond_lex()
        return self._ctok

    def _cnext(self):
        t = self._cpeek()
        self._ctok = None
        return t

    def _parse_cond_or(self):
        left = self._parse_cond_and()
        while self._cpeek()[:2] == ('OP', '||'):
            self._ctok = None
            left = ('or', left, self._parse_cond_and())
        return left

    def _parse_cond_and(self):
        left = self._parse_cond_not()
        while self._cpeek()[:2] == ('OP', '&&'):
            self._ctok = None
            left = ('and', left, self._parse_cond_not())
        return left

    def _parse_cond_not(self):
        t = self._cpeek()
        if t[0] == 'WORD' and t[2] == '!':
            self._ctok = None
            return ('not', self._parse_cond_not())
        return self._parse_cond_primary()

    def _parse_cond_primary(self):
        t = self._cnext()
        if t[:2] == ('OP', '('):
            e = self._parse_cond_or()
            c = self._cnext()
            if c[:2] != ('OP', ')'):
                self.error("syntax error in conditional expression: expected `)'")
            return e
        if t[0] != 'WORD':
            self.error("syntax error in conditional expression")
        w, text = t[1], t[2]
        nt = self._cpeek()
        if text is not None and _UNARY_RE.match(text) and nt[0] == 'WORD' \
                and nt[2] not in _COND_BINOPS:
            self._ctok = None
            return ('unary', text, nt[1])
        if nt[0] == 'WORD' and nt[2] in _COND_BINOPS:
            self._ctok = None
            op = nt[2]
            if op == '=~':
                s = self.s
                while self.i < self.n and s[self.i] in ' \t':
                    self.i += 1
                return ('binary', '=~', w, Word(self._read_parts(regex=True)))
            rt = self._cnext()
            if rt[0] != 'WORD':
                self.error("syntax error in conditional expression")
            return ('binary', op, w, rt[1])
        if nt[0] == 'OP' and nt[1] in ('<', '>'):
            self._ctok = None
            rt = self._cnext()
            if rt[0] != 'WORD':
                self.error("syntax error in conditional expression")
            return ('binary', nt[1], w, rt[1])
        return ('word', w)


def parse(src, lineno_base=1):
    """ソース文字列を解析して List ノードを返す。"""
    if '\r' in src:
        src = src.replace('\r\n', '\n')
    return Parser(src, lineno_base).parse_program()
