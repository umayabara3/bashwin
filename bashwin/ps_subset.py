# -*- coding: utf-8 -*-
"""PowerShell 変換可能性チェッカ(代替案「Bash -> PowerShell トランスパイラー」の計測器)。

スクリプトの AST を走査して、「意味を変えずに PowerShell へ機械変換できる範囲
(=変換可能サブセット)」から外れる構文を列挙する。変換そのものは行わない。

サブセットの考え方:
  * 制御構造・スカラー変数・条件判定・ネイティブ EXE の呼び出しは変換できる。
  * bash 固有の意味論に依存するものは変換できない(止める):
      - パイプライン(PowerShell はオブジェクト/テキスト再エンコードで別物)
      - 無引用の変数展開(単語分割とグロブが起きる)
      - 配列・連想配列、ヒアドキュメント、プロセス置換、サブシェル、trap
      - grep/sed/awk などの Unix コマンド(PowerShell 側に存在しない)
"""
from __future__ import unicode_literals

import re

from .nodes import (Lit, Esc, SQ, DQ, Param, CmdSub, Arith, ProcSub, Word, ArrayLit, Simple,
                    Pipeline, AndOr, List, If, While, For, CFor, Case, Group, Subshell,
                    FuncDef, Cond, ArithCmd)
from .parser import parse, ParseError

# PowerShell に同等の書き方がある組み込み
_OK_BUILTINS = frozenset((':', 'true', 'false', 'echo', 'exit', 'return', 'cd', 'export',
                          'local', 'test', '[', 'set', 'shift', 'break', 'continue', 'unset',
                          'pwd'))
_ARITH_OK = re.compile(r'[A-Za-z0-9_ \t+\-*/%()<>=!&|]*$')
_PARAM_OK = frozenset((None, ':-', '-'))
_COND_UNARY = frozenset(('-z', '-n', '-f', '-d', '-e', '-s', '-r', '-w'))
_COND_BINARY = frozenset(('==', '=', '!=', '-eq', '-ne', '-lt', '-le', '-gt', '-ge', '<', '>'))
_TEST_OPS = frozenset(('=', '==', '!=', '-eq', '-ne', '-lt', '-le', '-gt', '-ge', '-z', '-n',
                       '-f', '-d', '-e', '-s', '-r', '-w', '!', '-a', '-o', ']'))


