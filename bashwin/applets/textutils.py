# -*- coding: utf-8 -*-
"""テキスト処理アプレット: cat head tail wc sort uniq cut tr tee grep rev tac nl paste
seq yes base64 dos2unix unix2dos iconv md5sum/sha*sum diff cmp expr"""
from __future__ import unicode_literals

import base64 as _b64
import codecs
import difflib
import functools
import hashlib
import os
import re
import stat

from .. import pattern
from .common import (applet, getopt, Out, UsageError, open_inputs, iter_chunks, iter_lines,
                     read_text, split_lines, to_int)


@applet
def a_cat(sh, argv):
    opts, files = getopt(argv[1:], 'nbsAEevTu', {'number': 'n'})
    o = dict(opts)
    errs = []
    if 'n' in o or 'b' in o:
        out = Out(sh)
        num = 0
        for name, f in open_inputs(sh, 'cat', files, errs):
            for line, nl in iter_lines(sh, f, out):
                if 'b' in o and line == '':
                    out.write('\n')
                    continue
                num += 1
                out.write('%6d\t%s%s' % (num, line, '\n' if nl else ''))
        out.flush()
        return 1 if errs else 0
    for name, f in open_inputs(sh, 'cat', files, errs):
        for chunk in iter_chunks(f):
            sh.out_bytes(chunk)
    return 1 if errs else 0


def _count_arg(args):
    """head/tail の -5 / +5 形式を -n に正規化する(-n/-c の値はそのまま)。"""
    out = []
    skip = False
    for a in args:
        if skip:
            out.append(a)
            skip = False
        elif a in ('-n', '-c', '--lines', '--bytes'):
            out.append(a)
            skip = True
        elif re.match(r'-[0-9]+$', a):
            out.extend(['-n', a[1:]])
        elif re.match(r'\+[0-9]+$', a):
            out.extend(['-n', a])
        else:
            out.append(a)
    return out


@applet
def a_head(sh, argv):
    opts, files = getopt(_count_arg(argv[1:]), 'n:c:qv',
                         {'lines': 'n', 'bytes': 'c', 'quiet': 'q', 'verbose': 'v'})
    o = dict(opts)
    errs = []
    show = ('v' in o or len(files) > 1) and 'q' not in o
    first = True
    for name, f in open_inputs(sh, 'head', files, errs):
        if show:
            sh.out('%s==> %s <==\n' % ('' if first else '\n',
                                       'standard input' if name == '-' else name))
        first = False
        if 'c' in o:
            n = to_int(o['c'])
            data = b''.join(iter_chunks(f)) if n < 0 else b''
            if n < 0:
                sh.out_bytes(data[:n])
            else:
                left = n
                while left > 0:
                    b = f.read(min(left, 65536))
                    if not b:
                        break
                    sh.out_bytes(b)
                    left -= len(b)
            continue
        spec = o.get('n', '10')
        n = to_int(spec)
        if spec.startswith('-'):
            lines = [(l, nl) for l, nl in iter_lines(sh, f)]
            lines = lines[:n] if n else lines
            sh.out(''.join(l + ('\n' if nl else '') for l, nl in lines))
            continue
        if n == 0:
            continue
        out = Out(sh)
        k = 0
        for line, nl in iter_lines(sh, f, out):
            out.write(line + ('\n' if nl else ''))
            k += 1
            if k >= n:
                break
        out.flush()
    return 1 if errs else 0


@applet
def a_tail(sh, argv):
    opts, files = getopt(_count_arg(argv[1:]), 'n:c:qvfF',
                         {'lines': 'n', 'bytes': 'c', 'quiet': 'q', 'verbose': 'v'})
    o = dict(opts)
    if 'f' in o or 'F' in o:
        raise UsageError('-f is not supported by bashwin')
    errs = []
    show = ('v' in o or len(files) > 1) and 'q' not in o
    first = True
    for name, f in open_inputs(sh, 'tail', files, errs):
        if show:
            sh.out('%s==> %s <==\n' % ('' if first else '\n',
                                       'standard input' if name == '-' else name))
        first = False
        data = b''.join(iter_chunks(f))
        if 'c' in o:
            spec = o['c']
            n = to_int(spec)
            sh.out_bytes(data[n - 1:] if spec.startswith('+') else (data[-n:] if n else b''))
            continue
        spec = o.get('n', '10')
        n = abs(to_int(spec))
        lines = data.split(b'\n')
        tail_nl = lines and lines[-1] == b''
        if tail_nl:
            lines.pop()
        sel = lines[max(n - 1, 0):] if spec.startswith('+') else (lines[-n:] if n else [])
        if sel:
            sh.out_bytes(b'\n'.join(sel) + (b'\n' if tail_nl else b''))
    return 1 if errs else 0


@applet
def a_wc(sh, argv):
    opts, files = getopt(argv[1:], 'lwcmL', {'lines': 'l', 'words': 'w', 'bytes': 'c',
                                               'chars': 'm', 'max-line-length': 'L'})
    o = dict(opts)
    cols = [c for c in 'lwmcL' if c in o] or ['l', 'w', 'c']
    errs = []
    rows = []
    total_regular = 0
    min_width = 1
    for name, f in open_inputs(sh, 'wc', files, errs):
        try:
            st = os.fstat(f.fileno())
            if stat.S_ISREG(st.st_mode):
                total_regular += st.st_size
            else:
                min_width = 7
        except (OSError, ValueError, AttributeError):
            min_width = 7
        data = b''.join(iter_chunks(f))
        vals = {}
        vals['l'] = data.count(b'\n')
        vals['c'] = len(data)
        if 'w' in cols:
            vals['w'] = len(data.split())
        if 'm' in cols or 'L' in cols:
            text = sh.dec(data)
            vals['m'] = len(text)
            vals['L'] = max([len(x) for x in text.split('\n')] or [0])
        rows.append((name, vals))
    if not rows:
        return 1
    width = len(str(total_regular)) if total_regular >= 10 else 1
    width = max(width, min_width)
    if len(rows) == 1 and len(cols) == 1 and not errs:
        width = 1
    out = []
    if len(rows) > 1:
        tot = dict((c, 0) for c in cols)
        for name, vals in rows:
            for c in cols:
                tot[c] = max(tot[c], vals[c]) if c == 'L' else tot[c] + vals[c]
        rows.append(('total', tot))
    for name, vals in rows:
        line = ' '.join(str(vals[c]).rjust(width) for c in cols)
        if not (name == '-' and not files):
            line += ' ' + name
        out.append(line + '\n')
    sh.out(''.join(out))
    return 1 if errs else 0


