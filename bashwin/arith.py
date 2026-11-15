# -*- coding: utf-8 -*-
"""算術式 $(( )) / (( )) / let の評価器。

bash と同じく C 言語の整数演算(符号付き 64bit、除算は 0 方向への切り捨て)。
変数の読み書きは env オブジェクト(arith_get / arith_set)経由。
"""
from __future__ import unicode_literals

import re


class ArithError(Exception):
    pass


_TOKEN_RE = re.compile(r'''
    \s*(?:
      (?P<num>[0-9]+\#[0-9A-Za-z@_]+|0[xX][0-9A-Fa-f]+|[0-9]+)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<op>\*\*=?|<<=|>>=|\+\+|--|&&|\|\||<<|>>|<=|>=|==|!=|[-+*/%&|^]=|[-+*/%<>=!~&|^?:,()\[\]])
    )''', re.X)

_ASSIGN_OPS = frozenset(('=', '+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^=', '**='))
_BIN_PREC = [
    ('||',), ('&&',), ('|',), ('^',), ('&',), ('==', '!='), ('<', '<=', '>', '>='),
    ('<<', '>>'), ('+', '-'), ('*', '/', '%'),
]


def _wrap(v):
    v &= 0xFFFFFFFFFFFFFFFF
    if v & 0x8000000000000000:
        v -= 0x10000000000000000
    return v


def parse_int(text):
    """bash の整数リテラル(10進, 0x, 0 始まり 8進, base#n)。"""
    t = text
    if '#' in t:
        base, digits = t.split('#', 1)
        base = int(base)
        if base < 2 or base > 64:
            raise ArithError('invalid arithmetic base')
        val = 0
        for ch in digits:
            if ch.isdigit():
                d = ord(ch) - 48
            elif 'a' <= ch <= 'z':
                d = ord(ch) - 97 + 10
            elif 'A' <= ch <= 'Z':
                d = (ord(ch) - 65 + 36) if base > 36 else (ord(ch) - 65 + 10)
            elif ch == '@':
                d = 62
            elif ch == '_':
                d = 63
            else:
                raise ArithError('value too great for base')
            if d >= base:
                raise ArithError('value too great for base')
            val = val * base + d
        return val
    if t[:2] in ('0x', '0X'):
        return int(t, 16)
    if len(t) > 1 and t[0] == '0':
        try:
            return int(t, 8)
        except ValueError:
            raise ArithError('value too great for base (error token is "%s")' % t)
    return int(t)


class _P(object):
    """遅延字句解析つきの再帰下降パーサ。

    連想配列の添字(例: cnt[fail:lint])は式ではなく生の文字列なので、
    字句解析せずにそのまま切り出す必要がある。そのため先読みは 1 トークンだけ行う。
    """

    def __init__(self, text, env=None):
        self.text = text
        self.env = env
        self.pos = 0
        self.tok = None

    def _lex(self):
        text = self.text
        m = _TOKEN_RE.match(text, self.pos)
        if not m or m.end() == self.pos:
            if text[self.pos:].strip() == '':
                return ('end', '', len(text), len(text))
            raise ArithError('syntax error in expression (error token is "%s")'
                             % text[self.pos:].strip())
        if m.group('num') is not None:
            return ('num', m.group('num'), m.start('num'), m.end())
        if m.group('name') is not None:
            return ('name', m.group('name'), m.start('name'), m.end())
        return ('op', m.group('op'), m.start('op'), m.end())

    def peek(self):
        if self.tok is None:
            self.tok = self._lex()
        return self.tok

    def next(self):
        t = self.peek()
        self.tok = None
        self.pos = t[3]
        return t

    def accept(self, op):
        t = self.peek()
        if t[0] == 'op' and t[1] == op:
            self.tok = None
            self.pos = t[3]
            return True
        return False

    def expect(self, op):
        if not self.accept(op):
            raise ArithError('syntax error in expression (error token is "%s")' % self.text)

    # 文法: comma > assign > ternary > binary... > unary > postfix
    def comma(self):
        left = self.assign()
        while self.accept(','):
            left = ('comma', left, self.assign())
        return left

    def assign(self):
        save_pos, save_tok = self.pos, self.tok
        t = self.peek()
        if t[0] == 'name':
            self.next()
            idx = None
            if self.accept('['):
                idx = self._subscript(t[1])
            op = self.peek()
            if op[0] == 'op' and op[1] in _ASSIGN_OPS:
                self.next()
                return ('assign', t[1], idx, op[1], self.assign())
            self.pos, self.tok = save_pos, save_tok
        return self.ternary()

    def _subscript(self, name):
        """'[' の直後。(式木|None, 生テキスト) を返す。"""
        if self.env is not None and self.env.arith_is_assoc(name):
            # 連想配列: 対応する ']' までを生の文字列キーとして取り出す
            text = self.text
            depth = 0
            j = self.pos
            while j < len(text):
                c = text[j]
                if c == '[':
                    depth += 1
                elif c == ']':
                    if depth == 0:
                        break
                    depth -= 1
                j += 1
            if j >= len(text):
                raise ArithError('bad array subscript (error token is "%s")' % text)
            raw = text[self.pos:j]
            self.pos = j + 1
            self.tok = None
            return (None, raw)
        start = self.peek()[2]
        e = self.comma()
        raw = self.text[start:self.peek()[2]]
        self.expect(']')
        return (e, raw)

    def ternary(self):
        cond = self.binary(0)
        if self.accept('?'):
            a = self.assign()
            self.expect(':')
            b = self.assign()
            return ('?', cond, a, b)
        return cond

    def binary(self, level):
        if level >= len(_BIN_PREC):
            return self.power()
        left = self.binary(level + 1)
        ops = _BIN_PREC[level]
        while True:
            t = self.peek()
            if t[0] == 'op' and t[1] in ops:
                self.next()
                left = (t[1], left, self.binary(level + 1))
            else:
                return left

    def power(self):
        base = self.unary()
        if self.accept('**'):
            return ('**', base, self.power())
        return base

    def unary(self):
        t = self.peek()
        if t[0] == 'op':
            if t[1] in ('!', '~', '-', '+'):
                self.next()
                return ('u' + t[1], self.unary())
            if t[1] in ('++', '--'):
                self.next()
                n = self.next()
                if n[0] != 'name':
                    raise ArithError('syntax error: operand expected')
                idx = self._subscript(n[1]) if self.accept('[') else None
                return ('pre', t[1], n[1], idx)
        return self.postfix()

    def postfix(self):
        t = self.next()
        if t[0] == 'num':
            return ('num', parse_int(t[1]))
        if t[0] == 'name':
            idx = self._subscript(t[1]) if self.accept('[') else None
            p = self.peek()
            if p[0] == 'op' and p[1] in ('++', '--'):
                self.next()
                return ('post', p[1], t[1], idx)
            return ('var', t[1], idx)
        if t[0] == 'op' and t[1] == '(':
            e = self.comma()
            self.expect(')')
            return e
        raise ArithError('syntax error: operand expected (error token is "%s")' % self.text.strip())


