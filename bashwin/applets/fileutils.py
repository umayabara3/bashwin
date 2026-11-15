# -*- coding: utf-8 -*-
"""ファイル操作アプレット: ls mkdir rmdir rm cp mv touch ln chmod chown chgrp mktemp
realpath readlink basename dirname find stat du"""
from __future__ import unicode_literals

import os
import re
import shutil
import stat
import tempfile
import time

from .. import osdep, pattern, timefmt
from .common import applet, getopt, UsageError, to_int

IS_WIN = osdep.IS_WIN


def _err(sh, cmd, name, e):
    sh.err('%s: %s: %s\n' % (cmd, name, getattr(e, 'strerror', None) or e))


def _is_root(p):
    p = os.path.abspath(p)
    return os.path.dirname(p) == p


# ------------------------------------------------------------------ ls
def _mode_str(m):
    t = '-'
    if stat.S_ISDIR(m):
        t = 'd'
    elif stat.S_ISLNK(m):
        t = 'l'
    elif stat.S_ISFIFO(m):
        t = 'p'
    elif stat.S_ISCHR(m):
        t = 'c'
    elif stat.S_ISBLK(m):
        t = 'b'
    elif stat.S_ISSOCK(m):
        t = 's'
    s = ''
    for who in (6, 3, 0):
        s += 'r' if m >> who & 4 else '-'
        s += 'w' if m >> who & 2 else '-'
        s += 'x' if m >> who & 1 else '-'
    return t + s


def _owner(st):
    if IS_WIN:
        return 'owner', 'group'
    try:
        import grp
        import pwd
        return pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name
    except Exception:
        return str(st.st_uid), str(st.st_gid)


def _human(n):
    for unit in ('', 'K', 'M', 'G', 'T'):
        if n < 1024:
            return ('%d%s' % (n, unit)) if unit == '' or n >= 10 else ('%.1f%s' % (n, unit))
        n /= 1024.0
    return '%.1fP' % n


@applet
def a_ls(sh, argv):
    opts, names = getopt(argv[1:], '1aAdlrtSRpFhLgoQ', {'all': 'a', 'almost-all': 'A',
                                                         'directory': 'd', 'reverse': 'r',
                                                         'recursive': 'R', 'color': 'Q',
                                                         'human-readable': 'h'})
    o = set(c for c, v in opts)
    st = [0]
    out = []
    now = time.time()

    def decorate(name, full):
        if 'p' in o or 'F' in o:
            try:
                m = os.lstat(full).st_mode
            except OSError:
                return name
            if stat.S_ISDIR(m):
                return name + '/'
            if 'F' in o:
                if stat.S_ISLNK(m):
                    return name + '@'
                if not IS_WIN and m & 0o111:
                    return name + '*'
        return name

    def sort_entries(entries):
        # entries: [(表示名, 実パス)]
        if 't' in o or 'S' in o:
            def key(e):
                try:
                    s = os.lstat(e[1])
                    return (-(s.st_mtime_ns if 't' in o else s.st_size), e[0])
                except OSError:
                    return (0, e[0])
            entries.sort(key=key)
        else:
            entries.sort(key=lambda e: e[0])
        if 'r' in o:
            entries.reverse()
        return entries

    def emit(entries):
        if 'l' in o or 'g' in o or 'o' in o:
            rows = []
            for name, full in entries:
                try:
                    s = os.lstat(full)
                except OSError as e:
                    _err(sh, 'ls', name, e)
                    st[0] = 1
                    continue
                own, grp_ = _owner(s)
                size = _human(s.st_size) if 'h' in o else str(s.st_size)
                fmt = '%b %e %H:%M' if abs(now - s.st_mtime) < 15552000 else '%b %e  %Y'
                tail = decorate(name, full)
                if stat.S_ISLNK(s.st_mode):
                    try:
                        tail += ' -> ' + os.readlink(full)
                    except OSError:
                        pass
                rows.append((_mode_str(s.st_mode), str(s.st_nlink), own, grp_, size,
                             timefmt.strftime(fmt, s.st_mtime), tail))
            if rows:
                w = [max(len(r[k]) for r in rows) for k in range(5)]
                for r in rows:
                    out.append('%s %s %s %s %s %s %s\n' % (
                        r[0], r[1].rjust(w[1]), r[2].ljust(w[2]), r[3].ljust(w[3]),
                        r[4].rjust(w[4]), r[5], r[6]))
        else:
            for name, full in entries:
                out.append(decorate(name, full) + '\n')

    def list_dir(disp, full, header):
        try:
            ents = os.listdir(full)
        except OSError as e:
            _err(sh, 'ls', "cannot open directory '%s'" % disp, e)
            st[0] = 2
            return
        if header:
            out.append('%s:\n' % disp)
        if 'a' in o:
            ents = ['.', '..'] + ents
        elif 'A' not in o:
            ents = [x for x in ents if not x.startswith('.')]
        entries = sort_entries([(x, os.path.join(full, x)) for x in ents])
        if 'l' in o:
            total = 0
            for nm, fp in entries:
                try:
                    total += getattr(os.lstat(fp), 'st_blocks', 0) // 2
                except OSError:
                    pass
            out.append('total %d\n' % total)
        emit(entries)
        if 'R' in o:
            for nm, fp in entries:
                if nm in ('.', '..'):
                    continue
                if os.path.isdir(fp) and not os.path.islink(fp):
                    out.append('\n')
                    list_dir(disp.rstrip('/') + '/' + nm, fp, True)

    if not names:
        names = ['.']
    files = []
    dirs = []
    for n in names:
        full = sh.abspath(n)
        if not os.path.lexists(full):
            sh.err("ls: cannot access '%s': No such file or directory\n" % n)
            st[0] = 2
        elif os.path.isdir(full) and 'd' not in o:
            dirs.append((n, full))
        else:
            files.append((n, full))
    emit(sort_entries(files))
    header = len(names) > 1 or 'R' in o
    sort_entries(dirs)
    for k, (n, full) in enumerate(dirs):
        if header and (files or k):
            out.append('\n')
        list_dir(n, full, header)
    sh.out(''.join(out))
    return st[0]


