# -*- coding: utf-8 -*-
"""スクリプトが使うコマンドの棚卸し(実行せずに AST から抽出する)。

    bashwin --inventory script.sh

監査・引き継ぎ・移行判断のための一覧: 定義している関数、シェル組み込み、
内蔵コマンド(アプレット)、外部コマンド(=実行環境に別途必要なもの)、
名前が実行時に決まる呼び出し(静的には追えないもの)。
"""
from __future__ import unicode_literals

import sys

from .nodes import (Lit, Esc, SQ, DQ, Param, CmdSub, Arith, ProcSub, ArrayLit, Simple, Pipeline,
                    AndOr, List, If, While, For, CFor, Case, Group, Subshell, FuncDef, Cond,
                    ArithCmd)
from .parser import parse, ParseError


class Inventory(object):
    def __init__(self):
        self.defined = set()
        self.used = {}          # name -> [lines]
        self.dynamic = []       # lines

    def word(self, w):
        if w is None:
            return
        for p in w.parts:
            self.part(p)

    def part(self, p):
        tp = type(p)
        if tp is DQ:
            for q in p.parts:
                self.part(q)
        elif tp is Param:
            self.word(p.arg)
            self.word(p.arg2)
            if p.index is not None and not isinstance(p.index, str):
                self.word(p.index)
        elif tp is CmdSub or tp is ProcSub:
            self.node(p.node)
        elif tp is Arith:
            self.word(p.word)

    def simple(self, n):
        for name, idx, append, value in n.assigns:
            if type(value) is ArrayLit:
                for k, w in value.elems:
                    self.word(k)
                    self.word(w)
            else:
                self.word(value)
        for r in n.redirs:
            self.word(r.target)
        for w in n.words:
            self.word(w)
            if w.assign is not None and type(w.assign[3]) is ArrayLit:
                for k, e in w.assign[3].elems:
                    self.word(e)
        if not n.words:
            return
        parts = n.words[0].parts
        if all(type(p) in (Lit, Esc, SQ) for p in parts):
            name = ''.join(p.text for p in parts)
            self.used.setdefault(name, []).append(n.line)
            # command / builtin / exec / xargs などの先にある本体コマンドも拾う
            if name in ('command', 'builtin', 'exec', 'env', 'timeout', 'xargs', 'time') \
                    and len(n.words) > 1:
                for w in n.words[1:]:
                    wp = w.parts
                    if all(type(p) in (Lit, Esc, SQ) for p in wp):
                        t = ''.join(p.text for p in wp)
                        if t.startswith('-') or '=' in t or t.replace('.', '').isdigit():
                            continue
                        self.used.setdefault(t, []).append(n.line)
                    break
        else:
            self.dynamic.append(n.line)

    def cond(self, e):
        for x in e[1:]:
            if isinstance(x, tuple):
                self.cond(x)
            elif hasattr(x, 'parts'):
                self.word(x)

    def node(self, n):
        tp = type(n)
        if tp is List:
            for item, is_async in n.items:
                self.node(item)
        elif tp is Simple:
            self.simple(n)
        elif tp is AndOr:
            self.node(n.first)
            for op, pl in n.rest:
                self.node(pl)
        elif tp is Pipeline:
            for c in n.cmds:
                self.node(c)
        elif tp is If:
            for c, b in n.clauses:
                self.node(c)
                self.node(b)
            if n.else_body is not None:
                self.node(n.else_body)
        elif tp is While:
            self.node(n.cond)
            self.node(n.body)
        elif tp is For:
            for w in (n.words or []):
                self.word(w)
            self.node(n.body)
        elif tp is CFor:
            self.node(n.body)
        elif tp is Case:
            self.word(n.word)
            for pats, body, term in n.items:
                self.node(body)
        elif tp is Group or tp is Subshell:
            self.node(n.body)
        elif tp is FuncDef:
            self.defined.add(n.name)
            self.node(n.body)
        elif tp is Cond:
            self.cond(n.expr)
        elif tp is ArithCmd:
            self.word(n.word)
        for r in (getattr(n, 'redirs', None) or []) if tp is not Simple else []:
            self.word(r.target)


def inventory_file(path):
    from . import applets, shbuiltins
    try:
        with open(path, 'rb') as f:
            src = f.read().decode('utf-8', 'surrogateescape')
    except (OSError, TypeError) as e:
        sys.stderr.write('bashwin: %s: %s\n' % (path, getattr(e, 'strerror', None) or e))
        return 2
    try:
        tree = parse(src)
    except ParseError as e:
        sys.stderr.write('%s: line %d: %s\n' % (path, e.line, e.msg))
        return 2
    inv = Inventory()
    inv.node(tree)
    groups = {'functions': [], 'builtins': [], 'applets': [], 'external': []}
    for name in sorted(inv.used):
        if name in inv.defined:
            groups['functions'].append(name)
        elif name in shbuiltins.BUILTINS:
            groups['builtins'].append(name)
        elif name in applets.REGISTRY:
            groups['applets'].append(name)
        else:
            groups['external'].append(name)
    out = sys.stdout.write
    out('script: %s\n' % path)
    out('functions (defined in script): %s\n' % (' '.join(groups['functions']) or '-'))
    out('shell builtins:               %s\n' % (' '.join(groups['builtins']) or '-'))
    out('bashwin applets:              %s\n' % (' '.join(groups['applets']) or '-'))
    out('external commands (must exist on the host):\n')
    if groups['external']:
        for name in groups['external']:
            lines = inv.used[name]
            out('  %-24s line %s\n' % (name, ', '.join(str(x) for x in lines[:8])
                                       + (' ...' if len(lines) > 8 else '')))
    else:
        out('  (none)\n')
    if inv.dynamic:
        out('dynamic command names (decided at run time): line %s\n'
            % ', '.join(str(x) for x in inv.dynamic[:20]))
    unused = sorted(inv.defined - set(inv.used))
    if unused:
        out('functions defined but never called by name: %s\n' % ' '.join(unused))
    return 0