# ------------------------------------------------------------------ sort
class _Key(object):
    __slots__ = ('f1', 'c1', 'f2', 'c2', 'n', 'r', 'f', 'b', 'own')


_KEY_RE = re.compile(r'([0-9]+)(?:\.([0-9]+))?([a-zA-Z]*)(?:,([0-9]+)(?:\.([0-9]+))?([a-zA-Z]*))?$')
_NUM_RE = re.compile(r'[ \t]*(-?[0-9]*\.?[0-9]*)')


def _spans(line, sep):
    spans = []
    if sep is not None:
        start = 0
        while True:
            k = line.find(sep, start)
            if k < 0:
                spans.append((start, len(line)))
                return spans
            spans.append((start, k))
            start = k + 1
    i = 0
    n = len(line)
    while i < n:
        start = i
        while i < n and line[i] in ' \t':
            i += 1
        while i < n and line[i] not in ' \t':
            i += 1
        spans.append((start, i))
    return spans


def _numval(s):
    m = _NUM_RE.match(s)
    t = m.group(1)
    if t in ('', '-', '.', '-.'):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def _keytext(line, k, sep):
    if k.f1 is None:
        text = line
        if k.b:
            text = text.lstrip(' \t')
    else:
        spans = _spans(line, sep)
        n = len(line)
        if k.f1 - 1 >= len(spans):
            start = n
        else:
            s, e = spans[k.f1 - 1]
            if k.b:
                while s < e and line[s] in ' \t':
                    s += 1
            start = min(s + (k.c1 - 1 if k.c1 else 0), n)
        if k.f2 is None:
            end = n
        elif k.f2 - 1 >= len(spans):
            end = n
        else:
            s, e = spans[k.f2 - 1]
            end = min(s + k.c2, n) if k.c2 else e
        text = line[start:end] if end > start else ''
    if k.n:
        return _numval(text)
    if k.f:
        return text.upper()
    return text


@applet(usage=2)
def a_sort(sh, argv):
    opts, files = getopt(argv[1:], 'rnufbsk:t:o:cCzmdig',
                         {'reverse': 'r', 'numeric-sort': 'n', 'unique': 'u',
                          'ignore-case': 'f', 'key': 'k', 'field-separator': 't',
                          'output': 'o', 'stable': 's', 'ignore-leading-blanks': 'b'})
    g = set(c for c, v in opts if v is True)
    sep = None
    outfile = None
    keys = []
    for c, v in opts:
        if c == 't':
            sep = '\0' if v == '\\0' else v
        elif c == 'o':
            outfile = v
        elif c == 'k':
            m = _KEY_RE.match(v)
            if not m:
                raise UsageError("invalid key specification '%s'" % v)
            k = _Key()
            k.f1 = int(m.group(1))
            k.c1 = int(m.group(2)) if m.group(2) else 0
            k.f2 = int(m.group(4)) if m.group(4) else None
            k.c2 = int(m.group(5)) if m.group(5) else 0
            o = (m.group(3) or '') + (m.group(6) or '')
            k.own = bool(o)
            k.n = 'n' in o or 'g' in o
            k.r = 'r' in o
            k.f = 'f' in o
            k.b = 'b' in o
            if k.f1 < 1:
                raise UsageError("field number is zero: invalid field specification '%s'" % v)
            keys.append(k)
    for k in keys:
        if not k.own:
            k.n = 'n' in g or 'g' in g
            k.r = 'r' in g
            k.f = 'f' in g
            k.b = 'b' in g
    if not keys:
        k = _Key()
        k.f1 = k.f2 = None
        k.c1 = k.c2 = 0
        k.n = 'n' in g or 'g' in g
        k.r = 'r' in g
        k.f = 'f' in g
        k.b = 'b' in g
        k.own = False
        keys.append(k)
    errs = []
    lines = split_lines(read_text(sh, 'sort', files, errs))
    rows = [([_keytext(l, k, sep) for k in keys], l) for l in lines]
    grev = 'r' in g
    last_resort = not ('s' in g or 'u' in g)
    simple = len(keys) == 1 and keys[0].f1 is None and not keys[0].n and not keys[0].f \
        and not keys[0].b

    def cmp(a, b):
        ka, kb = a[0], b[0]
        for i, k in enumerate(keys):
            x, y = ka[i], kb[i]
            if x != y:
                r = -1 if x < y else 1
                return -r if k.r else r
        if not last_resort:
            return 0
        x, y = a[1], b[1]
        if x == y:
            return 0
        r = -1 if x < y else 1
        return -r if grev else r

    if 'c' in g or 'C' in g:
        for i in range(1, len(rows)):
            c = cmp(rows[i - 1], rows[i])
            if c > 0 or (c == 0 and 'u' in g):
                if 'c' in g:
                    sh.err('sort: -:%d: disorder: %s\n' % (i + 1, rows[i][1]))
                return 1
        return 0
    if simple:
        rows.sort(key=lambda r: r[1], reverse=grev)
    else:
        rows.sort(key=functools.cmp_to_key(cmp))
    if 'u' in g:
        uniq = []
        for r in rows:
            if not uniq or uniq[-1][0] != r[0]:
                uniq.append(r)
        rows = uniq
    data = sh.enc(''.join(r[1] + '\n' for r in rows))
    if outfile:
        with open(sh.abspath(outfile), 'wb') as f:
            f.write(data)
    else:
        sh.out_bytes(data)
    return 2 if errs else 0