# ------------------------------------------------------------------ mkdir / rm / cp / mv
@applet
def a_mkdir(sh, argv):
    opts, names = getopt(argv[1:], 'pvm:', {'parents': 'p', 'verbose': 'v', 'mode': 'm'})
    o = dict(opts)
    if not names:
        raise UsageError('missing operand')
    st = 0
    for n in names:
        p = sh.abspath(n)
        try:
            if 'p' in o:
                if os.path.isdir(p):
                    continue
                os.makedirs(p)
            else:
                os.mkdir(p)
            if 'v' in o:
                sh.out("mkdir: created directory '%s'\n" % n)
        except FileExistsError:
            if 'p' in o and os.path.isdir(p):
                continue
            sh.err("mkdir: cannot create directory '%s': File exists\n" % n)
            st = 1
        except OSError as e:
            sh.err("mkdir: cannot create directory '%s': %s\n" % (n, e.strerror or e))
            st = 1
    return st


@applet
def a_rmdir(sh, argv):
    opts, names = getopt(argv[1:], 'pv', {'parents': 'p', 'ignore-fail-on-non-empty': 'I'})
    o = dict(opts)
    st = 0
    for n in names:
        try:
            os.rmdir(sh.abspath(n))
            if 'p' in o:
                d = os.path.dirname(n.rstrip('/'))
                while d and d not in ('.', '/'):
                    os.rmdir(sh.abspath(d))
                    d = os.path.dirname(d)
        except OSError as e:
            if 'I' in o:
                continue
            sh.err("rmdir: failed to remove '%s': %s\n" % (n, e.strerror or e))
            st = 1
    return st


