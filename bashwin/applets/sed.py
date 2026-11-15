# -*- coding: utf-8 -*-
"""sed(GNU sed のよく使う範囲)。

対応: アドレス(N, $, /re/, first~step, addr1,addr2, addr1,+N, !)、
コマンド s y d D p P a i c n N g G h H x = q Q b t T : r w l { }、
オプション -n -e -f -E/-r -i[SUFFIX] -s。
"""
from __future__ import unicode_literals

import os
import re

from .. import pattern
from .common import applet, UsageError, split_lines


class _Cmd(object):
    __slots__ = ('a1', 'a2', 'neg', 'name', 'arg', 'arg2', 'flags', 'end', 'active', 'endline')

    def __init__(self):
        self.a1 = self.a2 = None
        self.neg = False
        self.name = None
        self.arg = self.arg2 = None
        self.flags = None
        self.end = -1
        self.active = False
        self.endline = 0


class _Quit(Exception):
    def __init__(self, code):
        Exception.__init__(self)
        self.code = code


class _Script(object):
    def __init__(self, text, ere):
        self.s = text
        self.i = 0
        self.ere = ere
        self.cmds = []
        self.labels = {}
        self.last_re = None

    def err(self, msg):
        raise UsageError('-e expression: char %d: %s' % (self.i, msg))

    def _rx(self, src, icase=False):
        if src == '':
            if self.last_re is None:
                self.err('no previous regular expression')
            return self.last_re
        try:
            rx = re.compile(pattern.posix_to_py(src, self.ere, end_anchor='\\Z'),
                            re.IGNORECASE if icase else 0)
        except re.error as e:
            self.err('invalid regular expression: %s' % e)
        self.last_re = rx
        return rx

    def _delimited(self, delim, is_regex):
        """delim までを読む。正規表現中の [..] 内の delim は終端にしない。"""
        s = self.s
        n = len(s)
        out = []
        in_br = False
        while True:
            if self.i >= n:
                self.err("unterminated `s' command" if is_regex is not None
                         else 'unterminated address regex')
            c = s[self.i]
            if c == '\\' and self.i + 1 < n:
                d = s[self.i + 1]
                if d == delim and not in_br:
                    out.append(d)
                elif d == 'n' and (not is_regex or in_br):
                    out.append('\n')
                elif d == 't' and is_regex:
                    out.append('\t')
                else:
                    out.append(c + d)
                self.i += 2
                continue
            if is_regex:
                if c == '[' and not in_br:
                    in_br = True
                    out.append(c)
                    self.i += 1
                    if self.i < n and s[self.i] == '^':
                        out.append('^')
                        self.i += 1
                    if self.i < n and s[self.i] == ']':
                        out.append(']')
                        self.i += 1
                    continue
                if c == ']' and in_br:
                    in_br = False
            if c == delim and not in_br:
                self.i += 1
                return ''.join(out)
            if c == '\n' and is_regex:
                self.err('unterminated regex')
            out.append(c)
            self.i += 1

    def _addr(self):
        s = self.s
        n = len(s)
        if self.i >= n:
            return None
        c = s[self.i]
        if c.isdigit():
            m = re.compile(r'([0-9]+)(?:~([0-9]+))?').match(s, self.i)
            self.i = m.end()
            if m.group(2) is not None:
                return ('step', int(m.group(1)), int(m.group(2)))
            return ('line', int(m.group(1)))
        if c == '$':
            self.i += 1
            return ('last',)
        if c == '/' or c == '\\':
            if c == '\\':
                self.i += 1
            delim = s[self.i]
            self.i += 1
            src = self._delimited(delim, True)
            icase = False
            while self.i < n and s[self.i] in 'IM':
                icase = icase or s[self.i] == 'I'
                self.i += 1
            return ('re', self._rx(src, icase))
        return None

    def _ws(self):
        while self.i < len(self.s) and self.s[self.i] in ' \t':
            self.i += 1

    def _text_arg(self):
        """a/i/c の本文。GNU の 1 行形式と、バックスラッシュ改行形式の両方。"""
        s = self.s
        n = len(s)
        self._ws()
        if self.i < n and s[self.i] == '\\':
            self.i += 1
            if self.i < n and s[self.i] == '\n':
                self.i += 1
            else:
                self._ws()
        out = []
        while self.i < n:
            c = s[self.i]
            if c == '\\' and self.i + 1 < n:
                out.append(s[self.i + 1])
                self.i += 2
                continue
            if c == '\n':
                self.i += 1
                break
            out.append(c)
            self.i += 1
        return ''.join(out)

    def _rest_of_line(self):
        s = self.s
        self._ws()
        j = s.find('\n', self.i)
        if j < 0:
            j = len(s)
        v = s[self.i:j]
        self.i = j
        return v

    def _label(self):
        s = self.s
        self._ws()
        m = re.compile(r'[^;\n}]*').match(s, self.i)
        self.i = m.end()
        return m.group().strip()

    def parse(self, depth=0):
        s = self.s
        n = len(s)
        stack = []
        while True:
            while self.i < n and s[self.i] in ' \t\n;':
                self.i += 1
            if self.i >= n:
                break
            if s[self.i] == '#':
                j = s.find('\n', self.i)
                self.i = n if j < 0 else j
                continue
            c = _Cmd()
            if s[self.i] == '}':
                if not stack:
                    self.err("unexpected `}'")
                self.i += 1
                self.cmds[stack.pop()].end = len(self.cmds)
                c.name = '}'
                self.cmds.append(c)
                continue
            c.a1 = self._addr()
            if c.a1 is not None:
                self._ws()
                if self.i < n and s[self.i] == ',':
                    self.i += 1
                    self._ws()
                    if self.i < n and s[self.i] == '+':
                        m = re.compile(r'\+([0-9]+)').match(s, self.i)
                        if not m:
                            self.err('unexpected `,\'')
                        self.i = m.end()
                        c.a2 = ('plus', int(m.group(1)))
                    else:
                        c.a2 = self._addr()
                        if c.a2 is None:
                            self.err("unexpected `,'")
            self._ws()
            while self.i < n and s[self.i] == '!':
                c.neg = not c.neg
                self.i += 1
                self._ws()
            if self.i >= n:
                self.err('missing command')
            name = s[self.i]
            self.i += 1
            c.name = name
            if name == '{':
                stack.append(len(self.cmds))
            elif name == 's':
                delim = s[self.i]
                self.i += 1
                src = self._delimited(delim, True)
                rep = self._delimited(delim, False)
                flags = {'g': False, 'p': False, 'n': 0, 'w': None, 'i': False}
                while self.i < n:
                    f = s[self.i]
                    if f == 'g':
                        flags['g'] = True
                    elif f == 'p':
                        flags['p'] = True
                    elif f in 'iI':
                        flags['i'] = True
                    elif f.isdigit():
                        m = re.compile(r'[0-9]+').match(s, self.i)
                        flags['n'] = int(m.group())
                        self.i = m.end() - 1
                    elif f == 'w':
                        self.i += 1
                        flags['w'] = self._rest_of_line()
                        break
                    elif f in 'mMe':
                        pass
                    else:
                        break
                    self.i += 1
                c.arg = self._rx(src, flags['i'])
                c.arg2 = _parse_repl(rep)
                c.flags = flags
            elif name == 'y':
                delim = s[self.i]
                self.i += 1
                a = self._delimited(delim, False)
                b = self._delimited(delim, False)
                if len(a) != len(b):
                    self.err("strings for `y' command are different lengths")
                c.arg = dict((ord(x), y) for x, y in zip(a, b))
            elif name in 'aic':
                c.arg = self._text_arg()
            elif name in 'btT':
                c.arg = self._label()
            elif name == ':':
                self.labels[self._label()] = len(self.cmds)
            elif name in 'rw':
                c.arg = self._rest_of_line()
            elif name in 'qQ':
                self._ws()
                m = re.compile(r'[0-9]+').match(s, self.i)
                c.arg = 0
                if m:
                    c.arg = int(m.group())
                    self.i = m.end()
            elif name not in 'dDpPgGhHxnN=l':
                self.err("unknown command: `%s'" % name)
            self.cmds.append(c)
        if stack:
            self.err("unmatched `{'")
        return self


