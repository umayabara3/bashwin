# -*- coding: utf-8 -*-
"""語の展開: ブレース -> チルダ -> パラメータ/コマンド/算術 -> 単語分割 -> パス名展開。

展開の途中結果は「フラグメント」(text, quoted, split) の列で持つ。
  quoted=True          : 引用済み。分割もグロブもしない
  quoted=False,split=F : 無引用リテラル。グロブ対象、IFS 分割はしない
  quoted=False,split=T : 無引用の展開結果。IFS 分割とグロブの対象
_SEP は "$@" などが作るフィールド境界。
"""
from __future__ import unicode_literals

import os
import re

from . import pattern
from .arith import ArithError
from .errors import ExpandError
from .nodes import Lit, Esc, SQ, DQ, Param, CmdSub, Arith, ProcSub, Word
from .parser import decode_ansi_c

_SEP = object()
_SEQ_NUM = re.compile(r'(-?[0-9]+)\.\.(-?[0-9]+)(?:\.\.(-?[0-9]+))?$')
_SEQ_CHR = re.compile(r'([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?[0-9]+))?$')
_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*$')
_NAME_IDX_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]$')
_SAFE_RE = re.compile(r'[A-Za-z0-9_@%+=:,./-]+$')


def _ansi_quote(s):
    out = ["$'"]
    for c in s:
        if c == '\n':
            out.append('\\n')
        elif c == '\t':
            out.append('\\t')
        elif c == '\r':
            out.append('\\r')
        elif c == "'" or c == '\\':
            out.append('\\' + c)
        elif ord(c) < 32 or ord(c) == 127:
            out.append('\\%03o' % ord(c))
        else:
            out.append(c)
    out.append("'")
    return ''.join(out)


def _has_ctrl(s):
    for c in s:
        if ord(c) < 32 or ord(c) == 127:
            return True
    return False


def shell_quote(s):
    """必要なときだけシングルクォートで囲む(set -x の表示など)。"""
    if s == '':
        return "''"
    if _SAFE_RE.match(s):
        return s
    if _has_ctrl(s):
        return _ansi_quote(s)
    return "'" + s.replace("'", "'\\''") + "'"


def quote_q(s):
    """${x@Q} 相当: 常にシングルクォートで囲む。"""
    if _has_ctrl(s):
        return _ansi_quote(s)
    return "'" + s.replace("'", "'\\''") + "'"


_BS_CHARS = frozenset(' \t!"#$&\'()*,;<>?[\\]^`{|}')


def quote_printf(s):
    """printf %q 相当: バックスラッシュでエスケープする。"""
    if s == '':
        return "''"
    if _has_ctrl(s):
        return _ansi_quote(s)
    out = []
    for k, c in enumerate(s):
        if c in _BS_CHARS or (c == '~' and k == 0):
            out.append('\\')
        out.append(c)
    return ''.join(out)


