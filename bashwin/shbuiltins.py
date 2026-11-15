# -*- coding: utf-8 -*-
"""シェル組み込みコマンド(シェルの状態を変えるもの)。

テキスト処理やファイル操作などの「外部コマンド相当」は applets パッケージ側。
各関数は (sh, argv) を受け取り終了コードを返す。
"""
from __future__ import unicode_literals

import os
import re
import signal
import stat
import time

from . import osdep, timefmt
from .errors import ExitEx, ReturnEx, BreakEx, ContinueEx, ExpandError
from .expand import shell_quote, quote_printf, quote_q
from .parser import Parser

IS_WIN = osdep.IS_WIN
BUILTINS = {}
_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*$')
_ELEM_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]$')
KEYWORDS = frozenset(('if', 'then', 'else', 'elif', 'fi', 'case', 'esac', 'for', 'select',
                      'while', 'until', 'do', 'done', 'in', 'function', 'time', '{', '}',
                      '!', '[[', ']]'))
_SIGNUM = {'0': 'EXIT', '1': 'HUP', '2': 'INT', '3': 'QUIT', '9': 'KILL', '13': 'PIPE',
           '14': 'ALRM', '15': 'TERM'}
_UNSUPPORTED_SHOPT = frozenset(('extglob', 'globstar', 'lastpipe'))


def builtin(*names):
    def deco(fn):
        for n in names:
            BUILTINS[n] = fn
        return fn
    return deco


def fix_bytes(s, encoding='utf-8'):
    """エスケープで作られた生バイト(サロゲート)を正しい文字にまとめ直す。"""
    for c in s:
        if '\udc80' <= c <= '\udcff':
            try:
                return s.encode(encoding, 'surrogateescape').decode(encoding, 'surrogateescape')
            except (UnicodeError, LookupError):
                return s
    return s


def _byte_chr(b):
    b &= 0xFF
    return chr(b) if b < 0x80 else chr(0xDC00 + b)


_ESC = {'a': '\a', 'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f', 'n': '\n', 'r': '\r',
        't': '\t', 'v': '\v', '\\': '\\'}
_OCT = re.compile(r'[0-7]{1,3}')
_HEX2 = re.compile(r'[0-9a-fA-F]{1,2}')


def unescape(s, printf_fmt=False, echo=False):
    """echo -e / printf のバックスラッシュエスケープ。(文字列, \\c で打ち切ったか)

    8 進は echo -e では \\0NNN のみ、printf の書式では \\NNN、%b では両方。
    """
    if '\\' not in s:
        return s, False
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != '\\' or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        d = s[i + 1]
        if d in _ESC:
            out.append(_ESC[d])
            i += 2
        elif d == 'c' and not printf_fmt:
            return ''.join(out), True
        elif d == '0' and not printf_fmt:
            m = _OCT.match(s, i + 2)
            if m:
                out.append(_byte_chr(int(m.group(), 8)))
                i = m.end()
            else:
                out.append('\0')
                i += 2
        elif d in '01234567' and not echo:
            m = _OCT.match(s, i + 1)
            out.append(_byte_chr(int(m.group(), 8)))
            i = m.end()
        elif d == 'x':
            m = _HEX2.match(s, i + 2)
            if m:
                out.append(_byte_chr(int(m.group(), 16)))
                i = m.end()
            else:
                out.append('\\x')
                i += 2
        elif d in 'uU':
            m = re.compile(r'[0-9a-fA-F]{1,%d}' % (4 if d == 'u' else 8)).match(s, i + 2)
            if m:
                out.append(chr(int(m.group(), 16)))
                i = m.end()
            else:
                out.append('\\' + d)
                i += 2
        elif printf_fmt and d in '"\'':
            out.append(d)
            i += 2
        else:
            out.append('\\' + d)
            i += 2
    return ''.join(out), False


# ------------------------------------------------------------------ basics
@builtin(':', 'true')
def b_true(sh, argv):
    return 0


@builtin('false')
def b_false(sh, argv):
    return 1


@builtin('echo')
def b_echo(sh, argv):
    args = argv[1:]
    nl = True
    esc = False
    while args and len(args[0]) > 1 and args[0][0] == '-' and all(c in 'neE' for c in args[0][1:]):
        for c in args[0][1:]:
            if c == 'n':
                nl = False
            elif c == 'e':
                esc = True
            else:
                esc = False
        args = args[1:]
    text = ' '.join(args)
    if esc:
        text, stop = unescape(text, echo=True)
        text = fix_bytes(text, sh.root.encoding)
        if stop:
            nl = False
    sh.out(text + '\n' if nl else text)
    return 0


_FMT_RE = re.compile(r'%([-+ #0]*)(\*|[0-9]+)?(?:\.(\*|[0-9]*))?(\([^)]*\))?([a-zA-Z%])')


def _printf_int(sh, a, errs):
    if a is None or a == '':
        return 0
    if a[0] in '\'"' and len(a) > 1:
        return ord(a[1])
    t = a.strip()
    try:
        neg = t.startswith('-')
        u = t.lstrip('+-')
        if u[:2].lower() == '0x':
            v = int(u, 16)
        elif len(u) > 1 and u[0] == '0':
            v = int(u, 8)
        else:
            v = int(u)
        return -v if neg else v
    except ValueError:
        sh.errmsg('printf: %s: invalid number' % a)
        errs.append(1)
        m = re.match(r'[-+]?[0-9]+', t)
        return int(m.group()) if m else 0


def _printf_float(sh, a, errs):
    if a is None or a == '':
        return 0.0
    if a[0] in '\'"' and len(a) > 1:
        return float(ord(a[1]))
    try:
        return float(a)
    except ValueError:
        sh.errmsg('printf: %s: invalid number' % a)
        errs.append(1)
        return 0.0