@applet
def a_uniq(sh, argv):
    opts, files = getopt(argv[1:], 'cdui', {'count': 'c', 'repeated': 'd', 'unique': 'u',
                                             'ignore-case': 'i'})
    o = dict(opts)
    errs = []
    lines = split_lines(read_text(sh, 'uniq', files[:1], errs))
    out = []
    i = 0
    n = len(lines)
    fold = (lambda s: s.lower()) if 'i' in o else (lambda s: s)
    while i < n:
        j = i + 1
        k = fold(lines[i])
        while j < n and fold(lines[j]) == k:
            j += 1
        cnt = j - i
        if ('d' in o and cnt < 2) or ('u' in o and cnt > 1):
            i = j
            continue
        out.append(('%7d %s\n' % (cnt, lines[i])) if 'c' in o else lines[i] + '\n')
        i = j
    data = sh.enc(''.join(out))
    if len(files) > 1:
        with open(sh.abspath(files[1]), 'wb') as f:
            f.write(data)
    else:
        sh.out_bytes(data)
    return 1 if errs else 0


def _parse_list(spec):
    ranges = []
    for part in spec.split(','):
        m = re.match(r'([0-9]*)(-?)([0-9]*)$', part)
        if not m or part in ('', '-'):
            raise UsageError("invalid field value '%s'" % part)
        a, dash, b = m.groups()
        lo = int(a) if a else 1
        hi = (int(b) if b else None) if dash else lo
        if lo < 1:
            raise UsageError('fields are numbered from 1')
        ranges.append((lo, hi))
    return ranges


def _selected(ranges, n):
    idx = set()
    for lo, hi in ranges:
        for k in range(lo, (n if hi is None else min(hi, n)) + 1):
            idx.add(k)
    return sorted(idx)


@applet
def a_cut(sh, argv):
    opts, files = getopt(argv[1:], 'd:f:c:b:sn', {'delimiter': 'd', 'fields': 'f',
                                                    'characters': 'c', 'bytes': 'b',
                                                    'only-delimited': 's'})
    o = dict(opts)
    errs = []
    out = Out(sh)
    if 'f' in o:
        ranges = _parse_list(o['f'])
        d = o.get('d', '\t')
        if len(d) != 1:
            raise UsageError('the delimiter must be a single character')
        for name, f in open_inputs(sh, 'cut', files, errs):
            for line, nl in iter_lines(sh, f, out):
                if d not in line:
                    if 's' not in o:
                        out.write(line + '\n')
                    continue
                parts = line.split(d)
                out.write(d.join(parts[k - 1] for k in _selected(ranges, len(parts))) + '\n')
    elif 'c' in o or 'b' in o:
        ranges = _parse_list(o.get('c') or o.get('b'))
        for name, f in open_inputs(sh, 'cut', files, errs):
            for line, nl in iter_lines(sh, f, out):
                out.write(''.join(line[k - 1] for k in _selected(ranges, len(line))) + '\n')
    else:
        raise UsageError('you must specify a list of bytes, characters, or fields')
    out.flush()
    return 1 if errs else 0


_TR_ESC = {'n': '\n', 't': '\t', 'r': '\r', 'a': '\a', 'b': '\b', 'f': '\f', 'v': '\v',
           '\\': '\\'}
_TR_CLASS = {
    'alpha': 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
    'upper': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'lower': 'abcdefghijklmnopqrstuvwxyz',
    'digit': '0123456789', 'space': '\t\n\v\f\r ', 'blank': '\t ',
    'xdigit': '0123456789ABCDEFabcdef',
    'punct': '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~',
}
_TR_CLASS['alnum'] = _TR_CLASS['digit'] + _TR_CLASS['alpha']
_TR_CLASS['cntrl'] = ''.join(chr(c) for c in list(range(32)) + [127])
_TR_CLASS['print'] = ''.join(chr(c) for c in range(32, 127))
_TR_CLASS['graph'] = ''.join(chr(c) for c in range(33, 127))