class Checker(object):
    def __init__(self):
        self.problems = []      # [(line, category, message)]
        self.line = 0
        from . import applets, shbuiltins
        self.unix_tools = frozenset(applets.REGISTRY)
        self.shell_builtins = frozenset(shbuiltins.BUILTINS)

    def bad(self, category, msg):
        self.problems.append((self.line, category, msg))

    # ---- words
    def word(self, w, ctx='arg'):
        """ctx: 'arg'(コマンド引数) / 'str'(分割されない文脈) / 'pattern' / 'forlist'"""
        for p in w.parts:
            tp = type(p)
            if tp is Lit:
                t = p.text
                if ctx in ('arg', 'str') and ('*' in t or '?' in t or '[' in t):
                    self.bad('glob', 'pathname expansion in a command argument')
                if '{' in t and ('..' in t or ',' in t) and '}' in t:
                    self.bad('brace', 'brace expansion')
                if t.startswith('~'):
                    self.bad('tilde', 'tilde expansion')
            elif tp is Esc or tp is SQ:
                pass
            elif tp is DQ:
                for q in p.parts:
                    self.part(q, quoted=True)
            else:
                self.part(p, quoted=(ctx != 'arg' and ctx != 'forlist'))

    def part(self, p, quoted):
        tp = type(p)
        if tp is Lit:
            return
        if tp is Param:
            if p.index is not None:
                self.bad('array', 'array element / array expansion')
            elif p.length or p.indirect or p.op not in _PARAM_OK:
                self.bad('param-op', 'parameter expansion operator ${%s%s...}' % (
                    p.name, p.op or ('#' if p.length else '!')))
            elif p.name in ('*', '!', '-', '$') or (p.name == '@' and not quoted):
                self.bad('special-param', 'special parameter $%s' % p.name)
            elif not quoted and p.name != '@':
                self.bad('unquoted', 'unquoted expansion $%s (word splitting / globbing)' % p.name)
            if p.arg is not None:
                self.word(p.arg, 'str')
        elif tp is CmdSub:
            items = p.node.items
            if len(items) == 1 and type(items[0][0]) is Simple and items[0][0].words \
                    and not items[0][0].redirs:
                if not quoted:
                    self.bad('unquoted', 'unquoted command substitution (word splitting)')
                self.simple(items[0][0])
            else:
                self.bad('cmdsub', 'command substitution with a compound command or pipeline')
                self.node(p.node)
        elif tp is Arith:
            self.arith(p.word)
        elif tp is ProcSub:
            self.bad('procsub', 'process substitution')

    def arith(self, w, statement=False):
        text = []
        for p in w.parts:
            if type(p) is Lit:
                text.append(p.text)
            elif type(p) is Param and p.op is None and p.index is None and not p.length:
                text.append(p.name)
            else:
                self.bad('arith', 'arithmetic with nested expansion')
                return
        t = ''.join(text)
        if not _ARITH_OK.match(t) or '**' in t or '<<' in t or '>>' in t or '?' in t:
            self.bad('arith', 'arithmetic operator outside the portable set: %s' % t.strip())
        elif not statement and re.search(r'\+\+|--|[^=!<>]=[^=]', t):
            self.bad('arith', 'assignment inside arithmetic expansion: %s' % t.strip())

    # ---- commands
    def simple(self, n):
        self.line = n.line
        for name, idx, append, value in n.assigns:
            if idx is not None or type(value) is ArrayLit:
                self.bad('array', 'array assignment')
            elif append:
                self.bad('append', 'append assignment +=')
            else:
                self.word(value, 'str')
        if n.assigns and n.words:
            self.bad('tmpenv', 'temporary environment assignment before a command')
        for r in n.redirs:
            if r.op in ('<<', '<<-', '<<<'):
                self.bad('heredoc', 'here-document / here-string')
            elif r.op in ('<', '<>', '<&'):
                self.bad('stdin-redirect', 'input redirection')
            elif r.op == '>&' and not (r.fd == 2 and self._lit(r.target) == '1'):
                self.bad('fd-dup', 'file descriptor duplication other than 2>&1')
            elif r.target is not None:
                self.word(r.target, 'str')
        if not n.words:
            return
        name = self._lit(n.words[0])
        if name is None:
            # "$APP" のような「引用された単純変数」は PowerShell の & $APP に対応する
            parts = n.words[0].parts
            simple_var = (len(parts) == 1 and type(parts[0]) is DQ and len(parts[0].parts) == 1
                          and type(parts[0].parts[0]) is Param and parts[0].parts[0].op is None
                          and parts[0].parts[0].index is None)
            if not simple_var:
                self.bad('dynamic-command', 'command name is not a literal')
        elif name in self.unix_tools:
            self.bad('unix-tool', 'Unix command `%s` (does not exist in PowerShell)' % name)
        elif name in self.shell_builtins and name not in _OK_BUILTINS:
            self.bad('builtin', 'shell builtin `%s`' % name)
        elif name in ('test', '['):
            for w in n.words[1:]:
                t = self._lit(w)
                if t is not None and t.startswith('-') and len(t) > 1 and t not in _TEST_OPS:
                    self.bad('test-op', 'test operator %s' % t)
        elif name == 'echo':
            t = self._lit(n.words[1]) if len(n.words) > 1 else None
            if t is not None and t.startswith('-') and t not in ('-n',) and set(t[1:]) <= set('neE'):
                self.bad('echo-opt', 'echo %s (escape processing)' % t)
        elif name == 'set':
            for w in n.words[1:]:
                t = self._lit(w)
                if t not in ('-e', '-u', '-eu', '-ue', '+e', '+u'):
                    self.bad('set-opt', 'set %s' % (t or '<dynamic>'))
        elif name == 'local':
            for w in n.words[1:]:
                if w.assign is not None and type(w.assign[3]) is ArrayLit:
                    self.bad('array', 'local array')
        for w in n.words[1:]:
            if w.assign is not None and type(w.assign[3]) is not ArrayLit:
                self.word(w.assign[3], 'str')
            else:
                self.word(w, 'arg')

    @staticmethod
    def _lit(w):
        if w is None:
            return None
        out = []
        for p in w.parts:
            if type(p) in (Lit, Esc, SQ):
                out.append(p.text)
            else:
                return None
        return ''.join(out)

    def cond(self, e):
        k = e[0]
        if k in ('or', 'and'):
            self.cond(e[1])
            self.cond(e[2])
        elif k == 'not':
            self.cond(e[1])
        elif k == 'word':
            self.word(e[1], 'str')
        elif k == 'unary':
            if e[1] not in _COND_UNARY:
                self.bad('test-op', '[[ %s ]]' % e[1])
            self.word(e[2], 'str')
        else:
            if e[1] == '=~':
                self.bad('regex', '[[ =~ ]] regular expression match')
            elif e[1] not in _COND_BINARY:
                self.bad('test-op', '[[ %s ]]' % e[1])
            self.word(e[2], 'str')
            self.word(e[3], 'pattern')

    def redirs(self, n):
        if getattr(n, 'redirs', None):
            self.bad('compound-redirect', 'redirection attached to a compound command')

    def node(self, n):
        tp = type(n)
        if tp is List:
            for item, is_async in n.items:
                if is_async:
                    self.bad('background', 'background job (&)')
                self.node(item)
        elif tp is Simple:
            self.simple(n)
        elif tp is AndOr:
            self.node(n.first)
            for op, pl in n.rest:
                self.node(pl)
        elif tp is Pipeline:
            for k, c in enumerate(n.cmds):
                self.node(c)
                if k == 0 and len(n.cmds) > 1:
                    self.bad('pipeline', 'pipeline (|)')
        elif tp is If:
            self.redirs(n)
            for c, b in n.clauses:
                self.node(c)
                self.node(b)
            if n.else_body is not None:
                self.node(n.else_body)
        elif tp is While:
            self.redirs(n)
            self.node(n.cond)
            self.node(n.body)
        elif tp is For:
            self.redirs(n)
            for w in (n.words or []):
                self.word(w, 'forlist')
            self.node(n.body)
        elif tp is CFor:
            self.redirs(n)
            for w in (n.init, n.cond, n.step):
                if w is not None:
                    self.arith(w, statement=True)
            self.node(n.body)
        elif tp is Case:
            self.redirs(n)
            self.word(n.word, 'str')
            for pats, body, term in n.items:
                if term != ';;':
                    self.bad('case-fallthrough', 'case terminator %s' % term)
                for p in pats:
                    self.word(p, 'pattern')
                self.node(body)
        elif tp is Group:
            self.redirs(n)
            self.node(n.body)
        elif tp is Subshell:
            self.bad('subshell', 'subshell ( ... )')
            self.node(n.body)
        elif tp is FuncDef:
            self.line = n.line
            self.node(n.body)
        elif tp is Cond:
            self.line = n.line
            self.redirs(n)
            self.cond(n.expr)
        elif tp is ArithCmd:
            self.line = n.line
            self.redirs(n)
            self.arith(n.word, statement=True)