@builtin('printf')
def b_printf(sh, argv):
    args = argv[1:]
    var = None
    if args[:1] == ['-v'] and len(args) >= 2:
        var = args[1]
        args = args[2:]
    if args[:1] == ['--']:
        args = args[1:]
    if not args:
        sh.errmsg('printf: usage: printf [-v var] format [arguments]')
        return 2
    fmt = args[0]
    params = args[1:]
    segs = []
    pos = 0
    for m in _FMT_RE.finditer(fmt):
        if m.start() > pos:
            segs.append(unescape(fmt[pos:m.start()], True)[0])
        segs.append(m)
        pos = m.end()
    if pos < len(fmt):
        segs.append(unescape(fmt[pos:], True)[0])
    out = []
    errs = []
    idx = [0]

    def take():
        k = idx[0]
        idx[0] = k + 1
        return params[k] if k < len(params) else None

    enc = sh.root.encoding

    def fmt_s(flags, width, prec, text):
        # bash の printf は C の printf と同じく幅・精度をバイト数で数える
        if all(ord(c) < 128 for c in text):
            return ('%' + flags + (width or '') + ('.' + prec if prec is not None else '') + 's') % text
        try:
            b = text.encode(enc, 'surrogateescape')
        except (UnicodeError, LookupError):
            b = text.encode('utf-8', 'surrogateescape')
        if prec is not None:
            b = b[:int(prec or 0)]
        pad = ' ' * max(int(width or 0) - len(b), 0)
        t = b.decode(enc, 'surrogateescape')
        return t + pad if '-' in flags else pad + t

    stop = False
    while not stop:
        start_idx = idx[0]
        for seg in segs:
            if isinstance(seg, str):
                out.append(seg)
                continue
            flags, width, prec, tfmt, conv = seg.groups()
            if conv == '%':
                out.append('%')
                continue
            if width == '*':
                w = _printf_int(sh, take(), errs)
                if w < 0:
                    flags += '-'
                    w = -w
                width = str(w)
            if prec == '*':
                prec = str(max(_printf_int(sh, take(), errs), 0))
            spec = '%' + flags + (width or '') + ('.' + prec if prec is not None else '')
            if conv == 'T' and tfmt is not None:
                a = take()
                ep = _printf_int(sh, a, errs) if a not in (None, '') else -1
                if ep == -1:
                    ep = time.time()
                elif ep == -2:
                    ep = sh.root.start
                out.append((spec + 's') % timefmt.strftime(tfmt[1:-1], ep))
            elif conv in 'sbq':
                a = take() or ''
                if conv == 'b':
                    a, st = unescape(a)
                    if st:
                        out.append(fmt_s(flags, width, prec, a))
                        stop = True
                        break
                elif conv == 'q':
                    a = quote_printf(a)
                out.append(fmt_s(flags, width, prec, a))
            elif conv in 'di':
                out.append((spec + 'd') % _printf_int(sh, take(), errs))
            elif conv in 'uoxX':
                v = _printf_int(sh, take(), errs)
                if v < 0:
                    v += 1 << 64
                if conv == 'o' and '#' in flags:
                    # C の %#o は先頭に 0 を付ける(Python は 0o になる)
                    body = '%o' % v
                    if not body.startswith('0'):
                        body = '0' + body
                    out.append(('%' + flags.replace('#', '') + (width or '') + 's') % body)
                else:
                    out.append((spec + ('d' if conv == 'u' else conv)) % v)
            elif conv == 'c':
                a = take() or ''
                out.append((spec + 's') % a[:1])
            elif conv in 'eEfFgG':
                out.append((spec + conv) % _printf_float(sh, take(), errs))
            else:
                sh.errmsg("printf: `%s': invalid format character" % conv)
                return 1
        if idx[0] >= len(params) or idx[0] == start_idx:
            break
    text = fix_bytes(''.join(out), sh.root.encoding)
    if var is not None:
        m = _ELEM_RE.match(var)
        if m:
            sh.set_elem(m.group(1), Parser(m.group(2)).parse_word_all(), text)
        else:
            sh.setvar(var, text)
    else:
        sh.out(text)
    return 1 if errs else 0


@builtin('cd')
def b_cd(sh, argv):
    args = [a for a in argv[1:] if a not in ('-L', '-P', '--')]
    show = False
    if not args:
        target = sh.getvar('HOME')
        if not target:
            sh.errmsg('cd: HOME not set')
            return 1
    elif len(args) > 1:
        sh.errmsg('cd: too many arguments')
        return 1
    elif args[0] == '-':
        target = sh.getvar('OLDPWD')
        if not target:
            sh.errmsg('cd: OLDPWD not set')
            return 1
        show = True
    else:
        target = args[0]
    if target == '':
        return 0
    new = os.path.normpath(sh.abspath(target))
    if not os.path.isdir(new):
        sh.errmsg('cd: %s: %s' % (target, 'Not a directory' if os.path.exists(new)
                                  else 'No such file or directory'))
        return 1
    new = osdep.unix_path(new)
    sh.setvar('OLDPWD', sh.cwd)
    sh.cwd = new
    sh.setvar('PWD', new)
    if show:
        sh.out(new + '\n')
    return 0


@builtin('pwd')
def b_pwd(sh, argv):
    if '-P' in argv[1:]:
        sh.out(osdep.unix_path(os.path.realpath(sh.cwd)) + '\n')
    else:
        sh.out(sh.cwd + '\n')
    return 0


@builtin('pushd')
def b_pushd(sh, argv):
    if len(argv) < 2:
        sh.errmsg('pushd: no other directory')
        return 1
    old = sh.cwd
    st = b_cd(sh, ['cd', argv[1]])
    if st == 0:
        sh.dirstack.append(old)
        b_dirs(sh, ['dirs'])
    return st


@builtin('popd')
def b_popd(sh, argv):
    if not sh.dirstack:
        sh.errmsg('popd: directory stack empty')
        return 1
    st = b_cd(sh, ['cd', sh.dirstack.pop()])
    if st == 0:
        b_dirs(sh, ['dirs'])
    return st


@builtin('dirs')
def b_dirs(sh, argv):
    sh.out(' '.join([sh.cwd] + list(reversed(sh.dirstack))) + '\n')
    return 0