def _tr_set(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '[' and s.startswith('[:', i):
            k = s.find(':]', i + 2)
            if k > 0 and s[i + 2:k] in _TR_CLASS:
                out.extend(_TR_CLASS[s[i + 2:k]])
                i = k + 2
                continue
        if c == '\\' and i + 1 < n:
            d = s[i + 1]
            m = re.compile(r'[0-7]{1,3}').match(s, i + 1)
            if m:
                c = chr(int(m.group(), 8))
                i = m.end()
            else:
                c = _TR_ESC.get(d, d)
                i += 2
        else:
            i += 1
        if i + 1 < n and s[i] == '-':
            hi = s[i + 1]
            j = i + 2
            if hi == '\\' and j < n:
                hi = _TR_ESC.get(s[j], s[j])
                j += 1
            if ord(hi) >= ord(c):
                out.extend(chr(x) for x in range(ord(c), ord(hi) + 1))
                i = j
                continue
        out.append(c)
    return out


@applet
def a_tr(sh, argv):
    opts, sets = getopt(argv[1:], 'dscCt', {'delete': 'd', 'squeeze-repeats': 's',
                                             'complement': 'c'}, posix=True)
    o = dict(opts)
    comp = 'c' in o or 'C' in o
    if not sets:
        raise UsageError('missing operand')
    s1 = _tr_set(sets[0])
    s2 = _tr_set(sets[1]) if len(sets) > 1 else []
    set1 = set(s1)
    text = sh.dec(sh.read_all(0))
    if 'd' in o:
        if comp:
            text = ''.join(c for c in text if c in set1)
        else:
            text = ''.join(c for c in text if c not in set1)
        squeeze = set(s2) if 's' in o else None
    elif s2:
        if comp:
            last = s2[-1]
            text = ''.join(c if c in set1 else last for c in text)
        else:
            if len(s2) < len(s1):
                s2 = s2 + [s2[-1]] * (len(s1) - len(s2))
            table = {}
            for a, b in zip(s1, s2):
                table[ord(a)] = b
            text = text.translate(table)
        squeeze = set(s2) if 's' in o else None
    else:
        if 's' not in o:
            raise UsageError("missing operand after '%s'" % sets[0])
        squeeze = None
        if comp:
            out = []
            prev = None
            for c in text:
                if c not in set1 and c == prev:
                    continue
                out.append(c)
                prev = c
            text = ''.join(out)
        else:
            squeeze = set1
    if squeeze:
        out = []
        prev = None
        for c in text:
            if c == prev and c in squeeze:
                continue
            out.append(c)
            prev = c
        text = ''.join(out)
    sh.out(text)
    return 0


@applet
def a_tee(sh, argv):
    opts, files = getopt(argv[1:], 'ai', {'append': 'a'})
    o = dict(opts)
    outs = []
    st = 0
    for name in files:
        try:
            outs.append(open(sh.abspath(name), 'ab' if 'a' in o else 'wb', buffering=0))
        except OSError as e:
            sh.err('tee: %s: %s\n' % (name, e.strerror or e))
            st = 1
    try:
        f = sh.fds.get(0)
        if f is not None:
            for chunk in iter_chunks(f):
                sh.out_bytes(chunk)
                for of in outs:
                    of.write(chunk)
    finally:
        for of in outs:
            of.close()
    return st


# ------------------------------------------------------------------ grep
def _grep_walk(sh, path, disp, acc):
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return
    for nm in names:
        p = os.path.join(path, nm)
        d = disp.rstrip('/') + '/' + nm if disp else nm
        if os.path.isdir(p):
            _grep_walk(sh, p, d, acc)
        else:
            acc.append(d)


@applet(usage=2)
def a_grep(sh, argv):
    name0 = argv[0]
    args = []
    for a in argv[1:]:
        m = re.match(r'-([0-9]+)$', a)
        args.extend(['-C', m.group(1)] if m else [a])
    opts, rest = getopt(args, 'EFGPivncqslLhHowxrRe:f:m:A:B:C:IaUz',
                        {'extended-regexp': 'E', 'fixed-strings': 'F', 'basic-regexp': 'G',
                         'perl-regexp': 'P', 'ignore-case': 'i', 'invert-match': 'v',
                         'line-number': 'n', 'count': 'c', 'quiet': 'q', 'silent': 'q',
                         'no-messages': 's', 'files-with-matches': 'l',
                         'files-without-match': 'L', 'no-filename': 'h', 'with-filename': 'H',
                         'only-matching': 'o', 'word-regexp': 'w', 'line-regexp': 'x',
                         'recursive': 'r', 'regexp': 'e', 'file': 'f', 'max-count': 'm',
                         'after-context': 'A', 'before-context': 'B', 'context': 'C',
                         'color': 'I', 'colour': 'I', 'text': 'a', 'binary-files': 'U',
                         'include': 'U', 'exclude': 'U', 'line-buffered': 'I'})
    flags = set(c for c, v in opts)
    pats = []
    after = before = 0
    maxc = None
    for c, v in opts:
        if c == 'e':
            pats.extend(v.split('\n'))
        elif c == 'f':
            with open(sh.abspath(v), 'rb') as pf:
                pats.extend(split_lines(sh.dec(pf.read())))
        elif c == 'm':
            maxc = to_int(v)
        elif c == 'A':
            after = to_int(v)
        elif c == 'B':
            before = to_int(v)
        elif c == 'C':
            after = before = to_int(v)
    if 'e' not in flags and 'f' not in flags:
        if not rest:
            raise UsageError('usage: grep [OPTION]... PATTERNS [FILE]...')
        pats = rest[0].split('\n')
        rest = rest[1:]
    mode = 'G'
    if name0 == 'egrep' or 'E' in flags:
        mode = 'E'
    if name0 == 'fgrep' or 'F' in flags:
        mode = 'F'
    if 'P' in flags:
        mode = 'P'
    srcs = []
    for p in pats:
        if mode == 'F':
            srcs.append(re.escape(p))
        elif mode == 'P':
            srcs.append(p)
        else:
            srcs.append(pattern.posix_to_py(p, ere=(mode == 'E')))
    src = '|'.join('(?:%s)' % s for s in srcs) if len(srcs) != 1 else srcs[0]
    if 'w' in flags:
        src = r'(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])' % src
    try:
        rx = re.compile(src, re.IGNORECASE if 'i' in flags else 0)
    except re.error as e:
        sh.err('grep: invalid regular expression: %s\n' % e)
        return 2
    whole = 'x' in flags
    invert = 'v' in flags
    files = rest
    recursive = 'r' in flags or 'R' in flags
    if recursive:
        acc = []
        for f in (files or ['.']):
            p = sh.abspath(f)
            if os.path.isdir(p):
                _grep_walk(sh, p, '' if (f == '.' and not files) else f, acc)
            else:
                acc.append(f)
        files = acc
    with_name = ('H' in flags or len(files) > 1 or recursive) and 'h' not in flags
    errs = []
    quiet_err = 's' in flags
    out = Out(sh)
    any_match = False
    for name in (files or ['-']):
        if name == '-':
            f = sh.fds.get(0)
            close = False
            label = '(standard input)'
        else:
            try:
                p = sh.abspath(name)
                if os.path.isdir(p):
                    if not quiet_err:
                        sh.err('grep: %s: Is a directory\n' % name)
                    continue
                f = open(p, 'rb', buffering=0)
            except OSError as e:
                if not quiet_err:
                    sh.err('grep: %s: %s\n' % (name, e.strerror or e))
                errs.append(1)
                continue
            close = True
            label = name
        prefix = label + ':' if with_name else ''
        cprefix = label + '-' if with_name else ''
        count = 0
        lineno = 0
        pending_after = 0
        ring = []
        last_printed = 0
        try:
            for line, nl in iter_lines(sh, f, out):
                lineno += 1
                if whole:
                    m = rx.fullmatch(line)
                else:
                    m = rx.search(line)
                hit = (m is None) if invert else (m is not None)
                if hit:
                    count += 1
                    any_match = True
                    if 'q' in flags:
                        return 0
                    if 'l' in flags or 'L' in flags or 'c' in flags:
                        if 'l' in flags:
                            break
                    else:
                        if (before or after) and last_printed and \
                                lineno - len(ring) > last_printed + 1:
                            out.write('--\n')
                        for bn, bl in ring:
                            out.write('%s%s%s\n' % (cprefix, ('%d-' % bn) if 'n' in flags else '',
                                                    bl))
                        ring = []
                        num = ('%d:' % lineno) if 'n' in flags else ''
                        if 'o' in flags and not invert:
                            for mm in (rx.finditer(line) if not whole else [m]):
                                if mm.group(0) != '':
                                    out.write('%s%s%s\n' % (prefix, num, mm.group(0)))
                        else:
                            out.write('%s%s%s\n' % (prefix, num, line))
                        last_printed = lineno
                        pending_after = after
                    if maxc is not None and count >= maxc:
                        break
                elif pending_after > 0:
                    out.write('%s%s%s\n' % (cprefix, ('%d-' % lineno) if 'n' in flags else '',
                                            line))
                    last_printed = lineno
                    pending_after -= 1
                elif before:
                    ring.append((lineno, line))
                    if len(ring) > before:
                        ring.pop(0)
        finally:
            if close:
                f.close()
        if 'c' in flags:
            out.write('%s%d\n' % (prefix, count))
        elif 'l' in flags and count:
            out.write(label + '\n')
        elif 'L' in flags and not count:
            out.write(label + '\n')
    out.flush()
    if errs and not any_match:
        return 2
    return 0 if any_match else 1


a_egrep = a_grep
a_fgrep = a_grep


# ------------------------------------------------------------------ small filters
@applet
def a_rev(sh, argv):
    errs = []
    out = Out(sh)
    for name, f in open_inputs(sh, 'rev', argv[1:], errs):
        for line, nl in iter_lines(sh, f, out):
            out.write(line[::-1] + ('\n' if nl else ''))
    out.flush()
    return 1 if errs else 0


@applet
def a_tac(sh, argv):
    errs = []
    lines = split_lines(read_text(sh, 'tac', argv[1:], errs))
    sh.out(''.join(l + '\n' for l in reversed(lines)))
    return 1 if errs else 0


@applet
def a_nl(sh, argv):
    opts, files = getopt(argv[1:], 'b:w:s:v:n:', {})
    o = dict(opts)
    style = o.get('b', 't')
    width = to_int(o.get('w', '6'))
    sep = o.get('s', '\t')
    num = to_int(o.get('v', '1'))
    errs = []
    out = Out(sh)
    for name, f in open_inputs(sh, 'nl', files, errs):
        for line, nl in iter_lines(sh, f, out):
            if style == 'a' or (style == 't' and line != ''):
                out.write('%s%s%s\n' % (str(num).rjust(width), sep, line))
                num += 1
            else:
                out.write((' ' * (width + len(sep)) + line if line else '') + '\n')
    out.flush()
    return 1 if errs else 0


@applet
def a_paste(sh, argv):
    opts, files = getopt(argv[1:], 'd:s', {'delimiters': 'd', 'serial': 's'})
    o = dict(opts)
    delims = list(o.get('d', '\t').replace('\\t', '\t').replace('\\n', '\n')) or ['']
    errs = []
    cols = []
    stdin_lines = None
    for name in (files or ['-']):
        if name == '-':
            if stdin_lines is None:
                stdin_lines = split_lines(sh.dec(sh.read_all(0)))
            cols.append(stdin_lines)
        else:
            cols.append(split_lines(read_text(sh, 'paste', [name], errs)))
    out = []
    if 's' in o:
        for col in cols:
            row = []
            for k, v in enumerate(col):
                if k:
                    row.append(delims[(k - 1) % len(delims)])
                row.append(v)
            out.append(''.join(row) + '\n')
    else:
        n = max([len(c) for c in cols] or [0])
        if files and files.count('-') > 1:
            k = files.count('-')
            rows = [stdin_lines[i:i + k] for i in range(0, len(stdin_lines), k)]
            for r in rows:
                r = r + [''] * (k - len(r))
                out.append(''.join(v + (delims[i % len(delims)] if i < k - 1 else '')
                                   for i, v in enumerate(r)) + '\n')
        else:
            for i in range(n):
                row = []
                for k, col in enumerate(cols):
                    if k:
                        row.append(delims[(k - 1) % len(delims)])
                    row.append(col[i] if i < len(col) else '')
                out.append(''.join(row) + '\n')
    sh.out(''.join(out))
    return 1 if errs else 0


@applet
def a_seq(sh, argv):
    args = argv[1:]
    sep = '\n'
    equal = False
    fmt = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '-w':
            equal = True
        elif a == '-s' and i + 1 < len(args):
            i += 1
            sep = args[i]
        elif a.startswith('-s') and len(a) > 2:
            sep = a[2:]
        elif a == '-f' and i + 1 < len(args):
            i += 1
            fmt = args[i]
        elif a == '--':
            i += 1
            break
        else:
            break
        i += 1
    nums = args[i:]
    if not nums or len(nums) > 3:
        raise UsageError('missing operand' if not nums else 'extra operand')
    try:
        vals = [float(x) if ('.' in x or 'e' in x.lower()) else int(x) for x in nums]
    except ValueError:
        raise UsageError("invalid floating point argument: '%s'" % ' '.join(nums))
    first, incr = 1, 1
    if len(vals) == 1:
        last = vals[0]
    elif len(vals) == 2:
        first, last = vals
    else:
        first, incr, last = vals
    if incr == 0:
        raise UsageError("invalid Zero increment value: '0'")
    prec = max([len(x.split('.')[1]) if '.' in x else 0 for x in nums[:-1] or ['1']] or [0])
    isfloat = any(isinstance(v, float) for v in (first, incr)) or isinstance(last, float)
    out = []
    k = 0
    while True:
        v = first + incr * k
        if (incr > 0 and v > last + 1e-12) or (incr < 0 and v < last - 1e-12):
            break
        if fmt:
            out.append(fmt % v)
        elif isfloat:
            out.append('%.*f' % (prec, v))
        else:
            out.append(str(v))
        k += 1
        if k > 100000000:
            break
    if equal and out:
        w = max(len(x) for x in out)
        out = [('-' + x[1:].zfill(w - 1)) if x.startswith('-') else x.zfill(w) for x in out]
    if out:
        sh.out(sep.join(out) + '\n')
    return 0


@applet
def a_yes(sh, argv):
    line = sh.enc((' '.join(argv[1:]) or 'y') + '\n') * 512
    while True:
        sh.out_bytes(line)


@applet
def a_base64(sh, argv):
    opts, files = getopt(argv[1:], 'dDiw:', {'decode': 'd', 'wrap': 'w', 'ignore-garbage': 'i'})
    o = dict(opts)
    errs = []
    data = b''
    for name, f in open_inputs(sh, 'base64', files[:1], errs):
        data = b''.join(iter_chunks(f))
    if errs:
        return 1
    if 'd' in o or 'D' in o:
        try:
            sh.out_bytes(_b64.b64decode(b''.join(data.split())))
        except Exception:
            sh.err('base64: invalid input\n')
            return 1
        return 0
    enc = _b64.b64encode(data)
    w = to_int(o.get('w', '76'))
    if w > 0:
        enc = b'\n'.join(enc[i:i + w] for i in range(0, len(enc), w))
    sh.out_bytes(enc + (b'\n' if enc else b''))
    return 0


def _convert_files(sh, cmd, files, fn):
    if not files:
        sh.out_bytes(fn(sh.read_all(0)))
        return 0
    st = 0
    for name in files:
        p = sh.abspath(name)
        try:
            with open(p, 'rb') as f:
                data = f.read()
            with open(p, 'wb') as f:
                f.write(fn(data))
        except OSError as e:
            sh.err('%s: %s: %s\n' % (cmd, name, e.strerror or e))
            st = 1
    return st


@applet
def a_dos2unix(sh, argv):
    return _convert_files(sh, 'dos2unix', [a for a in argv[1:] if not a.startswith('-')],
                          lambda d: d.replace(b'\r\n', b'\n'))


@applet
def a_unix2dos(sh, argv):
    return _convert_files(sh, 'unix2dos', [a for a in argv[1:] if not a.startswith('-')],
                          lambda d: d.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))