def _force_remove(fn, path):
    """Windows: 読み取り専用属性を外して再試行する。"""
    try:
        fn(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        fn(path)


def _rmtree(p):
    if os.path.islink(p) or not os.path.isdir(p):
        _force_remove(os.remove, p)
        return
    for nm in os.listdir(p):
        _rmtree(os.path.join(p, nm))
    _force_remove(os.rmdir, p)


@applet
def a_rm(sh, argv):
    opts, names = getopt(argv[1:], 'rRfvdi', {'recursive': 'r', 'force': 'f', 'verbose': 'v',
                                               'dir': 'd', 'no-preserve-root': 'N',
                                               'preserve-root': 'P'})
    o = set(c for c, v in opts)
    rec = 'r' in o or 'R' in o
    if not names:
        if 'f' in o:
            return 0
        raise UsageError('missing operand')
    st = 0
    for n in names:
        p = sh.abspath(n)
        if not os.path.lexists(p):
            if 'f' not in o:
                sh.err("rm: cannot remove '%s': No such file or directory\n" % n)
                st = 1
            continue
        if _is_root(p) and 'N' not in o:
            sh.err("rm: it is dangerous to operate recursively on '%s' (root); skipped\n" % n)
            st = 1
            continue
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                if rec:
                    _rmtree(p)
                elif 'd' in o:
                    os.rmdir(p)
                else:
                    sh.err("rm: cannot remove '%s': Is a directory\n" % n)
                    st = 1
                    continue
            else:
                _force_remove(os.remove, p)
            if 'v' in o:
                sh.out("removed '%s'\n" % n)
        except OSError as e:
            sh.err("rm: cannot remove '%s': %s\n" % (n, e.strerror or e))
            st = 1
    return st


def _copy_file(src, dst, preserve):
    if os.path.isdir(dst):
        raise IsADirectoryError(21, 'Is a directory')
    if preserve:
        shutil.copy2(src, dst)
    else:
        shutil.copyfile(src, dst)
        try:
            shutil.copymode(src, dst)
        except OSError:
            pass


def _copy_tree(src, dst, preserve, links):
    if links and os.path.islink(src):
        os.symlink(os.readlink(src), dst)
        return
    if os.path.isdir(src):
        if not os.path.isdir(dst):
            os.mkdir(dst)
        for nm in sorted(os.listdir(src)):
            _copy_tree(os.path.join(src, nm), os.path.join(dst, nm), preserve, links)
        if preserve:
            try:
                shutil.copystat(src, dst)
            except OSError:
                pass
    else:
        _copy_file(src, dst, preserve)


def _targets(sh, cmd, names, o):
    """(コピー元表示名, 元パス, 先パス) の列を返す。"""
    tdir = o.get('t')
    if tdir is not None:
        srcs = names
        dest = tdir
    else:
        if len(names) < 2:
            raise UsageError("missing destination file operand after '%s'" % names[0]
                             if names else 'missing file operand')
        srcs, dest = names[:-1], names[-1]
    dpath = sh.abspath(dest)
    into = os.path.isdir(dpath) and 'T' not in o
    if len(srcs) > 1 and not into:
        raise UsageError("target '%s' is not a directory" % dest)
    res = []
    for s in srcs:
        sp = sh.abspath(s)
        base = os.path.basename(os.path.normpath(sp))
        res.append((s, sp, os.path.join(dpath, base) if into else dpath))
    return res


@applet
def a_cp(sh, argv):
    opts, names = getopt(argv[1:], 'rRapfvnut:TdPLH', {'recursive': 'r', 'archive': 'a',
                                                        'preserve': 'p', 'force': 'f',
                                                        'verbose': 'v', 'no-clobber': 'n',
                                                        'update': 'u',
                                                        'target-directory': 't',
                                                        'no-target-directory': 'T'})
    o = dict(opts)
    rec = 'r' in o or 'R' in o or 'a' in o
    preserve = 'p' in o or 'a' in o
    links = 'a' in o or 'd' in o or 'P' in o
    st = 0
    for s, sp, dp in _targets(sh, 'cp', names, o):
        try:
            if not os.path.lexists(sp):
                sh.err("cp: cannot stat '%s': No such file or directory\n" % s)
                st = 1
                continue
            if os.path.isdir(sp):
                if not rec:
                    sh.err("cp: -r not specified; omitting directory '%s'\n" % s)
                    st = 1
                    continue
                if os.path.abspath(dp).startswith(os.path.abspath(sp) + os.sep):
                    sh.err("cp: cannot copy a directory, '%s', into itself\n" % s)
                    st = 1
                    continue
                _copy_tree(sp, dp, preserve, links)
            else:
                if os.path.exists(dp):
                    if 'n' in o:
                        continue
                    if 'u' in o and os.path.getmtime(dp) >= os.path.getmtime(sp):
                        continue
                    try:
                        if os.path.samefile(sp, dp):
                            sh.err("cp: '%s' and '%s' are the same file\n" % (s, names[-1]))
                            st = 1
                            continue
                    except OSError:
                        pass
                    if IS_WIN and not os.access(dp, os.W_OK) and 'f' in o:
                        os.chmod(dp, stat.S_IWRITE | stat.S_IREAD)
                _copy_file(sp, dp, preserve)
            if 'v' in o:
                sh.out("'%s' -> '%s'\n" % (s, osdep.unix_path(os.path.relpath(dp, sh.cwd))))
        except OSError as e:
            sh.err("cp: cannot copy '%s': %s\n" % (s, e.strerror or e))
            st = 1
    return st


@applet
def a_mv(sh, argv):
    opts, names = getopt(argv[1:], 'fvnut:Ti', {'force': 'f', 'verbose': 'v',
                                                 'no-clobber': 'n', 'update': 'u',
                                                 'target-directory': 't',
                                                 'no-target-directory': 'T'})
    o = dict(opts)
    st = 0
    for s, sp, dp in _targets(sh, 'mv', names, o):
        try:
            if not os.path.lexists(sp):
                sh.err("mv: cannot stat '%s': No such file or directory\n" % s)
                st = 1
                continue
            if os.path.exists(dp):
                if 'n' in o:
                    continue
                if 'u' in o and os.path.getmtime(dp) >= os.path.getmtime(sp):
                    continue
                if os.path.isdir(dp) and not os.path.isdir(sp):
                    sh.err("mv: cannot overwrite directory '%s' with non-directory\n" % names[-1])
                    st = 1
                    continue
            try:
                os.replace(sp, dp)
            except OSError:
                if os.path.isdir(dp) and os.path.isdir(sp) and not os.listdir(dp):
                    os.rmdir(dp)
                shutil.move(sp, dp)
            if 'v' in o:
                sh.out("renamed '%s' -> '%s'\n" % (s, osdep.unix_path(os.path.relpath(dp, sh.cwd))))
        except (OSError, shutil.Error) as e:
            sh.err("mv: cannot move '%s': %s\n" % (s, getattr(e, 'strerror', None) or e))
            st = 1
    return st


@applet
def a_touch(sh, argv):
    opts, names = getopt(argv[1:], 'acmr:d:t:', {'no-create': 'c', 'reference': 'r',
                                                  'date': 'd'})
    o = dict(opts)
    when = None
    if 'r' in o:
        when = os.stat(sh.abspath(o['r'])).st_mtime
    elif 'd' in o:
        from .sysutils import parse_date
        when = parse_date(o['d'], False)
        if when is None:
            raise UsageError("invalid date format '%s'" % o['d'])
    elif 't' in o:
        m = re.match(r'(?:(\d\d)?(\d\d))?(\d\d)(\d\d)(\d\d)(\d\d)(?:\.(\d\d))?$', o['t'])
        if not m:
            raise UsageError("invalid date format '%s'" % o['t'])
        cc, yy, mo, dd, hh, mi, ss = m.groups()
        year = time.localtime().tm_year if yy is None else int((cc or ('19' if int(yy) >= 69
                                                                       else '20')) + yy)
        when = time.mktime((year, int(mo), int(dd), int(hh), int(mi), int(ss or 0), 0, 0, -1))
    st = 0
    for n in names:
        p = sh.abspath(n)
        try:
            if not os.path.exists(p):
                if 'c' in o:
                    continue
                open(p, 'ab').close()
            os.utime(p, None if when is None else (when, when))
        except OSError as e:
            sh.err("touch: cannot touch '%s': %s\n" % (n, e.strerror or e))
            st = 1
    return st


@applet
def a_ln(sh, argv):
    opts, names = getopt(argv[1:], 'sfnvrT', {'symbolic': 's', 'force': 'f'})
    o = dict(opts)
    if not names:
        raise UsageError('missing file operand')
    if len(names) == 1:
        names = [names[0], os.path.basename(names[0])]
    target, link = names[0], names[-1]
    lp = sh.abspath(link)
    if os.path.isdir(lp) and not os.path.islink(lp) and 'T' not in o:
        lp = os.path.join(lp, os.path.basename(target.rstrip('/')))
    try:
        if 'f' in o and os.path.lexists(lp):
            os.remove(lp)
        if 's' in o:
            os.symlink(target, lp, target_is_directory=os.path.isdir(
                os.path.join(os.path.dirname(lp), target)))
        else:
            os.link(sh.abspath(target), lp)
    except OSError as e:
        sh.err("ln: failed to create %slink '%s': %s%s\n" % (
            'symbolic ' if 's' in o else 'hard ', link, e.strerror or e,
            ' (Windows: requires Developer Mode or administrator rights)' if IS_WIN else ''))
        return 1
    return 0


def _chmod_mode(spec, cur, isdir):
    if re.match(r'[0-7]{1,4}$', spec):
        return int(spec, 8)
    mode = cur & 0o7777
    for clause in spec.split(','):
        m = re.match(r'([ugoa]*)([-+=])([rwxXst]*)$', clause)
        if not m:
            raise UsageError("invalid mode: '%s'" % spec)
        who, op, perms = m.groups()
        who = who or 'a'
        bits = 0
        for p in perms:
            v = {'r': 4, 'w': 2, 'x': 1}.get(p)
            if p == 'X':
                v = 1 if (isdir or cur & 0o111) else 0
            if v is None:
                continue
            if 'u' in who or 'a' in who:
                bits |= v << 6
            if 'g' in who or 'a' in who:
                bits |= v << 3
            if 'o' in who or 'a' in who:
                bits |= v
        if op == '+':
            mode |= bits
        elif op == '-':
            mode &= ~bits
        else:
            mask = 0
            if 'u' in who or 'a' in who:
                mask |= 0o700
            if 'g' in who or 'a' in who:
                mask |= 0o070
            if 'o' in who or 'a' in who:
                mask |= 0o007
            mode = (mode & ~mask) | bits
    return mode


@applet
def a_chmod(sh, argv):
    args = argv[1:]
    rec = False
    while args and args[0] in ('-R', '-v', '-f', '-c', '--recursive'):
        rec = rec or args[0] in ('-R', '--recursive')
        args = args[1:]
    if len(args) < 2:
        raise UsageError('missing operand')
    spec, names = args[0], args[1:]
    st = [0]

    def apply(p, disp):
        try:
            s = os.stat(p)
            os.chmod(p, _chmod_mode(spec, s.st_mode, stat.S_ISDIR(s.st_mode)))
        except OSError as e:
            sh.err("chmod: cannot access '%s': %s\n" % (disp, e.strerror or e))
            st[0] = 1
            return
        if rec and os.path.isdir(p) and not os.path.islink(p):
            for nm in os.listdir(p):
                apply(os.path.join(p, nm), disp + '/' + nm)

    for n in names:
        apply(sh.abspath(n), n)
    return st[0]


@applet
def a_chown(sh, argv):
    args = [a for a in argv[1:] if not a.startswith('-')]
    if len(args) < 2:
        raise UsageError('missing operand')
    if IS_WIN:
        return 0        # Windows には POSIX の所有者が無いので何もしない
    spec, names = args[0], args[1:]
    import grp
    import pwd
    user, _, group = spec.replace('.', ':').partition(':')
    if argv[0] == 'chgrp':
        user, group = '', spec
    try:
        uid = -1 if not user else (int(user) if user.isdigit() else pwd.getpwnam(user).pw_uid)
        gid = -1 if not group else (int(group) if group.isdigit() else grp.getgrnam(group).gr_gid)
    except KeyError:
        sh.err("%s: invalid user or group: '%s'\n" % (argv[0], spec))
        return 1
    st = 0
    for n in names:
        try:
            os.chown(sh.abspath(n), uid, gid)
        except OSError as e:
            _err(sh, argv[0], n, e)
            st = 1
    return st


a_chgrp = a_chown


@applet
def a_mktemp(sh, argv):
    opts, names = getopt(argv[1:], 'dup:tq', {'directory': 'd', 'dry-run': 'u',
                                               'tmpdir': 'p', 'quiet': 'q'})
    o = dict(opts)
    template = names[0] if names else 'tmp.XXXXXXXXXX'
    base = None
    if 'p' in o or 't' in o or not names:
        base = o.get('p') if isinstance(o.get('p'), str) else None
        if not base:
            base = sh.getvar('TMPDIR') or ('/tmp' if not IS_WIN else
                                           osdep.unix_path(tempfile.gettempdir()))
    m = re.search(r'X{3,}', template)
    if not m:
        sh.err("mktemp: too few X's in template '%s'\n" % template)
        return 1
    # 最後の X の並びを置き換える
    ms = list(re.finditer(r'X{3,}', template))[-1]
    import random
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    rng = random.SystemRandom()
    for _ in range(100):
        name = template[:ms.start()] + ''.join(rng.choice(chars) for _ in range(len(ms.group()))) \
            + template[ms.end():]
        disp = (base.rstrip('/') + '/' + name) if base else name
        p = sh.abspath(disp)
        try:
            if 'u' in o:
                if os.path.lexists(p):
                    continue
            elif 'd' in o:
                os.mkdir(p, 0o700)
            else:
                os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            continue
        except OSError as e:
            if 'q' not in o:
                sh.err("mktemp: failed to create %s via template '%s': %s\n"
                       % ('directory' if 'd' in o else 'file', template, e.strerror or e))
            return 1
        sh.out((osdep.unix_path(osdep.map_virtual(disp)) if IS_WIN else disp) + '\n')
        return 0
    return 1


@applet
def a_realpath(sh, argv):
    opts, names = getopt(argv[1:], 'emsqz', {'canonicalize-existing': 'e',
                                             'canonicalize-missing': 'm', 'no-symlinks': 's'})
    o = dict(opts)
    st = 0
    for n in names:
        p = sh.abspath(n)
        r = os.path.normpath(p) if 's' in o else os.path.realpath(p)
        if 'm' not in o and not os.path.exists(os.path.dirname(r) if 'e' not in o else r):
            sh.err('realpath: %s: No such file or directory\n' % n)
            st = 1
            continue
        sh.out(osdep.unix_path(r) + '\n')
    return st


@applet
def a_readlink(sh, argv):
    opts, names = getopt(argv[1:], 'fenmqsvz', {'canonicalize': 'f'})
    o = dict(opts)
    st = 0
    for n in names:
        p = sh.abspath(n)
        if 'f' in o or 'e' in o or 'm' in o:
            sh.out(osdep.unix_path(os.path.realpath(p)) + '\n')
        else:
            try:
                sh.out(os.readlink(p) + ('' if 'n' in o else '\n'))
            except (OSError, AttributeError):
                st = 1
    return st


def _strip_seps(s):
    if IS_WIN:
        s = s.replace('\\', '/')
    return s


@applet
def a_basename(sh, argv):
    opts, names = getopt(argv[1:], 'as:z', {'multiple': 'a', 'suffix': 's'})
    o = dict(opts)
    if not names:
        raise UsageError('missing operand')
    suffix = o.get('s')
    if suffix is None and 'a' not in o and len(names) == 2:
        suffix = names[1]
        names = names[:1]
    elif suffix is None and 'a' not in o:
        names = names[:1]
    out = []
    for n in names:
        s = _strip_seps(n)
        if s and s.strip('/') == '':
            b = '/'
        else:
            b = s.rstrip('/').rsplit('/', 1)[-1]
        if suffix and b.endswith(suffix) and b != suffix:
            b = b[:-len(suffix)]
        out.append(b + '\n')
    sh.out(''.join(out))
    return 0


@applet
def a_dirname(sh, argv):
    names = [a for a in argv[1:] if a != '--']
    if not names:
        raise UsageError('missing operand')
    out = []
    for n in names:
        s = _strip_seps(n)
        if s and s.strip('/') == '':
            out.append('/\n')
            continue
        s = s.rstrip('/')
        if '/' not in s:
            out.append('.\n')
            continue
        d = s.rsplit('/', 1)[0].rstrip('/')
        out.append((d or '/') + '\n')
    sh.out(''.join(out))
    return 0


# ------------------------------------------------------------------ find
class _Find(object):
    def __init__(self, sh, args):
        self.sh = sh
        self.a = args
        self.i = 0
        self.maxdepth = None
        self.mindepth = 0
        self.has_action = False
        self.out = []
        self.status = 0
        self.batch = {}
        self.depth_first = False
        self.now = time.time()

    def peek(self):
        return self.a[self.i] if self.i < len(self.a) else None

    def next(self, what):
        if self.i >= len(self.a):
            raise UsageError("missing argument to `%s'" % what)
        v = self.a[self.i]
        self.i += 1
        return v

    def parse_or(self):
        left = self.parse_and()
        while self.peek() in ('-o', '-or'):
            self.i += 1
            right = self.parse_and()
            left = ('or', left, right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.peek() is not None and self.peek() not in ('-o', '-or', ')'):
            if self.peek() in ('-a', '-and'):
                self.i += 1
            right = self.parse_not()
            left = ('and', left, right)
        return left

    def parse_not(self):
        if self.peek() in ('!', '-not'):
            self.i += 1
            return ('not', self.parse_not())
        return self.parse_prim()

    def _num(self, s):
        m = re.match(r'([-+]?)(\d+)([a-zA-Z]?)$', s)
        if not m:
            raise UsageError("invalid argument `%s'" % s)
        return m.group(1), int(m.group(2)), m.group(3)

    def parse_prim(self):
        t = self.next('expression')
        if t == '(':
            e = self.parse_or()
            if self.next(')') != ')':
                raise UsageError("invalid expression; expected `)'")
            return e
        if t in ('-name', '-iname', '-path', '-ipath', '-wholename', '-regex', '-iregex'):
            v = self.next(t)
            if 'regex' in t:
                return ('regex', re.compile(pattern.posix_to_py(v, ere=False),
                                            re.IGNORECASE if t[1] == 'i' else 0))
            rx = pattern.compile_chars([(c, False) for c in v], t[1] == 'i')
            return ('name' if 'name' in t and 'whole' not in t else 'path', rx)
        if t == '-type':
            return ('type', self.next(t))
        if t == '-maxdepth':
            self.maxdepth = to_int(self.next(t))
            return ('true',)
        if t == '-mindepth':
            self.mindepth = to_int(self.next(t))
            return ('true',)
        if t == '-depth':
            self.depth_first = True
            return ('true',)
        if t in ('-mtime', '-mmin', '-atime', '-amin', '-ctime', '-cmin'):
            sign, n, _ = self._num(self.next(t))
            return ('time', t[1], 60 if t.endswith('min') else 86400, sign, n)
        if t in ('-newer', '-anewer', '-cnewer'):
            ref = self.next(t)
            try:
                return ('newer', os.stat(self.sh.abspath(ref)).st_mtime_ns)
            except OSError as e:
                raise UsageError("'%s': %s" % (ref, e.strerror or e))
        if t == '-size':
            sign, n, unit = self._num(self.next(t))
            mult = {'': 512, 'b': 512, 'c': 1, 'w': 2, 'k': 1024, 'M': 1 << 20, 'G': 1 << 30}
            if unit not in mult:
                raise UsageError("invalid -size type `%s'" % unit)
            return ('size', sign, n, mult[unit])
        if t == '-empty':
            return ('empty',)
        if t in ('-print', '-print0'):
            self.has_action = True
            return ('print', '\0' if t == '-print0' else '\n')
        if t == '-delete':
            self.has_action = True
            self.depth_first = True
            return ('delete',)
        if t == '-prune':
            return ('prune',)
        if t == '-quit':
            return ('quit',)
        if t in ('-true', '-false'):
            return (t[1:],)
        if t in ('-exec', '-execdir', '-ok'):
            self.has_action = True
            cmd = []
            while True:
                v = self.next(t)
                if v == ';':
                    return ('exec', cmd, False, len(self.batch))
                if v == '+' and cmd and cmd[-1] == '{}':
                    key = len(self.batch)
                    self.batch[key] = (cmd[:-1], [])
                    return ('exec', cmd[:-1], True, key)
                cmd.append(v)
        if t in ('-readable', '-writable', '-executable'):
            return ('access', {'r': os.R_OK, 'w': os.W_OK, 'e': os.X_OK}[t[1]])
        if t in ('-user', '-group', '-perm', '-links', '-inum', '-printf', '-fprint', '-ls'):
            raise UsageError("`%s' is not supported by bashwin" % t)
        raise UsageError("unknown predicate `%s'" % t)

    def ev(self, e, disp, full, st, state):
        k = e[0]
        if k == 'and':
            return self.ev(e[1], disp, full, st, state) and self.ev(e[2], disp, full, st, state)
        if k == 'or':
            return self.ev(e[1], disp, full, st, state) or self.ev(e[2], disp, full, st, state)
        if k == 'not':
            return not self.ev(e[1], disp, full, st, state)
        if k == 'true':
            return True
        if k == 'false':
            return False
        if k == 'name':
            base = disp.rstrip('/').rsplit('/', 1)[-1] if disp.strip('/') else disp
            return e[1].fullmatch(base) is not None
        if k == 'path':
            return e[1].fullmatch(disp) is not None
        if k == 'regex':
            return e[1].fullmatch(disp) is not None
        if k == 'type':
            m = st.st_mode
            for t in e[1].split(','):
                if (t == 'f' and stat.S_ISREG(m)) or (t == 'd' and stat.S_ISDIR(m)) or \
                        (t == 'l' and stat.S_ISLNK(m)) or (t == 'p' and stat.S_ISFIFO(m)) or \
                        (t == 's' and stat.S_ISSOCK(m)) or (t == 'b' and stat.S_ISBLK(m)) or \
                        (t == 'c' and stat.S_ISCHR(m)):
                    return True
            return False
        if k == 'time':
            ts = {'m': st.st_mtime, 'a': st.st_atime, 'c': st.st_ctime}[e[1]]
            units = int((self.now - ts) // e[2])
            if e[2] == 60 and e[3] == '':
                units = int((self.now - ts + 59) // 60) if self.now - ts > 0 else 0
            return units > e[4] if e[3] == '+' else (units < e[4] if e[3] == '-' else units == e[4])
        if k == 'newer':
            return st.st_mtime_ns > e[1]
        if k == 'size':
            units = -(-st.st_size // e[3])
            return units > e[2] if e[1] == '+' else (units < e[2] if e[1] == '-' else units == e[2])
        if k == 'empty':
            if stat.S_ISDIR(st.st_mode):
                try:
                    return not os.listdir(full)
                except OSError:
                    return False
            return stat.S_ISREG(st.st_mode) and st.st_size == 0
        if k == 'access':
            return os.access(full, e[1])
        if k == 'print':
            self.out.append(disp + e[1])
            if len(self.out) > 2000:
                self.flush()
            return True
        if k == 'prune':
            state['prune'] = True
            return True
        if k == 'quit':
            state['quit'] = True
            return True
        if k == 'delete':
            try:
                if stat.S_ISDIR(st.st_mode):
                    os.rmdir(full)
                else:
                    _force_remove(os.remove, full)
                return True
            except OSError as ex:
                self.sh.err("find: cannot delete '%s': %s\n" % (disp, ex.strerror or ex))
                self.status = 1
                return False
        if k == 'exec':
            if e[2]:
                self.batch[e[3]][1].append(disp)
                return True
            self.flush()
            cmd = [a.replace('{}', disp) for a in e[1]]
            return self.sh.exec_argv(cmd, nofunc=True) == 0
        return False

    def flush(self):
        if self.out:
            data = ''.join(self.out)
            self.out = []
            self.sh.out(data)

    def walk(self, expr, disp, full, depth, state):
        try:
            st = os.lstat(full)
        except OSError as e:
            self.sh.err("find: '%s': %s\n" % (disp, e.strerror or e))
            self.status = 1
            return
        isdir = stat.S_ISDIR(st.st_mode)
        descend = isdir and (self.maxdepth is None or depth < self.maxdepth)
        if not self.depth_first:
            if depth >= self.mindepth:
                state['prune'] = False
                self.ev(expr, disp, full, st, state)
                if state.get('quit'):
                    return
                if state.get('prune'):
                    descend = False
        if descend:
            try:
                names = os.listdir(full)
            except OSError as e:
                self.sh.err("find: '%s': %s\n" % (disp, e.strerror or e))
                self.status = 1
                names = []
            for nm in names:
                self.walk(expr, disp.rstrip('/') + '/' + nm if disp != '/' else '/' + nm,
                          os.path.join(full, nm), depth + 1, state)
                if state.get('quit'):
                    return
        if self.depth_first and depth >= self.mindepth:
            self.ev(expr, disp, full, st, state)


@applet
def a_find(sh, argv):
    args = argv[1:]
    while args and args[0] in ('-H', '-L', '-P'):
        args = args[1:]
    paths = []
    while args and not (args[0].startswith('-') and len(args[0]) > 1) and args[0] not in ('!', '('):
        paths.append(args[0])
        args = args[1:]
    if not paths:
        paths = ['.']
    f = _Find(sh, args)
    try:
        expr = f.parse_or() if args else ('true',)
        if f.i < len(args):
            raise UsageError("paths must precede expression: `%s'" % args[f.i])
    except UsageError as e:
        sh.err('find: %s\n' % e)
        return 1
    if not f.has_action:
        expr = ('and', expr, ('print', '\n'))
    state = {}
    for p in paths:
        full = sh.abspath(p)
        if not os.path.lexists(full):
            sh.err("find: '%s': No such file or directory\n" % p)
            f.status = 1
            continue
        f.walk(expr, p, full, 0, state)
        if state.get('quit'):
            break
    f.flush()
    for key in sorted(f.batch):
        cmd, items = f.batch[key]
        for k in range(0, len(items), 500):
            if sh.exec_argv(cmd + items[k:k + 500], nofunc=True) != 0:
                f.status = 1
    return f.status


# ------------------------------------------------------------------ stat / du
@applet
def a_stat(sh, argv):
    opts, names = getopt(argv[1:], 'c:Lft', {'format': 'c', 'dereference': 'L',
                                              'printf': 'P'})
    o = dict(opts)
    st_all = 0
    for n in names:
        p = sh.abspath(n)
        try:
            s = os.stat(p) if 'L' in o else os.lstat(p)
        except OSError as e:
            sh.err("stat: cannot statx '%s': %s\n" % (n, e.strerror or e))
            st_all = 1
            continue
        m = s.st_mode
        ftype = ('directory' if stat.S_ISDIR(m) else 'symbolic link' if stat.S_ISLNK(m)
                 else ('regular empty file' if s.st_size == 0 else 'regular file'))
        own, grp_ = _owner(s)
        if 'c' in o:
            def rep(mt):
                c = mt.group(1)
                return {'s': str(s.st_size), 'n': n, 'Y': str(int(s.st_mtime)),
                        'X': str(int(s.st_atime)), 'Z': str(int(s.st_ctime)),
                        'y': timefmt.strftime('%Y-%m-%d %H:%M:%S.%N %z', s.st_mtime),
                        'a': '%o' % (m & 0o7777), 'A': _mode_str(m), 'U': own, 'G': grp_,
                        'u': str(s.st_uid), 'g': str(s.st_gid), 'F': ftype,
                        'h': str(s.st_nlink), 'i': str(s.st_ino), '%': '%',
                        'b': str(getattr(s, 'st_blocks', 0)),
                        'N': "'%s'" % n}.get(c, '%' + c)
            sh.out(re.sub(r'%(.)', rep, o['c']) + '\n')
        else:
            sh.out('  File: %s\n  Size: %d\t%s\nAccess: (%04o/%s)  Uid: %s  Gid: %s\nModify: %s\n'
                   % (n, s.st_size, ftype, m & 0o7777, _mode_str(m), own, grp_,
                      timefmt.strftime('%Y-%m-%d %H:%M:%S.%N %z', s.st_mtime)))
    return st_all


@applet
def a_du(sh, argv):
    opts, names = getopt(argv[1:], 'shkbacmd:', {'summarize': 's', 'human-readable': 'h',
                                                  'bytes': 'b', 'all': 'a', 'total': 'c',
                                                  'max-depth': 'd'})
    o = dict(opts)
    maxd = 0 if 's' in o else (to_int(o['d']) if 'd' in o else None)
    out = []
    grand = [0]

    def size_of(s):
        if 'b' in o:
            return s.st_size
        blocks = getattr(s, 'st_blocks', None)
        return blocks * 512 if blocks is not None else -(-s.st_size // 4096) * 4096

    def fmt(n):
        if 'h' in o:
            return _human(n)
        if 'b' in o:
            return str(n)
        if 'm' in o:
            return str(-(-n // (1 << 20)))
        return str(-(-n // 1024))

    def walk(disp, full, depth):
        try:
            s = os.lstat(full)
        except OSError as e:
            sh.err("du: cannot access '%s': %s\n" % (disp, e.strerror or e))
            return 0
        total = size_of(s)
        if stat.S_ISDIR(s.st_mode):
            try:
                names_ = sorted(os.listdir(full))
            except OSError:
                names_ = []
            for nm in names_:
                total += walk(disp.rstrip('/') + '/' + nm, os.path.join(full, nm), depth + 1)
            if maxd is None or depth <= maxd:
                out.append('%s\t%s\n' % (fmt(total), disp))
        elif depth == 0 or ('a' in o and (maxd is None or depth <= maxd)):
            out.append('%s\t%s\n' % (fmt(total), disp))
        return total

    for n in (names or ['.']):
        grand[0] += walk(n, sh.abspath(n), 0)
    if 'c' in o:
        out.append('%s\ttotal\n' % fmt(grand[0]))
    sh.out(''.join(out))
    return 0