# ------------------------------------------------------------------ variables
def _split_assign(arg):
    """(name, index_text|None, append, value|None)。value は str か [(key,val)]。"""
    if hasattr(arg, 'name'):
        return arg.name, arg.index, arg.append, arg.value
    k = arg.find('=')
    if k < 0:
        return arg, None, False, None
    name = arg[:k]
    append = name.endswith('+')
    if append:
        name = name[:-1]
    return name, None, append, arg[k + 1:]


def _decl_str(sh, name, v):
    flags = ''
    val = v.value
    if type(val) is dict:
        flags += 'A' if v.assoc else 'a'
    if v.integer:
        flags += 'i'
    if v.case == 'l':
        flags += 'l'
    if v.readonly:
        flags += 'r'
    if v.case == 'u':
        flags += 'u'
    if v.exported:
        flags += 'x'
    head = 'declare -%s %s' % (flags or '-', name)
    if val is None:
        return head
    if type(val) is dict:
        if v.assoc:
            body = ' '.join('[%s]="%s"' % (shell_quote(k), _dq(x)) for k, x in val.items())
        else:
            body = ' '.join('[%d]="%s"' % (k, _dq(val[k])) for k in sorted(val))
        return '%s=(%s)' % (head, body + (' ' if v.assoc and body else ''))
    return '%s="%s"' % (head, _dq(val))