def check(src):
    """(問題のリスト, 構文エラー文字列|None) を返す。問題が空なら変換可能サブセット内。"""
    try:
        tree = parse(src)
    except ParseError as e:
        return [], 'line %d: %s' % (e.line, e.msg)
    c = Checker()
    c.node(tree)
    return c.problems, None


def check_file(path):
    import sys
    try:
        with open(path, 'rb') as f:
            src = f.read().decode('utf-8', 'surrogateescape')
    except (OSError, TypeError) as e:
        sys.stderr.write('bashwin: %s: %s\n' % (path, getattr(e, 'strerror', None) or e))
        return 2
    problems, err = check(src)
    if err:
        sys.stderr.write('%s: %s\n' % (path, err))
        return 2
    if not problems:
        sys.stdout.write('%s: within the PowerShell-transpilable subset\n' % path)
        return 0
    seen = set()
    for line, cat, msg in problems:
        key = (line, cat, msg)
        if key in seen:
            continue
        seen.add(key)
        sys.stdout.write('%s:%d: [%s] %s\n' % (path, line, cat, msg))
    cats = sorted(set(p[1] for p in problems))
    sys.stdout.write('%s: NOT transpilable (%d blocking constructs: %s)\n' % (
        path, len(seen), ', '.join(cats)))
    return 1
