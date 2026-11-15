# -*- coding: utf-8 -*-
"""グロブパターン -> 正規表現 変換と、POSIX 正規表現(BRE/ERE) -> Python re 変換。

パターンは (文字, 引用済みか) の列で受け取る。引用済みの文字は常にリテラル。
"""
from __future__ import unicode_literals

import re

_CLASSES = {
    'alpha': 'a-zA-Z', 'digit': '0-9', 'alnum': 'a-zA-Z0-9', 'upper': 'A-Z', 'lower': 'a-z',
    'space': ' \\t\\n\\r\\f\\v', 'blank': ' \\t', 'xdigit': '0-9A-Fa-f', 'word': 'a-zA-Z0-9_',
    'cntrl': '\\x00-\\x1f\\x7f', 'print': '\\x20-\\x7e', 'graph': '\\x21-\\x7e',
    'punct': '!-/:-@\\[-`{-~',
}
_cache = {}


def segs_to_chars(segs):
    """[(text, quoted)] -> [(ch, quoted)]"""
    out = []
    for text, quoted in segs:
        for ch in text:
            out.append((ch, quoted))
    return out


def has_magic(chars):
    """グロブとして意味を持つか。閉じていない '[' はただの文字(例: test コマンドの `[`)。"""
    for i, (ch, q) in enumerate(chars):
        if q:
            continue
        if ch == '*' or ch == '?':
            return True
        if ch == '[' and _bracket(chars, i) is not None:
            return True
    return False


def _cls_escape(ch):
    if ch in '\\]^-[':
        return '\\' + ch
    return ch


def _bracket(chars, i):
    """chars[i] が無引用の '[' のとき、(正規表現, 次の位置) か None を返す。"""
    n = len(chars)
    j = i + 1
    neg = False
    if j < n and not chars[j][1] and chars[j][0] in '!^':
        neg = True
        j += 1
    members = []
    first = True
    while True:
        if j >= n:
            return None
        ch, q = chars[j]
        if ch == ']' and not q and not first:
            j += 1
            break
        first = False
        if ch == '[' and not q and j + 1 < n and chars[j + 1][0] == ':':
            k = j + 2
            name = []
            while k + 1 < n and not (chars[k][0] == ':' and chars[k + 1][0] == ']'):
                name.append(chars[k][0])
                k += 1
            nm = ''.join(name)
            if k + 1 < n and nm in _CLASSES:
                members.append(_CLASSES[nm])
                j = k + 2
                continue
        if ch == '\\' and not q and j + 1 < n:
            j += 1
            ch = chars[j][0]
        # 範囲 a-b
        if j + 2 < n and chars[j + 1][0] == '-' and not chars[j + 1][1] \
                and not (chars[j + 2][0] == ']' and not chars[j + 2][1]):
            hi = chars[j + 2][0]
            if hi == '\\' and not chars[j + 2][1] and j + 3 < n:
                hi = chars[j + 3][0]
                j += 1
            if ord(hi) >= ord(ch):
                members.append(_cls_escape(ch) + '-' + _cls_escape(hi))
            j += 3
            continue
        members.append(_cls_escape(ch))
        j += 1
    body = ''.join(members)
    if not body:
        return ('(?!)' if not neg else '.', j)
    return ('[' + ('^' if neg else '') + body + ']', j)


def chars_to_regex(chars, lazy=False):
    out = []
    i = 0
    n = len(chars)
    star = '.*?' if lazy else '.*'
    while i < n:
        ch, q = chars[i]
        if q:
            out.append(re.escape(ch))
            i += 1
        elif ch == '*':
            while i + 1 < n and chars[i + 1] == ('*', False):
                i += 1
            out.append(star)
            i += 1
        elif ch == '?':
            out.append('.')
            i += 1
        elif ch == '[':
            r = _bracket(chars, i)
            if r is None:
                out.append('\\[')
                i += 1
            else:
                out.append(r[0])
                i = r[1]
        elif ch == '\\' and i + 1 < n:
            out.append(re.escape(chars[i + 1][0]))
            i += 2
        else:
            out.append(re.escape(ch))
            i += 1
    return ''.join(out)