def _dq(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')


@builtin('declare', 'typeset', 'local')
def b_declare(sh, argv):
    is_local = argv[0] == 'local'
    flags = set()
    minus = set()
    names = []
    for a in argv[1:]:
        if not hasattr(a, 'name') and len(a) > 1 and a[0] in '-+' and not names:
            if a == '--':
                continue
            (flags if a[0] == '-' else minus).update(a[1:])
        else:
            names.append(a)
    in_func = bool(sh.func_stack)
    if 'n' in flags:
        sh.errmsg('%s: -n (nameref) is not supported by bashwin' % argv[0])
        return 2
    if is_local and not in_func:
        sh.errmsg('local: can only be used in a function')
        return 1
    if 'f' in flags or 'F' in flags:
        st = 0
        for n in (names or sorted(sh.funcs)):
            if n in sh.funcs:
                sh.out((n if names else 'declare -f %s' % n) + '\n')
            else:
                st = 1
        return st
    if 'p' in flags or (not names and not is_local):
        st = 0
        if names:
            for n in names:
                v = sh.find(n)
                if v is None:
                    sh.errmsg('declare: %s: not found' % n)
                    st = 1
                else:
                    sh.out(_decl_str(sh, n, v) + '\n')
        else:
            for n in sorted(sh.all_var_names()):
                v = sh.find(n)
                if v is not None:
                    sh.out(_decl_str(sh, n, v) + '\n')
        return st
    st = 0
    for arg in names:
        name, idx, append, value = _split_assign(arg)
        if not _NAME_RE.match(name):
            sh.errmsg("%s: `%s': not a valid identifier" % (argv[0], arg))
            st = 1
            continue
        if (is_local or in_func) and 'g' not in flags:
            v, scope = sh.declare_local(name)
        else:
            scope = sh.scopes[0]
            v = scope.get(name)
            if v is None:
                from .interp import Var
                v = Var()
                scope[name] = v
        if v.readonly and value is not None:
            sh.errmsg('%s: %s: readonly variable' % (argv[0], name))
            st = 1
            continue
        if 'A' in flags:
            v.assoc = True
            if type(v.value) is not dict:
                v.value = {}
        elif 'a' in flags and type(v.value) is not dict:
            v.value = {} if v.value is None else {0: v.value}
        if 'i' in flags:
            v.integer = True
        if 'i' in minus:
            v.integer = False
        if 'l' in flags:
            v.case = 'l'
        if 'u' in flags:
            v.case = 'u'
        if 'x' in flags:
            v.exported = True
        if 'x' in minus:
            v.exported = False
        if value is not None:
            if isinstance(value, list):
                sh.assign_array(name, value, append, scope=scope)
            elif idx is not None:
                sh.set_elem(name, idx, value, append)
            elif append and type(v.value) is not dict:
                sh.setvar(name, (v.value or '') + value, scope=scope)
            else:
                sh.setvar(name, value, scope=scope)
        if 'r' in flags:
            v.readonly = True
    return st


@builtin('export')
def b_export(sh, argv):
    args = argv[1:]
    unexport = False
    while args and not hasattr(args[0], 'name') and args[0].startswith('-') and len(args[0]) > 1:
        if 'f' in args[0]:
            sh.errmsg('export: -f (exporting functions) is not supported by bashwin')
            return 2
        if 'n' in args[0]:
            unexport = True
        if args[0] == '-p' or args[0] == '--':
            pass
        args = args[1:]
    if not args:
        for n in sorted(sh.all_var_names()):
            v = sh.find(n)
            if v is not None and v.exported:
                if type(v.value) is str:
                    sh.out('declare -x %s="%s"\n' % (n, _dq(v.value)))
                elif v.value is None:
                    sh.out('declare -x %s\n' % n)
        return 0
    st = 0
    for arg in args:
        name, idx, append, value = _split_assign(arg)
        if not _NAME_RE.match(name):
            sh.errmsg("export: `%s': not a valid identifier" % arg)
            st = 1
            continue
        if value is not None and not isinstance(value, list):
            if append:
                value = (sh.getvar(name) or '') + value
            sh.setvar(name, value)
        v = sh.find(name)
        if v is None:
            from .interp import Var
            v = Var()
            sh.scopes[0][name] = v
        v.exported = not unexport
    return st


@builtin('readonly')
def b_readonly(sh, argv):
    args = [a for a in argv[1:] if hasattr(a, 'name') or not a.startswith('-')]
    if not args:
        for n in sorted(sh.all_var_names()):
            v = sh.find(n)
            if v is not None and v.readonly:
                sh.out(_decl_str(sh, n, v) + '\n')
        return 0
    for arg in args:
        name, idx, append, value = _split_assign(arg)
        if not _NAME_RE.match(name):
            sh.errmsg("readonly: `%s': not a valid identifier" % arg)
            return 1
        if isinstance(value, list):
            sh.assign_array(name, value, append)
        elif value is not None:
            sh.setvar(name, value)
        v = sh.find(name)
        if v is None:
            from .interp import Var
            v = Var()
            sh.scopes[0][name] = v
        v.readonly = True
    return 0


@builtin('unset')
def b_unset(sh, argv):
    args = argv[1:]
    mode = None
    while args and args[0] in ('-v', '-f', '-n', '--'):
        if args[0] in ('-v', '-f'):
            mode = args[0]
        args = args[1:]
    st = 0
    for a in args:
        if mode == '-f':
            sh.funcs.pop(a, None)
            continue
        m = _ELEM_RE.match(a)
        if m:
            v = sh.find(m.group(1))
            if v is not None and type(v.value) is dict:
                if v.readonly:
                    sh.errmsg('unset: %s: cannot unset: readonly variable' % m.group(1))
                    st = 1
                    continue
                if m.group(2) in ('@', '*'):
                    v.value.clear()
                else:
                    try:
                        v.value.pop(sh._key(v, Parser(m.group(2)).parse_word_all()), None)
                    except ExpandError:
                        pass
            continue
        try:
            if not sh.unsetvar(a) and mode is None:
                sh.funcs.pop(a, None)
        except ExpandError as e:
            sh.errmsg('unset: ' + e.msg)
            st = 1
    return st


@builtin('shift')
def b_shift(sh, argv):
    n = 1
    if len(argv) > 1:
        try:
            n = int(argv[1])
        except ValueError:
            sh.errmsg('shift: %s: numeric argument required' % argv[1])
            return 1
    if n < 0 or n > len(sh.pos):
        return 1
    del sh.pos[:n]
    return 0


def _int_arg(sh, argv, default):
    if len(argv) < 2:
        return default
    try:
        return int(argv[1])
    except ValueError:
        sh.errmsg('%s: %s: numeric argument required' % (argv[0], argv[1]))
        return None


@builtin('exit')
def b_exit(sh, argv):
    n = _int_arg(sh, argv, sh.last_status)
    raise ExitEx(2 if n is None else n & 0xFF)


@builtin('return')
def b_return(sh, argv):
    n = _int_arg(sh, argv, sh.last_status)
    if not sh.func_stack and not sh.source_stack:
        sh.errmsg("return: can only `return' from a function or sourced script")
        return 2
    raise ReturnEx(2 if n is None else n & 0xFF)


@builtin('break')
def b_break(sh, argv):
    n = _int_arg(sh, argv, 1)
    if sh.loop_depth == 0:
        sh.errmsg("break: only meaningful in a `for', `while', or `until' loop")
        return 0
    raise BreakEx(max(n or 1, 1))


@builtin('continue')
def b_continue(sh, argv):
    n = _int_arg(sh, argv, 1)
    if sh.loop_depth == 0:
        sh.errmsg("continue: only meaningful in a `for', `while', or `until' loop")
        return 0
    raise ContinueEx(max(n or 1, 1))


_SET_SHORT = {'e': 'errexit', 'u': 'nounset', 'x': 'xtrace', 'f': 'noglob', 'a': 'allexport',
              'v': 'verbose', 'C': 'noclobber'}
_SET_IGNORED = frozenset(('posix', 'monitor', 'braceexpand', 'hashall', 'histexpand', 'history',
                          'errtrace', 'functrace', 'interactive-comments', 'emacs', 'vi',
                          'notify', 'physical', 'privileged', 'keyword', 'onecmd', 'ignoreeof',
                          'nolog', 'noexec'))


@builtin('set')
def b_set(sh, argv):
    args = argv[1:]
    if not args:
        for n in sorted(sh.all_var_names()):
            v = sh.find(n)
            if v is not None and type(v.value) is str:
                sh.out('%s=%s\n' % (n, shell_quote(v.value)))
        return 0
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--':
            sh.pos = list(args[i + 1:])
            return 0
        if a == '-':
            sh.opts['xtrace'] = False
            sh.opts['verbose'] = False
            if i + 1 < len(args):
                sh.pos = list(args[i + 1:])
            return 0
        if a[0] in '-+' and len(a) > 1:
            on = a[0] == '-'
            for ch in a[1:]:
                if ch == 'o':
                    i += 1
                    if i >= len(args):
                        for k in sorted(sh.opts):
                            sh.out('%-15s\t%s\n' % (k, 'on' if sh.opts[k] else 'off'))
                        return 0
                    name = args[i]
                    if name in sh.opts:
                        sh.opts[name] = on
                    elif name not in _SET_IGNORED:
                        sh.errmsg('set: %s: invalid option name' % name)
                        return 2
                elif ch in _SET_SHORT:
                    sh.opts[_SET_SHORT[ch]] = on
                elif ch not in 'hBHmbkptET':
                    sh.errmsg('set: %s%s: invalid option' % (a[0], ch))
                    return 2
            i += 1
        else:
            sh.pos = list(args[i:])
            return 0
    return 0


@builtin('shopt')
def b_shopt(sh, argv):
    args = argv[1:]
    mode = None
    quiet = False
    while args and args[0].startswith('-'):
        for c in args[0][1:]:
            if c in 'su':
                mode = c
            elif c == 'q':
                quiet = True
        args = args[1:]
    if mode is None:
        st = 0
        for n in (args or sorted(sh.shopts)):
            on = bool(sh.shopts.get(n))
            if not quiet:
                sh.out('%-15s\t%s\n' % (n, 'on' if on else 'off'))
            if not on:
                st = 1
        return st
    for n in args:
        if n in _UNSUPPORTED_SHOPT and mode == 's':
            sh.errmsg('shopt: %s: not supported by bashwin (ignored)' % n)
        sh.shopts[n] = mode == 's'
    return 0


# ------------------------------------------------------------------ source/eval/trap
@builtin('source', '.')
def b_source(sh, argv):
    if len(argv) < 2:
        sh.errmsg('%s: filename argument required' % argv[0])
        return 2
    name = argv[1]
    path = sh.abspath(name)
    if '/' not in name and not os.path.isfile(path):
        sep = ';' if IS_WIN else ':'
        for d in (sh.getvar('PATH') or '').split(sep):
            cand = os.path.join(sh.cwd, d, name)
            if os.path.isfile(cand):
                path = cand
                break
    try:
        code = sh.read_script(path)
    except OSError as e:
        sh.errmsg('%s: %s' % (name, e.strerror or e))
        return 1
    saved_pos = None
    if len(argv) > 2:
        saved_pos = sh.pos
        sh.pos = list(argv[2:])
    sh.source_stack.append(name)
    try:
        return sh.source_string(code)
    except ReturnEx as r:
        return r.status
    finally:
        sh.source_stack.pop()
        if saved_pos is not None:
            sh.pos = saved_pos


@builtin('eval')
def b_eval(sh, argv):
    code = ' '.join(argv[1:])
    if not code.strip():
        return 0
    return sh.source_string(code, sh.lineno or 1)


def _signame(s):
    s = s.upper()
    if s in _SIGNUM:
        return _SIGNUM[s]
    if s.startswith('SIG'):
        s = s[3:]
    return s


@builtin('trap')
def b_trap(sh, argv):
    args = argv[1:]
    if args[:1] == ['--']:
        args = args[1:]
    if not args or args[0] == '-p':
        # サブシェル内では、自分で trap を設定するまでは親の trap を表示する(bash 互換)
        traps = sh.traps or sh.inherited_traps
        want = [_signame(x) for x in args[1:]]
        order = {'EXIT': 0, 'HUP': 1, 'INT': 2, 'QUIT': 3, 'TERM': 15}
        for k in sorted(traps, key=lambda x: (order.get(x, 99), x)):
            if want and k not in want:
                continue
            sh.out("trap -- %s %s\n" % (quote_q(traps[k]),
                                        k if k in ('EXIT', 'ERR', 'DEBUG', 'RETURN') else 'SIG' + k))
        return 0
    if args[0] == '-l':
        sh.out(' 1) SIGHUP\t 2) SIGINT\t 3) SIGQUIT\t 9) SIGKILL\t15) SIGTERM\n')
        return 0
    if len(args) == 1 or args[0] == '-' or args[0].isdigit():
        action = None
        sigs = args[1:] if args[0] == '-' else args
    else:
        action = args[0]
        sigs = args[1:]
    for s in sigs:
        name = _signame(s)
        if name in ('DEBUG', 'RETURN') and action:
            sh.errmsg('trap: %s traps are accepted but never fired by bashwin' % name)
        if action is None:
            sh.traps.pop(name, None)
        else:
            sh.traps[name] = action
        sh.inherited_traps = {}
    return 0


# ------------------------------------------------------------------ lookup
def classify(sh, name):
    if name in KEYWORDS:
        return 'keyword', None
    if name in sh.funcs:
        return 'function', None
    if name in BUILTINS:
        return 'builtin', None
    from . import applets
    if name in applets.REGISTRY:
        return 'builtin', None
    p = sh.find_command(name)
    if p:
        return 'file', osdep.unix_path(p)
    return None, None


@builtin('type')
def b_type(sh, argv):
    args = argv[1:]
    opt = None
    while args and args[0].startswith('-') and len(args[0]) > 1:
        opt = args[0][1:]
        args = args[1:]
    st = 0
    for n in args:
        kind, path = classify(sh, n)
        if opt and 'P' in opt:
            path = sh.find_command(n)
            if path:
                sh.out(osdep.unix_path(path) + '\n')
            else:
                st = 1
            continue
        if kind is None:
            if not opt:
                sh.errmsg('type: %s: not found' % n)
            st = 1
        elif opt and 't' in opt:
            sh.out(kind + '\n')
        elif opt and 'p' in opt:
            if kind == 'file':
                sh.out(path + '\n')
        elif kind == 'keyword':
            sh.out('%s is a shell keyword\n' % n)
        elif kind == 'function':
            sh.out('%s is a function\n' % n)
        elif kind == 'builtin':
            sh.out('%s is a shell builtin\n' % n)
        else:
            sh.out('%s is %s\n' % (n, path))
    return st


@builtin('command')
def b_command(sh, argv):
    args = argv[1:]
    mode = None
    while args and args[0] in ('-v', '-V', '-p', '--'):
        if args[0] in ('-v', '-V'):
            mode = args[0]
        args = args[1:]
    if not args:
        return 0
    if mode is None:
        return sh.exec_argv(args, nofunc=True)
    st = 0
    for n in args:
        kind, path = classify(sh, n)
        if kind is None:
            if mode == '-V':
                sh.errmsg('command: %s: not found' % n)
            st = 1
        elif mode == '-v':
            sh.out((path if kind == 'file' else n) + '\n')
        else:
            sh.out('%s is %s\n' % (n, path if kind == 'file' else 'a shell ' + kind))
    return st


@builtin('builtin')
def b_builtin(sh, argv):
    if len(argv) < 2:
        return 0
    b = sh.lookup_builtin(argv[1])
    if b is None:
        sh.errmsg('builtin: %s: not a shell builtin' % argv[1])
        return 1
    return sh.call_builtin(b, argv[1:])


@builtin('hash', 'umask', 'ulimit', 'disown', 'bind', 'history', 'fc', 'enable', 'compgen',
         'complete', 'times')
def b_noop(sh, argv):
    if argv[0] == 'umask' and len(argv) == 1:
        sh.out('0022\n')
    return 0


@builtin('alias', 'unalias')
def b_alias(sh, argv):
    if len(argv) > 1 and argv[0] == 'alias':
        sh.errmsg('alias: not supported by bashwin (use a function instead)')
        return 1
    return 0


@builtin('let')
def b_let(sh, argv):
    v = 0
    for a in argv[1:]:
        v = sh.arith_word(a)
    return 0 if v != 0 else 1


@builtin('getopts')
def b_getopts(sh, argv):
    if len(argv) < 3:
        sh.errmsg('getopts: usage: getopts optstring name [arg ...]')
        return 2
    optstring = argv[1]
    name = argv[2]
    args = argv[3:] if len(argv) > 3 else sh.pos
    silent = optstring.startswith(':')
    if silent:
        optstring = optstring[1:]
    try:
        optind = int(sh.getvar('OPTIND') or 1)
    except ValueError:
        optind = 1
    state = getattr(sh, '_optstate', None)
    pos = state[1] if state is not None and state[0] == optind else 0
    if optind < 1:
        optind = 1

    def finish(optind, pos, val, st):
        sh.setvar('OPTIND', str(optind))
        sh._optstate = (optind, pos)
        sh.setvar(name, val)
        return st

    if optind > len(args):
        return finish(optind, 0, '?', 1)
    arg = args[optind - 1]
    if pos == 0:
        if arg == '--':
            return finish(optind + 1, 0, '?', 1)
        if len(arg) < 2 or arg[0] != '-':
            return finish(optind, 0, '?', 1)
        pos = 1
    c = arg[pos]
    pos += 1
    at_end = pos >= len(arg)
    k = optstring.find(c)
    if k < 0 or c == ':':
        if silent:
            sh.setvar('OPTARG', c)
        else:
            sh.errmsg('illegal option -- %s' % c)
            sh.unsetvar('OPTARG')
        return finish(optind + 1 if at_end else optind, 0 if at_end else pos, '?', 0)
    if k + 1 < len(optstring) and optstring[k + 1] == ':':
        if not at_end:
            sh.setvar('OPTARG', arg[pos:])
            return finish(optind + 1, 0, c, 0)
        if optind < len(args):
            sh.setvar('OPTARG', args[optind])
            return finish(optind + 2, 0, c, 0)
        if silent:
            sh.setvar('OPTARG', c)
            return finish(optind + 1, 0, ':', 0)
        sh.errmsg('option requires an argument -- %s' % c)
        sh.unsetvar('OPTARG')
        return finish(optind + 1, 0, '?', 0)
    sh.unsetvar('OPTARG')
    return finish(optind + 1 if at_end else optind, 0 if at_end else pos, c, 0)


# ------------------------------------------------------------------ read / mapfile
def _read_split(chars, ifs, nvars):
    """chars: [(ch, escaped)]。IFS で最大 nvars 個に分割(最後は残り全部)。"""
    ws = [c for c in ifs if c in ' \t\n']
    nw = [c for c in ifs if c not in ' \t\n']
    n = len(chars)
    i = 0

    def is_ws(k):
        return not chars[k][1] and chars[k][0] in ws

    def is_nw(k):
        return not chars[k][1] and chars[k][0] in nw

    while i < n and is_ws(i):
        i += 1
    fields = []
    while i < n and len(fields) < nvars - 1:
        start = i
        while i < n and not is_ws(i) and not is_nw(i):
            i += 1
        fields.append(''.join(c for c, e in chars[start:i]))
        while i < n and is_ws(i):
            i += 1
        if i < n and is_nw(i):
            i += 1
            while i < n and is_ws(i):
                i += 1
    if i < n:
        end = n
        while end > i and is_ws(end - 1):
            end -= 1
        # 末尾に非空白区切りが 1 個だけ残っている場合は落とす
        if end > i and is_nw(end - 1):
            k = end - 1
            inner = any(is_ws(j) or is_nw(j) for j in range(i, k))
            if not inner:
                end = k
                while end > i and is_ws(end - 1):
                    end -= 1
        fields.append(''.join(c for c, e in chars[i:end]))
    return fields


@builtin('read')
def b_read(sh, argv):
    args = argv[1:]
    raw = False
    prompt = None
    array = None
    delim = '\n'
    nchars = None
    exact = False
    fd = 0
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--':
            i += 1
            break
        if len(a) < 2 or a[0] != '-':
            break
        j = 1
        while j < len(a):
            c = a[j]
            if c == 'r':
                raw = True
            elif c in 'se':
                pass
            elif c in 'padnNtui':
                val = a[j + 1:]
                if not val:
                    i += 1
                    val = args[i] if i < len(args) else ''
                if c == 'p':
                    prompt = val
                elif c == 'a':
                    array = val
                elif c == 'd':
                    delim = val[:1] if val else '\0'
                elif c in 'nN':
                    try:
                        nchars = int(val)
                    except ValueError:
                        sh.errmsg('read: %s: invalid number' % val)
                        return 2
                    exact = c == 'N'
                elif c == 'u':
                    fd = int(val)
                break
            else:
                sh.errmsg('read: -%s: invalid option' % c)
                return 2
            j += 1
        i += 1
    names = args[i:]
    f = sh.fds.get(fd)
    if f is None:
        sh.errmsg('read: %d: invalid file descriptor' % fd)
        return 1
    if prompt:
        try:
            if f.isatty():
                sh.err(prompt)
        except (AttributeError, ValueError):
            pass
    dbytes = sh.enc(delim)
    found = True
    if nchars is not None:
        buf = bytearray()
        text = ''
        while len(text) < nchars:
            c = f.read(1)
            if not c:
                found = False
                break
            if not exact and c == dbytes:
                break
            buf += c
            text = sh.dec(bytes(buf))
        chars = [(c, False) for c in text]
    else:
        chars = []
        while True:
            data, found = sh.read_line(f, dbytes)
            text = sh.dec(data)
            if sh.opts['igncr'] and text.endswith('\r'):
                text = text[:-1]
            if raw:
                chars.extend((c, False) for c in text)
                break
            k = 0
            cont = False
            while k < len(text):
                c = text[k]
                if c == '\\':
                    if k + 1 < len(text):
                        chars.append((text[k + 1], True))
                        k += 2
                        continue
                    cont = found       # 行末のバックスラッシュ = 行継続
                    k += 1
                    continue
                chars.append((c, False))
                k += 1
            if not cont:
                break
    ifs = sh.getvar('IFS')
    if ifs is None:
        ifs = ' \t\n'
    if array is not None:
        fields = _read_split(chars, ifs, 1 << 30)
        sh.assign_array(array, [(None, x) for x in fields])
    elif not names:
        sh.setvar('REPLY', ''.join(c for c, e in chars))
    else:
        if exact:
            fields = [''.join(c for c, e in chars)]
        else:
            fields = _read_split(chars, ifs, len(names))
        for k, nm in enumerate(names):
            if not _NAME_RE.match(nm):
                sh.errmsg("read: `%s': not a valid identifier" % nm)
                return 1
            sh.setvar(nm, fields[k] if k < len(fields) else '')
    return 0 if found else 1


@builtin('mapfile', 'readarray')
def b_mapfile(sh, argv):
    args = argv[1:]
    strip = False
    delim = '\n'
    count = 0
    skip = 0
    i = 0
    while i < len(args) and args[i].startswith('-') and len(args[i]) > 1:
        a = args[i]
        if a == '-t':
            strip = True
        elif a in ('-d', '-n', '-s', '-O', '-u', '-C', '-c'):
            i += 1
            val = args[i] if i < len(args) else ''
            if a == '-d':
                delim = val[:1] if val else '\0'
            elif a == '-n':
                count = int(val)
            elif a == '-s':
                skip = int(val)
        i += 1
    name = args[i] if i < len(args) else 'MAPFILE'
    text = sh.dec(sh.read_all(0))
    parts = text.split(delim)
    lines = []
    for k, p in enumerate(parts):
        last = k == len(parts) - 1
        if last:
            if p:
                lines.append(p)
        else:
            lines.append(p if strip else p + delim)
    lines = lines[skip:]
    if count:
        lines = lines[:count]
    sh.assign_array(name, [(None, x) for x in lines])
    return 0


# ------------------------------------------------------------------ jobs
@builtin('wait')
def b_wait(sh, argv):
    args = [a for a in argv[1:] if not a.startswith('-')]
    if '-n' in argv[1:]:
        # いずれか 1 つのジョブの終了を待つ
        pending = dict((k, j) for k, j in sh.jobs.items() if not getattr(j, 'reaped', False))
        if not pending:
            return 127
        while True:
            for k, j in pending.items():
                if j.done.is_set():
                    j.reaped = True
                    return j.status
            if sh.root.pending_signals:
                sh.check_signals()
            time.sleep(0.02)
    if not args:
        for job in list(sh.jobs.values()):
            while not job.done.wait(0.2):
                if sh.root.pending_signals:
                    sh.check_signals()
        return 0
    st = 0
    for a in args:
        job = sh.jobs.get(a.lstrip('%')) if not a.startswith('%') else None
        if a.startswith('%'):
            for j in sh.jobs.values():
                if str(j.id) == a[1:]:
                    job = j
        if job is None:
            sh.errmsg('wait: pid %s is not a child of this shell' % a)
            st = 127
            continue
        while not job.done.wait(0.2):
            if sh.root.pending_signals:
                sh.check_signals()
        st = job.status
    return st


@builtin('jobs')
def b_jobs(sh, argv):
    for pid, job in sorted(sh.jobs.items(), key=lambda kv: kv[1].id):
        if not job.done.is_set():
            sh.out('[%d]  Running                 (pid %s)\n' % (job.id, pid))
    return 0


def _kill_job(sh, job, hard):
    job.killed = True
    sh.root.killed.add(job.id)
    for p, jid in list(sh.root.children.items()):
        if jid == job.id:
            try:
                if hard:
                    p.kill()
                else:
                    p.terminate()
            except OSError:
                pass


@builtin('kill')
def b_kill(sh, argv):
    args = argv[1:]
    sig = 'TERM'
    if args and args[0] == '-l':
        sh.out('HUP INT QUIT KILL TERM\n')
        return 0
    if args and args[0] in ('-s', '-n') and len(args) > 1:
        sig = _signame(args[1])
        args = args[2:]
    elif args and args[0].startswith('-') and len(args[0]) > 1 and args[0] != '--':
        sig = _signame(args[0][1:])
        args = args[1:]
    if args[:1] == ['--']:
        args = args[1:]
    if not args:
        sh.errmsg('kill: usage: kill [-s sigspec | -signum] pid | jobspec ...')
        return 2
    st = 0
    for a in args:
        job = None
        if a.startswith('%'):
            for j in sh.jobs.values():
                if str(j.id) == a[1:]:
                    job = j
        else:
            job = sh.jobs.get(a)
        if job is not None:
            if sig == 'EXIT':
                if job.done.is_set():
                    st = 1
            elif job.done.is_set():
                sh.errmsg('kill: (%s) - No such process' % a)
                st = 1
            else:
                _kill_job(sh, job, sig == 'KILL')
            continue
        try:
            pid = int(a)
        except ValueError:
            sh.errmsg('kill: %s: arguments must be process or job IDs' % a)
            st = 1
            continue
        try:
            if sig == 'EXIT':
                if not _pid_alive(pid):
                    st = 1
            elif IS_WIN:
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, getattr(signal, 'SIG' + sig, signal.SIGTERM))
        except (OSError, AttributeError) as e:
            sh.errmsg('kill: (%s) - %s' % (a, getattr(e, 'strerror', None) or 'No such process'))
            st = 1
    return st