def _binop(op, a, b):
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    if op in ('/', '%'):
        if b == 0:
            raise ArithError('division by 0')
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q if op == '/' else a - q * b
    if op == '**':
        if b < 0:
            raise ArithError('exponent less than 0')
        return a ** b
    if op == '<<':
        return a << (b & 63)
    if op == '>>':
        return a >> (b & 63)
    if op == '&':
        return a & b
    if op == '|':
        return a | b
    if op == '^':
        return a ^ b
    if op == '==':
        return int(a == b)
    if op == '!=':
        return int(a != b)
    if op == '<':
        return int(a < b)
    if op == '<=':
        return int(a <= b)
    if op == '>':
        return int(a > b)
    if op == '>=':
        return int(a >= b)
    raise ArithError('bad operator ' + op)


class Evaluator(object):
    def __init__(self, env):
        self.env = env
        self.depth = 0

    def eval_text(self, text):
        text = text.strip()
        if not text:
            return 0
        self.depth += 1
        if self.depth > 64:
            self.depth = 0
            raise ArithError('expression recursion level exceeded')
        try:
            p = _P(text, self.env)
            tree = p.comma()
            if p.peek()[0] != 'end':
                raise ArithError('syntax error in expression (error token is "%s")' % text)
            return self.ev(tree)
        finally:
            self.depth -= 1

    def _key(self, name, idx):
        if idx is None:
            return None
        if self.env.arith_is_assoc(name):
            return idx[1].strip()
        return self.ev(idx[0])

    def _get(self, name, idx):
        k = self._key(name, idx)
        raw = self.env.arith_get(name, k)
        if raw is None or raw == '':
            return 0
        try:
            return parse_int(raw.strip())
        except (ValueError, ArithError):
            return self.eval_text(raw)

    def _set(self, name, idx, val):
        self.env.arith_set(name, self._key(name, idx), _wrap(val))

    def ev(self, t):
        op = t[0]
        if op == 'num':
            return t[1]
        if op == 'var':
            return self._get(t[1], t[2])
        if op == '||':
            return int(self.ev(t[1]) != 0 or self.ev(t[2]) != 0)
        if op == '&&':
            return int(self.ev(t[1]) != 0 and self.ev(t[2]) != 0)
        if op == '?':
            return self.ev(t[2]) if self.ev(t[1]) != 0 else self.ev(t[3])
        if op == 'comma':
            self.ev(t[1])
            return self.ev(t[2])
        if op == 'assign':
            _, name, idx, aop, rhs = t
            val = self.ev(rhs)
            if aop != '=':
                val = _binop(aop[:-1], self._get(name, idx), val)
            val = _wrap(val)
            self._set(name, idx, val)
            return val
        if op == 'pre':
            v = _wrap(self._get(t[2], t[3]) + (1 if t[1] == '++' else -1))
            self._set(t[2], t[3], v)
            return v
        if op == 'post':
            old = self._get(t[2], t[3])
            self._set(t[2], t[3], _wrap(old + (1 if t[1] == '++' else -1)))
            return old
        if op == 'u!':
            return int(self.ev(t[1]) == 0)
        if op == 'u~':
            return ~self.ev(t[1])
        if op == 'u-':
            return _wrap(-self.ev(t[1]))
        if op == 'u+':
            return self.ev(t[1])
        return _wrap(_binop(op, self.ev(t[1]), self.ev(t[2])))