def _codec(name):
    n = name.split('//')[0].strip()
    alias = {'SJIS': 'cp932', 'SHIFT_JIS': 'cp932', 'SHIFT-JIS': 'cp932', 'MS932': 'cp932',
             'WINDOWS-31J': 'cp932', 'CP932': 'cp932', 'EUCJP': 'euc_jp', 'EUC-JP': 'euc_jp',
             'UTF8': 'utf-8'}
    n = alias.get(n.upper(), n)
    try:
        return codecs.lookup(n).name
    except LookupError:
        raise UsageError('conversion from/to `%s\' is not supported' % name)


@applet
def a_iconv(sh, argv):
    opts, files = getopt(argv[1:], 'f:t:co:l', {'from-code': 'f', 'to-code': 't',
                                                  'output': 'o', 'list': 'l'})
    o = dict(opts)
    if 'l' in o:
        sh.out('UTF-8 UTF-16 UTF-16LE UTF-16BE CP932 SJIS SHIFT_JIS EUC-JP ISO-2022-JP '
               'ISO-8859-1 ASCII CP1252\n')
        return 0
    src = _codec(o.get('f', sh.root.encoding))
    dst_name = o.get('t', sh.root.encoding)
    dst = _codec(dst_name)
    lenient = 'c' in o or '//IGNORE' in dst_name.upper()
    translit = '//TRANSLIT' in dst_name.upper()
    errs = []
    data = b''
    for name, f in open_inputs(sh, 'iconv', files, errs):
        data += b''.join(iter_chunks(f))
    if errs:
        return 1
    try:
        text = data.decode(src, 'ignore' if lenient else 'strict')
        res = text.encode(dst, 'ignore' if lenient else ('replace' if translit else 'strict'))
    except UnicodeError as e:
        sh.err('iconv: illegal input sequence at position %d\n' % getattr(e, 'start', 0))
        return 1
    if 'o' in o:
        with open(sh.abspath(o['o']), 'wb') as f:
            f.write(res)
    else:
        sh.out_bytes(res)
    return 0