def compile_chars(chars, nocase=False, lazy=False):
    key = (tuple(chars), nocase, lazy)
    r = _cache.get(key)
    if r is None:
        flags = re.DOTALL | (re.IGNORECASE if nocase else 0)
        r = re.compile(chars_to_regex(chars, lazy), flags)
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = r
    return r


def match_segs(segs, string, nocase=False):
    """グロブパターン全体一致。"""
    return compile_chars(segs_to_chars(segs), nocase).fullmatch(string) is not None


def fnmatch(pattern, string, nocase=False):
    """無引用パターン文字列での全体一致(find -name 等)。"""
    return compile_chars([(c, False) for c in pattern], nocase).fullmatch(string) is not None


# ------------------------------------------------------------------ POSIX regex
_posix_cache = {}


def posix_to_py(pat, ere=False, end_anchor='$'):
    """POSIX BRE/ERE(GNU 拡張込み) を Python の re 構文に変換する。

    end_anchor: 行末アンカー '$' の置き換え先。sed は改行を含むパターンスペースを
    扱うため '\\Z' を渡す(Python の '$' は末尾改行の手前にも一致してしまう)。
    """
    out = []
    i = 0
    n = len(pat)
    while i < n:
        c = pat[i]
        if c == '\\' and i + 1 < n:
            d = pat[i + 1]
            i += 2
            if d in '<>':
                out.append('\\b')
            elif not ere and d in '(){}|+?':
                out.append(d)                      # BRE: \( \) \{ \} \| \+ \? は特殊
            elif d.isdigit() or d in 'wWsSbB':
                out.append('\\' + d)
            elif d == 'n':
                out.append('\\n')
            elif d == 't':
                out.append('\\t')
            elif d in 'rfv':
                out.append('\\' + d)
            else:
                out.append(re.escape(d))
        elif c == '[':
            j = i + 1
            neg = False
            if j < n and pat[j] == '^':
                neg = True
                j += 1
            members = []
            first = True
            ok = False
            while j < n:
                ch = pat[j]
                if ch == ']' and not first:
                    ok = True
                    j += 1
                    break
                first = False
                if ch == '[' and pat.startswith('[:', j):
                    k = pat.find(':]', j + 2)
                    if k > 0 and pat[j + 2:k] in _CLASSES:
                        members.append(_CLASSES[pat[j + 2:k]])
                        j = k + 2
                        continue
                if j + 2 < n and pat[j + 1] == '-' and pat[j + 2] != ']':
                    members.append(_cls_escape(ch) + '-' + _cls_escape(pat[j + 2]))
                    j += 3
                    continue
                members.append(_cls_escape(ch))
                j += 1
            if not ok:
                out.append('\\[')
                i += 1
            else:
                out.append('[' + ('^' if neg else '') + ''.join(members) + ']')
                i = j
        elif not ere and c in '(){}|+?':
            if c == '{' or c == '}':
                out.append('\\' + c)
            else:
                out.append('\\' + c)
            i += 1
        elif not ere and c == '*' and (not out or out[-1] in ('^', '(')):
            out.append('\\*')                      # BRE: 先頭の * はリテラル
            i += 1
        elif c == '^' and not ere and out and out[-1] != '(':
            out.append('\\^')
            i += 1
        elif c == '$' and not ere and i + 1 < n and not pat.startswith('\\)', i + 1):
            out.append('\\$')
            i += 1
        elif c == '{' and ere:
            m = re.compile(r'\{[0-9]*,?[0-9]*\}').match(pat, i)
            if m and m.group() != '{}' and m.group() != '{,}':
                out.append(m.group())
                i = m.end()
            else:
                out.append('\\{')
                i += 1
        elif c == '}' and ere:
            out.append('\\}')
            i += 1
        elif c == '$':
            out.append(end_anchor)
            i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def compile_posix(pat, ere=False, nocase=False, extra_flags=0):
    key = (pat, ere, nocase, extra_flags)
    r = _posix_cache.get(key)
    if r is None:
        flags = extra_flags | (re.IGNORECASE if nocase else 0)
        r = re.compile(posix_to_py(pat, ere), flags)
        if len(_posix_cache) > 500:
            _posix_cache.clear()
        _posix_cache[key] = r
    return r