# ------------------------------------------------------------------ brace
def _sequence(text):
    m = _SEQ_NUM.match(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        step = abs(int(m.group(3))) if m.group(3) else 1
        if step == 0:
            step = 1
        width = 0
        for g in (m.group(1), m.group(2)):
            d = g.lstrip('-')
            if len(d) > 1 and d[0] == '0':
                width = max(width, len(g))
        rng = range(a, b + 1, step) if a <= b else range(a, b - 1, -step)
        if width:
            return [('-' + str(-v).zfill(width - 1)) if v < 0 else str(v).zfill(width) for v in rng]
        return [str(v) for v in rng]
    m = _SEQ_CHR.match(text)
    if m:
        a, b = ord(m.group(1)), ord(m.group(2))
        step = abs(int(m.group(3))) if m.group(3) else 1
        if step == 0:
            step = 1
        rng = range(a, b + 1, step) if a <= b else range(a, b - 1, -step)
        return [chr(v) for v in rng]
    return None


def _brace(items):
    n = len(items)
    i = 0
    while i < n:
        if items[i] == '{':
            depth = 0
            commas = []
            close = -1
            j = i + 1
            while j < n:
                it = items[j]
                if it == '{':
                    depth += 1
                elif it == '}':
                    if depth == 0:
                        close = j
                        break
                    depth -= 1
                elif it == ',' and depth == 0:
                    commas.append(j)
                j += 1
            if close >= 0:
                alts = None
                if commas:
                    alts = []
                    start = i + 1
                    for cpos in commas + [close]:
                        alts.append(items[start:cpos])
                        start = cpos + 1
                else:
                    inner = items[i + 1:close]
                    if inner and all(isinstance(x, str) for x in inner):
                        seq = _sequence(''.join(inner))
                        if seq is not None:
                            alts = [list(x) for x in seq]
                if alts is not None:
                    prefix = items[:i]
                    suffixes = _brace(items[close + 1:])
                    out = []
                    for alt in alts:
                        for a in _brace(alt):
                            for sfx in suffixes:
                                out.append(prefix + a + sfx)
                    return out
        i += 1
    return [items]


def brace_expand(word):
    """Word -> [Word]。無引用リテラル中の {a,b} / {1..5} を展開する。"""
    items = []
    for p in word.parts:
        if type(p) is Lit:
            items.extend(p.text)
        else:
            items.append(p)
    results = _brace(items)
    if len(results) == 1:
        return [word]
    out = []
    for r in results:
        parts = []
        buf = []
        for it in r:
            if isinstance(it, str):
                buf.append(it)
            else:
                if buf:
                    parts.append(Lit(''.join(buf)))
                    buf = []
                parts.append(it)
        if buf:
            parts.append(Lit(''.join(buf)))
        out.append(Word(parts))
    return out


# ------------------------------------------------------------------ helpers
def _ifs_tokens(text, ws, nw):
    """(0, 文字列) と (1, hard) を順に返す。hard=非空白区切り文字を含む区切り。"""
    i = 0
    n = len(text)
    start = 0
    while i < n:
        c = text[i]
        if c in ws or c in nw:
            if i > start:
                yield (0, text[start:i])
            hard = False
            while i < n and text[i] in ws:
                i += 1
            if i < n and text[i] in nw:
                hard = True
                i += 1
                while i < n and text[i] in ws:
                    i += 1
            yield (1, hard)
            start = i
        else:
            i += 1
    if n > start:
        yield (0, text[start:n])


def _strip(s, chars, op):
    n = len(s)
    if not pattern.has_magic(chars) and not any(c == '\\' and not q for c, q in chars):
        lit = ''.join(c for c, q in chars)
        if op[0] == '#':
            return s[len(lit):] if s.startswith(lit) else s
        return s[:n - len(lit)] if lit and s.endswith(lit) else s
    rx = pattern.compile_chars(chars)
    if op == '#':
        rng = range(0, n + 1)
    elif op == '##':
        rng = range(n, -1, -1)
    elif op == '%':
        rng = range(n, -1, -1)
    else:
        rng = range(0, n + 1)
    if op[0] == '#':
        for i in rng:
            if rx.fullmatch(s, 0, i):
                return s[i:]
    else:
        for i in rng:
            if rx.fullmatch(s, i):
                return s[:i]
    return s


def _replace(s, chars, repfn, op):
    if not chars:
        if op == '/#':
            return repfn('') + s
        if op == '/%':
            return s + repfn('')
        return s
    rx = re.compile(pattern.chars_to_regex(chars), re.DOTALL)
    n = len(s)
    if op == '/#':
        m = rx.match(s)
        return repfn(m.group()) + s[m.end():] if m else s
    if op == '/%':
        for i in range(0, n + 1):
            if rx.fullmatch(s, i):
                return s[:i] + repfn(s[i:])
        return s
    if op == '//':
        out = []
        pos = 0
        while pos <= n:
            m = rx.search(s, pos)
            if not m:
                break
            if m.end() == m.start():
                if m.start() >= n:
                    break
                out.append(s[pos:m.start() + 1])
                pos = m.start() + 1
                continue
            out.append(s[pos:m.start()])
            out.append(repfn(m.group()))
            pos = m.end()
        out.append(s[pos:])
        return ''.join(out)
    m = rx.search(s)
    if m and m.end() > m.start():
        return s[:m.start()] + repfn(m.group()) + s[m.end():]
    return s


def _substr(s, off, ln):
    n = len(s)
    if off < 0:
        off = n + off
        if off < 0:
            return ''
    if ln is None:
        return s[off:]
    if ln < 0:
        end = n + ln
        if end < off:
            raise ExpandError('%s: substring expression < 0' % ln)
        return s[off:end]
    return s[off:off + ln]


def _join(prefix, name):
    if not prefix:
        return name
    if prefix.endswith('/'):
        return prefix + name
    return prefix + '/' + name


class ExpandMixin(object):
    """Interp に混ぜ込む展開処理。self.getvar などは Interp 側が提供する。"""

    # ------------------------------------------------------------ public
    def expand_words(self, words):
        out = []
        for w in words:
            parts = w.parts
            if len(parts) == 1 and type(parts[0]) is Lit:
                t = parts[0].text
                if not ('{' in t or '*' in t or '?' in t or '[' in t or t[0] == '~'):
                    out.append(t)
                    continue
            self._expand_word(w, out)
        return out

    def _expand_word(self, w, out):
        words = (w,)
        for p in w.parts:
            if type(p) is Lit and '{' in p.text:
                words = brace_expand(w)
                break
        for bw in words:
            frags = self._expand_parts(bw.parts, False)
            for field in self._split_fields(frags):
                self._glob_field(field, out)

    def expand_str(self, w, assign=False):
        """分割・グロブなしで 1 つの文字列に展開する(代入の右辺、case の語など)。"""
        parts = w.parts
        if len(parts) == 1:
            p = parts[0]
            tp = type(p)
            if tp is SQ or (tp is Lit and '~' not in p.text):
                return p.text
        elif not parts:
            return ''
        frags = self._expand_parts(parts, False, assign=assign, nosplit=True)
        return ''.join([' ' if f is _SEP else f[0] for f in frags])

    def expand_pattern(self, w):
        """パターン用: [(text, quoted)] を返す。引用部分はリテラル扱い。"""
        frags = self._expand_parts(w.parts, False, nosplit=True)
        return [(' ', False) if f is _SEP else (f[0], f[1]) for f in frags]

    def expand_regex(self, w):
        """[[ x =~ re ]] 用。無引用部分は ERE、引用部分はリテラル。"""
        out = []
        for text, quoted in self.expand_pattern(w):
            out.append(re.escape(text) if quoted else pattern.posix_to_py(text, ere=True))
        return ''.join(out)

    def arith_word(self, w):
        text = self.expand_str(w) if isinstance(w, Word) else w
        try:
            return self.arith.eval_text(text)
        except ArithError as e:
            raise ExpandError('%s: %s' % (text.strip(), e))
        except RecursionError:
            raise ExpandError('%s: expression recursion level exceeded' % text.strip())

    # ------------------------------------------------------------ parts
    def _tilde_one(self, seg):
        if not seg.startswith('~'):
            return None
        k = seg.find('/')
        prefix = seg if k < 0 else seg[:k]
        rest = '' if k < 0 else seg[k:]
        if prefix == '~':
            home = self.getvar('HOME')
            if home is None:
                home = os.path.expanduser('~')
        elif prefix == '~+':
            home = self.getvar('PWD') or self.cwd
        elif prefix == '~-':
            home = self.getvar('OLDPWD')
            if home is None:
                return None
        else:
            home = os.path.expanduser(prefix)
            if home == prefix:
                return None
        return home, rest

    def _tilde(self, text, assign, at_start):
        """チルダ展開。代入の右辺では ':' の直後も対象。展開しなければ None。"""
        if not assign:
            r = self._tilde_one(text) if at_start else None
            if r is None:
                return None
            return [(r[0], True, False), (r[1], False, False)]
        out = []
        changed = False
        for k, seg in enumerate(text.split(':')):
            if k:
                out.append((':', False, False))
            r = self._tilde_one(seg) if (k > 0 or at_start) else None
            if r is None:
                out.append((seg, False, False))
            else:
                changed = True
                out.append((r[0], True, False))
                out.append((r[1], False, False))
        return out if changed else None

    def _expand_parts(self, parts, quoted, assign=False, nosplit=False):
        out = []
        last = len(parts) - 1
        for idx, p in enumerate(parts):
            tp = type(p)
            if tp is Lit:
                text = p.text
                if not quoted and '~' in text and (idx == 0 or assign) \
                        and not (text == '~' and idx < last):
                    # '~' 単独で後ろに別のパーツが続く場合は展開しない(~"$x" など)
                    fr = self._tilde(text, assign, idx == 0)
                    if fr is not None:
                        out.extend(fr)
                        continue
                out.append((text, quoted, False))
            elif tp is Esc or tp is SQ:
                out.append((p.text, True, False))
            elif tp is DQ:
                if not p.parts:
                    out.append(('', True, False))
                else:
                    out.extend(self._expand_parts(p.parts, True, nosplit=nosplit))
            elif tp is Param:
                out.extend(self._expand_param(p, quoted, nosplit))
            elif tp is CmdSub:
                out.append((self.command_subst(p.node), quoted, not quoted))
            elif tp is Arith:
                out.append((str(self.arith_word(p.word)), quoted, not quoted))
            elif tp is ProcSub:
                out.append((self.process_subst(p), True, False))
        return out

    # ------------------------------------------------------------ fields
    def _split_fields(self, frags):
        ifs = self.getvar('IFS')
        if ifs is None:
            ifs = ' \t\n'
        ws = ''.join(c for c in ifs if c in ' \t\n')
        nw = ''.join(c for c in ifs if c not in ' \t\n')
        fields = []
        cur = None
        for f in frags:
            if f is _SEP:
                if cur is not None:
                    fields.append(cur)
                    cur = None
                continue
            text, quoted, split = f
            if not split:
                if cur is None:
                    cur = []
                cur.append((text, quoted))
                continue
            if not text:
                continue
            if not ifs:
                if cur is None:
                    cur = []
                cur.append((text, False))
                continue
            for kind, val in _ifs_tokens(text, ws, nw):
                if kind == 0:
                    if cur is None:
                        cur = []
                    cur.append((val, False))
                elif cur is not None:
                    fields.append(cur)
                    cur = None
                elif val:
                    fields.append([])
        if cur is not None:
            fields.append(cur)
        return fields

    def _glob_field(self, field, out):
        if not self.opts['noglob']:
            for text, quoted in field:
                if not quoted and ('*' in text or '?' in text or '[' in text):
                    if not pattern.has_magic(pattern.segs_to_chars(field)):
                        break       # 閉じていない '[' などはパターンではない
                    matches = self.glob_expand(field)
                    if matches:
                        out.extend(matches)
                        return
                    if self.shopts.get('nullglob'):
                        return
                    break
        out.append(''.join([t for t, q in field]))

    def glob_expand(self, field):
        chars = pattern.segs_to_chars(field)
        comps = [[]]
        for ch, q in chars:
            if ch == '/':
                comps.append([])
            else:
                comps[-1].append((ch, q))
        results = ['']
        n = len(comps)
        nocase = bool(self.shopts.get('nocaseglob'))
        dotglob = bool(self.shopts.get('dotglob'))
        for idx, comp in enumerate(comps):
            last = idx == n - 1
            if not comp:
                if idx == 0:
                    results = ['/']
                elif last:
                    results = [r if r.endswith('/') else r + '/' for r in results
                               if os.path.isdir(self.abspath(r))]
                continue
            new = []
            if not pattern.has_magic(comp):
                lit = ''.join([c for c, q in comp])
                for r in results:
                    new.append(_join(r, lit))
                if last:
                    new = [x for x in new if os.path.lexists(self.abspath(x))]
            else:
                rx = pattern.compile_chars(comp, nocase)
                show_dot = comp[0][0] == '.' or dotglob
                for r in results:
                    d = self.abspath(r) if r else self.cwd
                    try:
                        names = os.listdir(d)
                    except OSError:
                        continue
                    for name in names:
                        if name[0] == '.' and not show_dot:
                            continue
                        if rx.fullmatch(name):
                            cand = _join(r, name)
                            if not last and not os.path.isdir(self.abspath(cand)):
                                continue
                            new.append(cand)
            results = new
            if not results:
                return []
        results.sort()
        return results

    # ------------------------------------------------------------ parameters
    def _ifs_first(self):
        ifs = self.getvar('IFS')
        if ifs is None:
            return ' '
        return ifs[:1]

    def _value_frags(self, val, islist, star, quoted, nosplit):
        if not islist:
            return [(val, quoted, not quoted)]
        if nosplit:
            sep = self._ifs_first() if star else ' '
            return [(sep.join(val), quoted, False)]
        out = []
        if quoted:
            if star:
                return [(self._ifs_first().join(val), True, False)]
            for k, v in enumerate(val):
                if k:
                    out.append(_SEP)
                out.append((v, True, False))
            return out
        for k, v in enumerate(val):
            if k:
                out.append(_SEP)
            out.append((v, False, True))
        return out

    def _word_frags(self, w, quoted, nosplit):
        """${x:-word} の word 部分。無引用の文脈ではリテラルも単語分割の対象になる。"""
        frags = self._expand_parts(w.parts, quoted, nosplit=nosplit)
        if quoted:
            # "${x:-}" は空でも 1 フィールド(空文字列)になる
            return frags if frags else [('', True, False)]
        if nosplit:
            return frags
        return [f if (f is _SEP or f[1]) else (f[0], False, True) for f in frags]

    def _scalar_param(self, p):
        name = p.name
        c = name[0]
        if c.isdigit():
            k = int(name)
            if k == 0:
                return self.argv0
            return self.pos[k - 1] if k <= len(self.pos) else None
        if c == '#':
            return str(len(self.pos))
        if c == '?':
            return str(self.last_status)
        if c == '$':
            return str(self.root.pid)
        if c == '!':
            return self.last_bg
        if c == '-':
            return self.option_flags()
        if p.index is None:
            return self.getvar(name)
        return self.get_elem(name, p.index)

    def _indirect(self, target):
        if target is None or target == '':
            return None
        if target.isdigit():
            k = int(target)
            if k == 0:
                return self.argv0
            return self.pos[k - 1] if k <= len(self.pos) else None
        if _NAME_RE.match(target):
            return self.getvar(target)
        m = _NAME_IDX_RE.match(target)
        if m:
            from .parser import Parser
            return self.get_elem(m.group(1), Parser(m.group(2)).parse_word_all())
        raise ExpandError('%s: invalid variable name' % target)

    def _expand_param(self, p, quoted, nosplit=False):
        name = p.name
        op = p.op
        if op == 'prefix':
            names = sorted(n for n in self.all_var_names() if n.startswith(name))
            return self._value_frags(names, True, False, quoted, nosplit)
        islist = False
        star = False
        if name == '@' or name == '*':
            val = list(self.pos)
            islist = True
            star = name == '*'
        elif p.index == '@' or p.index == '*':
            val = self.array_keys(name) if p.indirect else self.array_values(name)
            islist = True
            star = p.index == '*'
        else:
            val = self._scalar_param(p)
            if p.indirect:
                val = self._indirect(val)

        if p.length:
            if islist:
                return [(str(len(val)), quoted, not quoted)]
            if val is None:
                if self.opts['nounset'] and name not in '@*':
                    raise ExpandError('%s: unbound variable' % name, fatal=True)
                val = ''
            return [(str(len(val)), quoted, not quoted)]

        if islist:
            unset = len(val) == 0
            null = unset or (len(val) == 1 and val[0] == '')
        else:
            unset = val is None
            null = unset or val == ''

        if op is not None:
            o = op[-1] if op in (':-', '-', ':=', '=', ':?', '?', ':+', '+') else None
            if o is not None:
                cond = null if op[0] == ':' else unset
                if o == '-':
                    if cond:
                        return self._word_frags(p.arg, quoted, nosplit)
                elif o == '=':
                    if cond:
                        v = self.expand_str(p.arg)
                        if not _NAME_RE.match(name):
                            raise ExpandError('$%s: cannot assign in this way' % name)
                        if p.index is not None and p.index not in ('@', '*'):
                            self.set_elem(name, p.index, v)
                        else:
                            self.setvar(name, v)
                        val = v
                        islist = False
                elif o == '?':
                    if cond:
                        msg = self.expand_str(p.arg) if p.arg.parts else \
                            ('parameter null or not set' if op[0] == ':' else 'parameter not set')
                        raise ExpandError('%s: %s' % (name, msg), fatal=True)
                else:  # '+'
                    if not cond:
                        return self._word_frags(p.arg, quoted, nosplit)
                    return [('', True, False)] if quoted and not islist else []
                op = None

        if not islist and val is None:
            if self.opts['nounset'] and p.op is None and name not in '@*':
                raise ExpandError('%s: unbound variable' % name, fatal=True)
            val = ''

        if op is not None:
            fn = None
            if op in ('#', '##', '%', '%%'):
                chars = pattern.segs_to_chars(self.expand_pattern(p.arg))
                fn = lambda s: _strip(s, chars, op)
            elif op[0] == '/':
                chars = pattern.segs_to_chars(self.expand_pattern(p.arg))
                rsegs = self.expand_pattern(p.arg2) if p.arg2 is not None else []
                if any((not q) and '&' in t for t, q in rsegs):
                    repfn = lambda m: ''.join(t if q else t.replace('&', m) for t, q in rsegs)
                else:
                    rep = ''.join(t for t, q in rsegs)
                    repfn = lambda m: rep
                fn = lambda s: _replace(s, chars, repfn, op)
            elif op in ('^', '^^', ',', ',,'):
                if op == '^':
                    fn = lambda s: s[:1].upper() + s[1:]
                elif op == '^^':
                    fn = lambda s: s.upper()
                elif op == ',':
                    fn = lambda s: s[:1].lower() + s[1:]
                else:
                    fn = lambda s: s.lower()
            elif op == 'substr':
                off = self.arith_word(p.arg)
                ln = self.arith_word(p.arg2) if p.arg2 is not None else None
                if islist:
                    base = ([self.argv0] + val) if name in '@*' else val
                    n = len(base)
                    if off < 0:
                        off = max(n + off, 0) if name not in '@*' else n + off
                        if off < 0:
                            off = n
                    if ln is None:
                        val = base[off:]
                    elif ln < 0:
                        raise ExpandError('%s: substring expression < 0' % ln)
                    else:
                        val = base[off:off + ln]
                else:
                    fn = lambda s: _substr(s, off, ln)
            elif op[0] == '@':
                k = op[1]
                if k == 'Q':
                    fn = quote_q
                elif k == 'U':
                    fn = lambda s: s.upper()
                elif k == 'L':
                    fn = lambda s: s.lower()
                elif k == 'u':
                    fn = lambda s: s[:1].upper() + s[1:]
                elif k == 'E':
                    fn = decode_ansi_c
                else:
                    fn = lambda s: s
            if fn is not None:
                val = [fn(v) for v in val] if islist else fn(val)
        return self._value_frags(val, islist, star, quoted, nosplit)