def _hashsum(algo):
    @applet
    def fn(sh, argv):
        opts, files = getopt(argv[1:], 'cbt', {'check': 'c', 'binary': 'b', 'text': 't',
                                                'quiet': 'q', 'status': 'S'})
        o = dict(opts)
        errs = []
        if 'c' in o:
            bad = 0
            for line in split_lines(read_text(sh, argv[0], files, errs)):
                m = re.match(r'([0-9a-fA-F]+) [ *](.*)$', line)
                if not m:
                    continue
                try:
                    with open(sh.abspath(m.group(2)), 'rb') as f:
                        h = hashlib.new(algo)
                        for chunk in iter(lambda: f.read(1 << 20), b''):
                            h.update(chunk)
                    ok = h.hexdigest() == m.group(1).lower()
                except OSError:
                    sh.err('%s: %s: No such file or directory\n' % (argv[0], m.group(2)))
                    ok = False
                if 'S' not in o and not (ok and 'q' in o):
                    sh.out('%s: %s\n' % (m.group(2), 'OK' if ok else 'FAILED'))
                if not ok:
                    bad += 1
            if bad and 'S' not in o:
                sh.err('%s: WARNING: %d computed checksum%s did NOT match\n'
                       % (argv[0], bad, '' if bad == 1 else 's'))
            return 1 if bad or errs else 0
        for name, f in open_inputs(sh, argv[0], files, errs):
            h = hashlib.new(algo)
            for chunk in iter_chunks(f):
                h.update(chunk)
            sh.out('%s  %s\n' % (h.hexdigest(), name))
        return 1 if errs else 0
    return fn