def _parse_repl(rep):
    """置換文字列を [str | int(グループ番号) | ('case', 'U'|'L'|'E'|'u'|'l')] に分解。"""
    parts = []
    buf = []
    i = 0
    n = len(rep)

    def flush():
        if buf:
            parts.append(''.join(buf))
            del buf[:]

    while i < n:
        c = rep[i]
        if c == '\\' and i + 1 < n:
            d = rep[i + 1]
            i += 2
            if d.isdigit():
                flush()
                parts.append(int(d))
            elif d == 'n':
                buf.append('\n')
            elif d == 't':
                buf.append('\t')
            elif d in 'ULEul':
                flush()
                parts.append(('case', d))
            else:
                buf.append(d)
        elif c == '&':
            flush()
            parts.append(0)
            i += 1
        else:
            buf.append(c)
            i += 1
    flush()
    return parts


def _apply_repl(parts, m):
    out = []
    mode = None
    once = None
    for p in parts:
        if isinstance(p, tuple):
            if p[1] in 'UL':
                mode = p[1]
            elif p[1] == 'E':
                mode = None
            else:
                once = p[1]
            continue
        t = p if isinstance(p, str) else (m.group(p) or '')
        if mode == 'U':
            t = t.upper()
        elif mode == 'L':
            t = t.lower()
        if once and t:
            t = (t[0].upper() if once == 'u' else t[0].lower()) + t[1:]
            once = None
        out.append(t)
    return ''.join(out)