def _pid_alive(pid):
    if not IS_WIN:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False
    # Windows の os.kill(pid, 0) は TerminateProcess になるため使わない
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259
    except Exception:
        return False


# ------------------------------------------------------------------ test / [
class TestError(Exception):
    pass


_UNARY = frozenset('-' + c for c in 'abcdefghknoprstuvwxzGLNOS')
_BINARY = frozenset(('=', '==', '!=', '<', '>', '-eq', '-ne', '-lt', '-le', '-gt', '-ge',
                     '-nt', '-ot', '-ef'))


def _mode(sh, a):
    try:
        return os.stat(sh.abspath(a)).st_mode
    except OSError:
        return None


def test_unary(sh, op, a):
    if op == '-z':
        return a == ''
    if op == '-n':
        return a != ''
    if op == '-v':
        m = _ELEM_RE.match(a)
        if m:
            if m.group(2) in ('@', '*'):
                return bool(sh.array_values(m.group(1)))
            return sh.get_elem(m.group(1), Parser(m.group(2)).parse_word_all()) is not None
        if a.isdigit():
            return 0 < int(a) <= len(sh.pos)
        v = sh.find(a)
        return v is not None and v.value is not None
    if op == '-o':
        return bool(sh.opts.get(a))
    if op == '-t':
        try:
            f = sh.fds.get(int(a))
            return f is not None and f.isatty()
        except (ValueError, AttributeError):
            return False
    if a == '':
        return False
    p = sh.abspath(a)
    if op in ('-e', '-a'):
        return os.path.exists(p)
    if op == '-f':
        return os.path.isfile(p)
    if op == '-d':
        return os.path.isdir(p)
    if op in ('-L', '-h'):
        return os.path.islink(p)
    if op == '-s':
        try:
            return os.path.getsize(p) > 0
        except OSError:
            return False
    if op == '-r':
        return os.access(p, os.R_OK)
    if op == '-w':
        return os.access(p, os.W_OK)
    if op == '-x':
        return os.path.exists(p) and osdep.is_executable(p)
    m = _mode(sh, a)
    if m is None:
        return False
    if op == '-p':
        return stat.S_ISFIFO(m)
    if op == '-S':
        return stat.S_ISSOCK(m)
    if op == '-b':
        return stat.S_ISBLK(m)
    if op == '-c':
        return stat.S_ISCHR(m)
    if op == '-u':
        return bool(m & stat.S_ISUID)
    if op == '-g':
        return bool(m & stat.S_ISGID)
    if op == '-k':
        return bool(m & stat.S_ISVTX)
    if op in ('-O', '-G'):
        if IS_WIN:
            return True
        st = os.stat(p)
        return st.st_uid == os.geteuid() if op == '-O' else st.st_gid == os.getegid()
    if op == '-N':
        st = os.stat(p)
        return st.st_mtime > st.st_atime
    raise TestError('%s: unary operator expected' % op)