a_md5sum = _hashsum('md5')
a_sha1sum = _hashsum('sha1')
a_sha256sum = _hashsum('sha256')
a_sha512sum = _hashsum('sha512')


# ------------------------------------------------------------------ diff / cmp
def _rng(a, b):
    return str(a) if a >= b else '%d,%d' % (a, b)


@applet(usage=2)
def a_diff(sh, argv):
    opts, files = getopt(argv[1:], 'uqsibwBU:rN', {'unified': 'u', 'brief': 'q',
                                                    'report-identical-files': 's',
                                                    'ignore-case': 'i',
                                                    'ignore-space-change': 'b',
                                                    'ignore-all-space': 'w',
                                                    'ignore-blank-lines': 'B'})
    o = dict(opts)
    if len(files) != 2:
        raise UsageError('missing operand' if len(files) < 2 else 'extra operand')
    datas = []
    for name in files:
        try:
            if name == '-':
                datas.append(sh.read_all(0))
            else:
                p = sh.abspath(name)
                if os.path.isdir(p):
                    sh.err('diff: %s: Is a directory (directory diff is not supported)\n' % name)
                    return 2
                with open(p, 'rb') as f:
                    datas.append(f.read())
        except OSError as e:
            sh.err('diff: %s: %s\n' % (name, e.strerror or e))
            return 2
    a = sh.dec(datas[0]).split('\n')
    b = sh.dec(datas[1]).split('\n')
    a_nonl = a[-1] != ''
    b_nonl = b[-1] != ''
    if not a_nonl:
        a.pop()
    if not b_nonl:
        b.pop()

    def norm(s):
        if 'w' in o:
            s = re.sub(r'[ \t]+', '', s)
        elif 'b' in o:
            s = re.sub(r'[ \t]+', ' ', s).rstrip()
        if 'i' in o:
            s = s.lower()
        return s

    na = [norm(x) for x in a]
    nb = [norm(x) for x in b]
    same = na == nb and (a_nonl == b_nonl or bool(set('bw') & set(o)))
    if same:
        if 's' in o:
            sh.out('Files %s and %s are identical\n' % (files[0], files[1]))
        return 0
    if 'q' in o:
        sh.out('Files %s and %s differ\n' % (files[0], files[1]))
        return 1
    # 改行なし終端を区別するため、最終行に目印を付けて比較する
    if a_nonl and na:
        na[-1] += '\0'
    if b_nonl and nb:
        nb[-1] += '\0'
    sm = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    out = []
    if 'u' in o or 'U' in o:
        ctx = to_int(o['U']) if 'U' in o else 3
        out.append('--- %s\n+++ %s\n' % (files[0], files[1]))
        for group in sm.get_grouped_opcodes(ctx):
            i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]

            def ur(s, e):
                ln = e - s
                if ln == 1:
                    return str(s + 1)
                return '%d,%d' % (s + 1 if ln else s, ln)
            out.append('@@ -%s +%s @@\n' % (ur(i1, i2), ur(j1, j2)))
            for tag, x1, x2, y1, y2 in group:
                if tag == 'equal':
                    for k in range(x1, x2):
                        out.append(' ' + a[k] + '\n')
                        if a_nonl and k == len(a) - 1:
                            out.append('\\ No newline at end of file\n')
                    continue
                if tag in ('replace', 'delete'):
                    for k in range(x1, x2):
                        out.append('-' + a[k] + '\n')
                        if a_nonl and k == len(a) - 1:
                            out.append('\\ No newline at end of file\n')
                if tag in ('replace', 'insert'):
                    for k in range(y1, y2):
                        out.append('+' + b[k] + '\n')
                        if b_nonl and k == len(b) - 1:
                            out.append('\\ No newline at end of file\n')
    else:
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            if tag == 'replace':
                out.append('%sc%s\n' % (_rng(i1 + 1, i2), _rng(j1 + 1, j2)))
            elif tag == 'delete':
                out.append('%sd%d\n' % (_rng(i1 + 1, i2), j1))
            else:
                out.append('%da%s\n' % (i1, _rng(j1 + 1, j2)))
            if tag in ('replace', 'delete'):
                for k in range(i1, i2):
                    out.append('< ' + a[k] + '\n')
                    if a_nonl and k == len(a) - 1:
                        out.append('\\ No newline at end of file\n')
            if tag == 'replace':
                out.append('---\n')
            if tag in ('replace', 'insert'):
                for k in range(j1, j2):
                    out.append('> ' + b[k] + '\n')
                    if b_nonl and k == len(b) - 1:
                        out.append('\\ No newline at end of file\n')
    sh.out(''.join(out))
    return 1


@applet(usage=2)
def a_cmp(sh, argv):
    opts, files = getopt(argv[1:], 'sl', {'silent': 's', 'quiet': 's'})
    o = dict(opts)
    if len(files) < 2:
        raise UsageError('missing operand')
    datas = []
    for name in files[:2]:
        try:
            if name == '-':
                datas.append(sh.read_all(0))
            else:
                with open(sh.abspath(name), 'rb') as f:
                    datas.append(f.read())
        except OSError as e:
            if 's' not in o:
                sh.err('cmp: %s: %s\n' % (name, e.strerror or e))
            return 2
    a, b = datas
    if a == b:
        return 0
    if 's' not in o:
        n = min(len(a), len(b))
        k = 0
        while k < n and a[k] == b[k]:
            k += 1
        if k == n:
            sh.err('cmp: EOF on %s after byte %d\n' % (files[0] if len(a) < len(b) else files[1],
                                                       n))
        else:
            sh.out('%s %s differ: byte %d, line %d\n' % (files[0], files[1], k + 1,
                                                         a[:k].count(b'\n') + 1))
    return 1