def _subst(c, ps):
    rx, parts, fl = c.arg, c.arg2, c.flags
    nth = fl['n'] or 1
    out = []
    pos = 0
    count = 0
    done = False
    n = len(ps)
    while pos <= n:
        m = rx.search(ps, pos)
        if not m:
            break
        count += 1
        if count >= nth:
            out.append(ps[pos:m.start()])
            out.append(_apply_repl(parts, m))
            done = True
            if m.end() == m.start():
                if m.start() < n:
                    out.append(ps[m.start()])
                pos = m.start() + 1
            else:
                pos = m.end()
            if not fl['g']:
                break
        else:
            end = m.end() if m.end() > m.start() else m.start() + 1
            out.append(ps[pos:end])
            pos = end
    if not done:
        return ps, False
    out.append(ps[pos:])
    return ''.join(out), True


class _Runner(object):
    def __init__(self, sh, script, quiet):
        self.sh = sh
        self.cmds = script.cmds
        self.labels = script.labels
        self.quiet = quiet
        self.out = []
        self.wfiles = {}

    def _match_addr(self, a, lineno, ps, last):
        k = a[0]
        if k == 'line':
            return lineno == a[1]
        if k == 'last':
            return last
        if k == 're':
            return a[1].search(ps) is not None
        if k == 'step':
            if a[2] == 0:
                return lineno == a[1]
            return lineno >= a[1] and (lineno - a[1]) % a[2] == 0
        return False

    def _selected(self, c, lineno, ps, last):
        if c.a1 is None:
            r = True
        elif c.a2 is None:
            r = self._match_addr(c.a1, lineno, ps, last)
        elif c.active:
            a2 = c.a2
            if a2[0] in ('line', 'plus'):
                if lineno >= c.endline:
                    c.active = False
                r = True
            else:
                if self._match_addr(a2, lineno, ps, last):
                    c.active = False
                r = True
        elif self._match_addr(c.a1, lineno, ps, last):
            a2 = c.a2
            r = True
            c.active = True
            if a2[0] == 'line':
                c.endline = a2[1]
                if a2[1] <= lineno:
                    c.active = False
            elif a2[0] == 'plus':
                c.endline = lineno + a2[1]
                if a2[1] == 0:
                    c.active = False
        else:
            r = False
        return (not r) if c.neg else r

    def run(self, lines, trailing_nl=True):
        out = self.out
        cmds = self.cmds
        ncmd = len(cmds)
        hs = ''
        idx = 0
        total = len(lines)
        lineno_base = getattr(self, 'lineno_base', 0)
        code = 0
        try:
            ps = None
            while idx < total or ps is not None:
                if ps is None:
                    ps = lines[idx]
                    idx += 1
                lineno = lineno_base + idx
                last = idx >= total and getattr(self, 'is_last_file', True)
                append = []
                pc = 0
                tflag = False
                autoprint = True
                restart = False
                while pc < ncmd:
                    c = cmds[pc]
                    if not self._selected(c, lineno, ps, last):
                        pc = c.end + 1 if c.name == '{' else pc + 1
                        continue
                    nm = c.name
                    pc += 1
                    if nm == '{' or nm == '}':
                        continue
                    if nm == 's':
                        ps, ok = _subst(c, ps)
                        if ok:
                            tflag = True
                            if c.flags['p']:
                                out.append(ps + '\n')
                            if c.flags['w']:
                                self._wfile(c.flags['w']).append(ps + '\n')
                    elif nm == 'd':
                        autoprint = False
                        break
                    elif nm == 'p':
                        out.append(ps + '\n')
                    elif nm == 'y':
                        ps = ps.translate(c.arg)
                    elif nm == 'a':
                        append.append(c.arg + '\n')
                    elif nm == 'i':
                        out.append(c.arg + '\n')
                    elif nm == 'c':
                        if c.a2 is None or not c.active:
                            out.append(c.arg + '\n')
                        autoprint = False
                        break
                    elif nm == 'n':
                        if idx >= total:
                            raise _Quit(0)
                        if not self.quiet:
                            out.append(ps + '\n')
                        out.extend(append)
                        append = []
                        ps = lines[idx]
                        idx += 1
                        lineno = lineno_base + idx
                        last = idx >= total and getattr(self, 'is_last_file', True)
                    elif nm == 'N':
                        if idx >= total:
                            raise _Quit(0)
                        ps = ps + '\n' + lines[idx]
                        idx += 1
                        lineno = lineno_base + idx
                        last = idx >= total and getattr(self, 'is_last_file', True)
                    elif nm == 'D':
                        k = ps.find('\n')
                        if k < 0:
                            autoprint = False
                            break
                        ps = ps[k + 1:]
                        restart = True
                        autoprint = False
                        break
                    elif nm == 'P':
                        k = ps.find('\n')
                        out.append((ps if k < 0 else ps[:k]) + '\n')
                    elif nm == 'g':
                        ps = hs
                    elif nm == 'G':
                        ps = ps + '\n' + hs
                    elif nm == 'h':
                        hs = ps
                    elif nm == 'H':
                        hs = hs + '\n' + ps
                    elif nm == 'x':
                        ps, hs = hs, ps
                    elif nm == '=':
                        out.append('%d\n' % lineno)
                    elif nm == 'l':
                        out.append(ps.replace('\\', '\\\\').replace('\t', '\\t')
                                   .replace('\n', '\\n') + '$\n')
                    elif nm == 'q':
                        self._final = (ps, append, True)
                        raise _Quit(c.arg)
                    elif nm == 'Q':
                        self._final = (ps, append, False)
                        raise _Quit(c.arg)
                    elif nm == 'b' or (nm == 't' and tflag) or (nm == 'T' and not tflag):
                        if nm == 't':
                            tflag = False
                        if c.arg:
                            if c.arg not in self.labels:
                                raise UsageError("can't find label for jump to `%s'" % c.arg)
                            pc = self.labels[c.arg]
                        else:
                            pc = ncmd
                    elif nm == 'r':
                        try:
                            with open(self.sh.abspath(c.arg), 'rb') as f:
                                append.append(self.sh.dec(f.read()))
                        except OSError:
                            pass
                    elif nm == 'w':
                        self._wfile(c.arg).append(ps + '\n')
                if restart:
                    out.extend(append)
                    continue
                if autoprint and not self.quiet:
                    if idx >= total and not trailing_nl and getattr(self, 'is_last_file', True):
                        out.append(ps)
                    else:
                        out.append(ps + '\n')
                out.extend(append)
                ps = None
        except _Quit as q:
            code = q.code
            fin = getattr(self, '_final', None)
            if fin is None:
                if ps is not None and not self.quiet:
                    out.append(ps + '\n')
            else:
                if fin[2] and not self.quiet:
                    out.append(fin[0] + '\n')
                out.extend(fin[1])
            self.quit = True
        self.lineno_base = lineno_base + total
        return code

    def _wfile(self, name):
        if name not in self.wfiles:
            self.wfiles[name] = []
        return self.wfiles[name]

    def finish(self):
        for name, chunks in self.wfiles.items():
            if name == '/dev/stdout':
                self.out.extend(chunks)
                continue
            try:
                with open(self.sh.abspath(name), 'wb') as f:
                    f.write(self.sh.enc(''.join(chunks)))
            except OSError:
                pass