def _tint(s):
    try:
        return int(s.strip())
    except ValueError:
        raise TestError('%s: integer expression expected' % s)


def _mtime(sh, a):
    try:
        return os.stat(sh.abspath(a)).st_mtime_ns if a else None
    except OSError:
        return None


def test_binary(sh, op, a, b):
    if op in ('=', '=='):
        return a == b
    if op == '!=':
        return a != b
    if op == '<':
        return a < b
    if op == '>':
        return a > b
    if op == '-eq':
        return _tint(a) == _tint(b)
    if op == '-ne':
        return _tint(a) != _tint(b)
    if op == '-lt':
        return _tint(a) < _tint(b)
    if op == '-le':
        return _tint(a) <= _tint(b)
    if op == '-gt':
        return _tint(a) > _tint(b)
    if op == '-ge':
        return _tint(a) >= _tint(b)
    if op in ('-nt', '-ot'):
        ma, mb = _mtime(sh, a), _mtime(sh, b)
        if op == '-nt':
            return ma is not None and (mb is None or ma > mb)
        return mb is not None and (ma is None or ma < mb)
    if op == '-ef':
        try:
            return os.path.samefile(sh.abspath(a), sh.abspath(b))
        except OSError:
            return False
    raise TestError('%s: binary operator expected' % op)