# ------------------------------------------------------------------ expr
class _Expr(object):
    def __init__(self, args):
        self.a = args
        self.i = 0

    def peek(self):
        return self.a[self.i] if self.i < len(self.a) else None

    def next(self):
        t = self.peek()
        if t is None:
            raise UsageError('syntax error: missing argument')
        self.i += 1
        return t

    @staticmethod
    def num(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            raise UsageError('non-integer argument')

    @staticmethod
    def truthy(v):
        return not (v == '' or re.match(r'-?0+$', str(v)))

    def or_(self):
        v = self.and_()
        while self.peek() == '|':
            self.i += 1
            r = self.and_()
            v = v if self.truthy(v) else (r if self.truthy(r) else '0')
        return v

    def and_(self):
        v = self.cmp_()
        while self.peek() == '&':
            self.i += 1
            r = self.cmp_()
            v = v if (self.truthy(v) and self.truthy(r)) else '0'
        return v

    def cmp_(self):
        v = self.add()
        while self.peek() in ('=', '==', '!=', '<', '<=', '>', '>='):
            op = self.next()
            r = self.add()
            try:
                x, y = int(v), int(r)
            except ValueError:
                x, y = str(v), str(r)
            res = {'=': x == y, '==': x == y, '!=': x != y, '<': x < y, '<=': x <= y,
                   '>': x > y, '>=': x >= y}[op]
            v = '1' if res else '0'
        return v

    def add(self):
        v = self.mul()
        while self.peek() in ('+', '-'):
            op = self.next()
            r = self.mul()
            v = str(self.num(v) + self.num(r) if op == '+' else self.num(v) - self.num(r))
        return v

    def mul(self):
        v = self.match()
        while self.peek() in ('*', '/', '%'):
            op = self.next()
            r = self.match()
            x, y = self.num(v), self.num(r)
            if op != '*' and y == 0:
                raise UsageError('division by zero')
            if op == '*':
                v = str(x * y)
            else:
                q = abs(x) // abs(y)
                if (x < 0) != (y < 0):
                    q = -q
                v = str(q if op == '/' else x - q * y)
        return v

    def match(self):
        v = self.prim()
        while self.peek() == ':':
            self.i += 1
            v = self._match(v, self.prim())
        return v

    @staticmethod
    def _match(s, rx):
        try:
            m = re.match(pattern.posix_to_py(rx, ere=False), s)
        except re.error:
            raise UsageError('Invalid regular expression')
        if m is None:
            return '' if '\\(' in rx else '0'
        if m.groups():
            return m.group(1) or ''
        return str(len(m.group(0)))

    def prim(self):
        t = self.next()
        if t == '(':
            v = self.or_()
            if self.next() != ')':
                raise UsageError('syntax error')
            return v
        if t == 'length' and self.peek() is not None:
            return str(len(self.next()))
        if t == 'substr' and self.peek() is not None:
            s, p, ln = self.next(), self.num(self.next()), self.num(self.next())
            return s[p - 1:p - 1 + ln] if p > 0 and ln > 0 else ''
        if t == 'index' and self.peek() is not None:
            s, chars = self.next(), self.next()
            idx = [s.find(c) for c in chars if c in s]
            return str(min(idx) + 1) if idx else '0'
        if t == 'match' and self.peek() is not None:
            s = self.next()
            return self._match(s, self.next())
        return t


@applet
def a_expr(sh, argv):
    args = argv[1:]
    if args[:1] == ['--']:
        args = args[1:]
    if not args:
        raise UsageError('missing operand')
    p = _Expr(args)
    try:
        v = p.or_()
        if p.i != len(args):
            raise UsageError('syntax error: unexpected argument')
    except UsageError as e:
        sh.err('expr: %s\n' % e)
        return 2
    sh.out(str(v) + '\n')
    return 0 if _Expr.truthy(v) else 1


# ------------------------------------------------------------------ od
_OD_NAMED = {0: '\\0', 7: '\\a', 8: '\\b', 9: '\\t', 10: '\\n', 11: '\\v', 12: '\\f',
             13: '\\r'}


@applet
def a_od(sh, argv):
    args = []
    for a in argv[1:]:
        m = re.match(r'-t([a-zA-Z][0-9]*)$', a)
        m2 = re.match(r'-A([a-z])$', a)
        if m:
            args.extend(['-t', m.group(1)])
        elif m2:
            args.extend(['-A', m2.group(1)])
        else:
            args.append(a)
    opts, files = getopt(args, 'cbxvA:t:N:', {})
    o = dict(opts)
    fmt = o.get('t', 'c' if 'c' in o else ('o1' if 'b' in o else ('x2' if 'x' in o else 'o2')))
    radix = o.get('A', 'o')
    errs = []
    data = b''
    for name, f in open_inputs(sh, 'od', files, errs):
        data += b''.join(iter_chunks(f))
    if 'N' in o:
        data = data[:to_int(o['N'])]

    def addr(n):
        if radix == 'n':
            return ''
        return {'o': '%07o', 'd': '%07d', 'x': '%06x'}[radix] % n

    out = []
    prev = None
    starred = False
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        if 'v' not in o and chunk == prev and len(chunk) == 16:
            if not starred:
                out.append('*\n')
                starred = True
            continue
        starred = False
        prev = chunk
        if fmt == 'c':
            cells = []
            for b in bytearray(chunk):
                if b in _OD_NAMED:
                    cells.append(_OD_NAMED[b].rjust(4))
                elif 32 <= b < 127:
                    cells.append(chr(b).rjust(4))
                else:
                    cells.append(('%03o' % b).rjust(4))
        elif fmt in ('x1', 'o1', 'd1', 'u1'):
            f1 = {'x1': ' %02x', 'o1': ' %03o', 'd1': ' %4d', 'u1': ' %3d'}[fmt]
            cells = [f1 % (b if fmt != 'd1' or b < 128 else b - 256) for b in bytearray(chunk)]
        else:
            width = 2
            base = 'x' if fmt.startswith('x') else 'o'
            cells = []
            for k in range(0, len(chunk), width):
                v = int.from_bytes(chunk[k:k + width].ljust(width, b'\0'), 'little')
                cells.append((' %04x' if base == 'x' else ' %06o') % v)
        out.append(addr(off) + ''.join(cells) + '\n')
    if radix != 'n':
        out.append(addr(len(data)) + '\n')
    sh.out(''.join(out))
    return 1 if errs else 0