@applet
def a_sed(sh, argv):
    args = argv[1:]
    scripts = []
    quiet = False
    ere = False
    inplace = None
    separate = False
    files = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--':
            files.extend(args[i + 1:])
            break
        if a in ('-n', '--quiet', '--silent'):
            quiet = True
        elif a in ('-E', '-r', '--regexp-extended'):
            ere = True
        elif a in ('-s', '--separate'):
            separate = True
        elif a == '-e' or a == '--expression':
            i += 1
            if i >= len(args):
                raise UsageError('option requires an argument -- e')
            scripts.append(args[i])
        elif a.startswith('--expression='):
            scripts.append(a.split('=', 1)[1])
        elif a == '-f' or a == '--file':
            i += 1
            if i >= len(args):
                raise UsageError('option requires an argument -- f')
            with open(sh.abspath(args[i]), 'rb') as f:
                scripts.append(sh.dec(f.read()))
        elif a.startswith('-i') or a.startswith('--in-place'):
            inplace = a[2:] if a.startswith('-i') else a.partition('=')[2]
        elif a in ('--posix', '-u', '--unbuffered', '-z', '--debug'):
            pass
        elif len(a) > 1 and a[0] == '-' and all(c in 'nErs' for c in a[1:]):
            quiet = quiet or 'n' in a
            ere = ere or 'E' in a or 'r' in a
            separate = separate or 's' in a
        elif len(a) > 1 and a[0] == '-' and not scripts and a[1] not in '0123456789':
            raise UsageError("invalid option -- '%s'" % a[1:])
        else:
            files.append(a)
        i += 1
    if not scripts:
        if not files:
            raise UsageError('no script specified')
        scripts.append(files.pop(0))
    script = _Script('\n'.join(scripts), ere).parse()

    def load(name):
        if name == '-':
            data = sh.read_all(0)
        else:
            with open(sh.abspath(name), 'rb') as f:
                data = f.read()
        text = sh.dec(data)
        return split_lines(text), (text.endswith('\n') or text == '')

    st = 0
    if inplace is not None:
        for name in files:
            try:
                lines, nl = load(name)
            except OSError as e:
                sh.err("sed: can't read %s: %s\n" % (name, e.strerror or e))
                st = 2
                continue
            for c in script.cmds:
                c.active = False
            r = _Runner(sh, script, quiet)
            r.run(lines, nl)
            r.finish()
            p = sh.abspath(name)
            if inplace:
                bak = p + inplace
                try:
                    if os.path.exists(bak):
                        os.remove(bak)
                    os.rename(p, bak)
                except OSError:
                    pass
            with open(p, 'wb') as f:
                f.write(sh.enc(''.join(r.out)))
        return st
    r = _Runner(sh, script, quiet)
    names = files or ['-']
    loaded = []
    for name in names:
        try:
            loaded.append(load(name))
        except OSError as e:
            sh.err("sed: can't read %s: %s\n" % (name, e.strerror or e))
            st = 2
    code = 0
    if separate:
        for k, (lines, nl) in enumerate(loaded):
            r.is_last_file = True
            code = r.run(lines, nl)
            if getattr(r, 'quit', False):
                break
    else:
        allines = []
        nl = True
        for lines, x in loaded:
            allines.extend(lines)
            nl = x
        code = r.run(allines, nl)
    r.finish()
    sh.out(''.join(r.out))
    return code or st