class _TP(object):
    def __init__(self, sh, args):
        self.sh = sh
        self.a = args
        self.i = 0

    def peek(self, k=0):
        return self.a[self.i + k] if self.i + k < len(self.a) else None

    def or_(self):
        v = self.and_()
        while self.peek() == '-o':
            self.i += 1
            r = self.and_()
            v = v or r
        return v

    def and_(self):
        v = self.not_()
        while self.peek() == '-a':
            self.i += 1
            r = self.not_()
            v = v and r
        return v

    def not_(self):
        if self.peek() == '!' and self.peek(1) is not None:
            self.i += 1
            return not self.not_()
        return self.prim()

    def prim(self):
        t = self.peek()
        if t is None:
            raise TestError('argument expected')
        self.i += 1
        if t == '(' and self.peek() is not None:
            v = self.or_()
            if self.peek() != ')':
                raise TestError("`)' expected")
            self.i += 1
            return v
        n1, n2 = self.peek(), self.peek(1)
        if n1 in _BINARY and n2 is not None:
            self.i += 2
            return test_binary(self.sh, n1, t, n2)
        if t in _UNARY and n1 is not None:
            self.i += 1
            return test_unary(self.sh, t, n1)
        return t != ''


def _test(sh, args):
    n = len(args)
    if n == 0:
        return False
    if n == 1:
        return args[0] != ''
    if n == 2:
        if args[0] == '!':
            return args[1] == ''
        if args[0] in _UNARY:
            return test_unary(sh, args[0], args[1])
        raise TestError('%s: unary operator expected' % args[0])
    if n == 3:
        if args[1] in _BINARY:
            return test_binary(sh, args[1], args[0], args[2])
        if args[1] == '-a':
            return args[0] != '' and args[2] != ''
        if args[1] == '-o':
            return args[0] != '' or args[2] != ''
        if args[0] == '!':
            return not _test(sh, args[1:])
        if args[0] == '(' and args[2] == ')':
            return args[1] != ''
        raise TestError('%s: binary operator expected' % args[1])
    if n == 4 and args[0] == '!':
        return not _test(sh, args[1:])
    p = _TP(sh, args)
    v = p.or_()
    if p.i != n:
        raise TestError('too many arguments')
    return v


@builtin('test', '[')
def b_test(sh, argv):
    args = argv[1:]
    if argv[0] == '[':
        if not args or args[-1] != ']':
            sh.errmsg("[: missing `]'")
            return 2
        args = args[:-1]
    try:
        return 0 if _test(sh, args) else 1
    except TestError as e:
        sh.errmsg('%s: %s' % (argv[0], e))
        return 2
