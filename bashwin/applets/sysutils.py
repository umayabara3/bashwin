# -*- coding: utf-8 -*-
"""システム系アプレット: date sleep env printenv which xargs timeout hostname whoami
uname id nproc tput winpath cygpath"""
from __future__ import unicode_literals

import calendar
import datetime
import os
import platform
import re
import threading
import time

from .. import osdep, timefmt
from .common import applet, getopt, UsageError, to_int, split_lines

IS_WIN = osdep.IS_WIN
_UNITS = {'sec': 'seconds', 'second': 'seconds', 'min': 'minutes', 'minute': 'minutes',
          'hour': 'hours', 'day': 'days', 'week': 'weeks', 'fortnight': 'fortnights',
          'month': 'months', 'year': 'years'}
_MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def _to_epoch(dt, utc):
    tup = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, 0, 0, -1)
    return (calendar.timegm(tup) if utc else time.mktime(tup)) + dt.microsecond / 1e6


def _add_months(dt, months):
    total = dt.year * 12 + (dt.month - 1) + months
    y, m = divmod(total, 12)
    first = dt.replace(year=y, month=m + 1, day=1)
    return first + datetime.timedelta(days=dt.day - 1)     # 月末あふれは mktime と同じく繰り越す


def parse_date(text, utc, now=None):
    """GNU date -d のよく使う書式を解釈して epoch 秒を返す。解釈できなければ None。"""
    if now is None:
        now = time.time()
    s = text.strip()
    if s.startswith('@'):
        try:
            return float(s[1:])
        except ValueError:
            return None
    tm = time.gmtime(now) if utc else time.localtime(now)
    dt = datetime.datetime(tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec)
    low = s.lower().replace(',', ' ')
    tz_utc = utc
    had_date = False
    had_time = False
    # 絶対日付
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', low)
    if m:
        dt = dt.replace(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))
        low = low[:m.start()] + ' ' + low[m.end():]
        had_date = True
    else:
        m = re.search(r'(?<![\d:.+-])(\d{4})(\d{2})(\d{2})(?![\d:])', low)
        if m:
            dt = dt.replace(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))
            low = low[:m.start()] + ' ' + low[m.end():]
            had_date = True
    m = re.search(r'(?:^|[\st])(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(am|pm)?', low)
    if m:
        hh = int(m.group(1))
        if m.group(5) == 'pm' and hh < 12:
            hh += 12
        if m.group(5) == 'am' and hh == 12:
            hh = 0
        dt = dt.replace(hour=hh, minute=int(m.group(2)), second=int(m.group(3) or 0))
        low = low[:m.start()] + ' ' + low[m.end():]
        had_time = True
    elif had_date:
        dt = dt.replace(hour=0, minute=0, second=0)
    m = re.search(r'(?:^|\s)(z|utc|gmt)(?:\s|$)', low)
    if m:
        tz_utc = True
        low = low[:m.start()] + ' ' + low[m.end():]
    months = 0
    delta = datetime.timedelta()
    toks = low.replace('t', ' t ').split() if False else low.split()
    i = 0
    sign_next = 1
    while i < len(toks):
        t = toks[i]
        if t in ('now', 'today', 'at', 'on'):
            pass
        elif t == 'yesterday':
            delta -= datetime.timedelta(days=1)
            if not had_time:
                dt = dt.replace(hour=0, minute=0, second=0)
        elif t == 'tomorrow':
            delta += datetime.timedelta(days=1)
            if not had_time:
                dt = dt.replace(hour=0, minute=0, second=0)
        elif t == 'midnight':
            dt = dt.replace(hour=0, minute=0, second=0)
        elif t == 'noon':
            dt = dt.replace(hour=12, minute=0, second=0)
        elif t == 'ago':
            pass
        elif t in ('next', 'last', 'this'):
            sign_next = {'next': 1, 'last': -1, 'this': 0}[t]
            unit = toks[i + 1].rstrip('s') if i + 1 < len(toks) else ''
            if unit not in _UNITS:
                return None
            i += 1
            u = _UNITS[unit]
            if u == 'months':
                months += sign_next
            elif u == 'years':
                months += 12 * sign_next
            else:
                delta += datetime.timedelta(**{u: sign_next}) if u != 'fortnights' \
                    else datetime.timedelta(weeks=2 * sign_next)
        else:
            m = re.match(r'([-+]?\d+)\s*([a-z]*)$', t)
            if not m:
                # 月名 + 日 (例: "15 nov 2026" / "nov 15")
                if t[:3] in _MONTHS and len(t) >= 3:
                    dt = dt.replace(month=_MONTHS.index(t[:3]) + 1)
                    if not had_time:
                        dt = dt.replace(hour=0, minute=0, second=0)
                    i += 1
                    continue
                return None
            n = int(m.group(1))
            unit = m.group(2)
            if not unit:
                if i + 1 < len(toks) and toks[i + 1].rstrip('s') in _UNITS:
                    unit = toks[i + 1]
                    i += 1
                elif i + 1 < len(toks) and toks[i + 1][:3] in _MONTHS:
                    dt = dt.replace(day=n)
                    i += 1
                    continue
                elif i > 0 and toks[i - 1][:3] in _MONTHS and n <= 31:
                    dt = dt.replace(day=n)
                    i += 1
                    continue
                elif n > 31:
                    dt = dt.replace(year=n)
                    i += 1
                    continue
                else:
                    return None
            unit = unit.rstrip('s')
            if unit not in _UNITS:
                return None
            if i + 1 < len(toks) and toks[i + 1] == 'ago':
                n = -n
                i += 1
            u = _UNITS[unit]
            if u == 'months':
                months += n
            elif u == 'years':
                months += 12 * n
            elif u == 'fortnights':
                delta += datetime.timedelta(weeks=2 * n)
            else:
                delta += datetime.timedelta(**{u: n})
        i += 1
    try:
        if months:
            dt = _add_months(dt, months)
        dt = dt + delta
        return _to_epoch(dt, tz_utc)
    except (ValueError, OverflowError):
        return None


@applet
def a_date(sh, argv):
    args = argv[1:]
    utc = False
    when = None
    fmt = None
    i = 0
    tz = sh.getvar('TZ')
    if tz in ('UTC', 'UTC0', 'GMT', 'GMT0', 'Etc/UTC'):
        utc = True
    spec = None
    while i < len(args):
        a = args[i]
        if a in ('-u', '--utc', '--universal'):
            utc = True
        elif a in ('-d', '--date', '-r', '--reference'):
            i += 1
            if i >= len(args):
                raise UsageError("option requires an argument -- '%s'" % a.lstrip('-')[:1])
            spec = (a, args[i])
        elif a.startswith('--date='):
            spec = ('-d', a.split('=', 1)[1])
        elif a.startswith('-d') and len(a) > 2:
            spec = ('-d', a[2:])
        elif a.startswith('--reference='):
            spec = ('-r', a.split('=', 1)[1])
        elif a in ('-R', '--rfc-email', '--rfc-2822'):
            fmt = '%a, %d %b %Y %H:%M:%S %z'
        elif a.startswith('-I') or a.startswith('--iso-8601'):
            v = a[2:] if a.startswith('-I') else a.partition('=')[2]
            fmt = {'': '%Y-%m-%d', 'date': '%Y-%m-%d', 'hours': '%Y-%m-%dT%H%:z',
                   'minutes': '%Y-%m-%dT%H:%M%:z', 'seconds': '%Y-%m-%dT%H:%M:%S%:z',
                   'ns': '%Y-%m-%dT%H:%M:%S,%N%:z'}.get(v)
            if fmt is None:
                raise UsageError("invalid argument '%s' for '--iso-8601'" % v)
        elif a.startswith('+'):
            fmt = a[1:]
        else:
            raise UsageError("invalid date '%s'" % a)
        i += 1
    if spec is not None:
        if spec[0] in ('-r', '--reference'):
            try:
                when = os.stat(sh.abspath(spec[1])).st_mtime
            except OSError as e:
                sh.err('date: %s: %s\n' % (spec[1], e.strerror or e))
                return 1
        else:
            when = parse_date(spec[1], utc)
            if when is None:
                sh.err("date: invalid date '%s'\n" % spec[1])
                return 1
    if fmt is None:
        fmt = '%a %b %e %H:%M:%S %Z %Y'
    sh.out(timefmt.strftime(fmt, when, utc) + '\n')
    return 0


def _duration(s):
    m = re.match(r'([0-9]*\.?[0-9]+)([smhd]?)$', s)
    if not m:
        raise UsageError("invalid time interval '%s'" % s)
    return float(m.group(1)) * {'': 1, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}[m.group(2)]


def _interrupted(sh):
    root = sh.root
    return bool(root.pending_signals) or (sh.job_id and sh.job_id in root.killed)


@applet
def a_sleep(sh, argv):
    if len(argv) < 2:
        raise UsageError('missing operand')
    end = time.time() + sum(_duration(a) for a in argv[1:])
    while True:
        left = end - time.time()
        if left <= 0:
            return 0
        if _interrupted(sh):
            return 130
        time.sleep(min(left, 0.1))


@applet
def a_env(sh, argv):
    args = argv[1:]
    clear = False
    unset = []
    while args and args[0].startswith('-'):
        a = args.pop(0)
        if a in ('-i', '-', '--ignore-environment'):
            clear = True
        elif a == '-u' and args:
            unset.append(args.pop(0))
        elif a == '--':
            break
        else:
            raise UsageError("invalid option -- '%s'" % a.lstrip('-'))
    env = {} if clear else sh.export_env()
    for n in unset:
        env.pop(n, None)
    while args and re.match(r'[A-Za-z_][A-Za-z0-9_]*=', args[0]):
        k, _, v = args.pop(0).partition('=')
        env[k] = v
    if not args:
        sh.out(''.join('%s=%s\n' % kv for kv in sorted(env.items())))
        return 0
    if sh.lookup_builtin(args[0]) is not None:
        from ..interp import Var
        tmp = dict((k, Var(v, True)) for k, v in env.items())
        sh.scopes.append(tmp)
        try:
            return sh.exec_argv(args, nofunc=True)
        finally:
            for k in range(len(sh.scopes) - 1, -1, -1):
                if sh.scopes[k] is tmp:
                    del sh.scopes[k]
                    break
    return sh.run_external(args, env)


@applet
def a_printenv(sh, argv):
    env = sh.export_env()
    names = [a for a in argv[1:] if not a.startswith('-')]
    if not names:
        sh.out(''.join('%s=%s\n' % kv for kv in sorted(env.items())))
        return 0
    st = 0
    for n in names:
        if n in env:
            sh.out(env[n] + '\n')
        else:
            st = 1
    return st


@applet
def a_which(sh, argv):
    st = 0
    for n in [a for a in argv[1:] if not a.startswith('-')]:
        p = sh.find_command(n)
        if p:
            sh.out(osdep.unix_path(p) + '\n')
        elif sh.lookup_builtin(n) is not None:
            sh.out('%s: bashwin built-in command\n' % n)
        else:
            st = 1
    return st


def _xargs_split(text):
    """空白区切り + クォート/バックスラッシュ処理(xargs 既定の入力解釈)。"""
    items = []
    cur = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\n':
            if cur is not None:
                items.append(''.join(cur))
                cur = None
            i += 1
        elif c in '"\'':
            j = text.find(c, i + 1)
            if j < 0:
                raise UsageError('unmatched %s quote' % ('double' if c == '"' else 'single'))
            cur = (cur or []) + [text[i + 1:j]]
            i = j + 1
        elif c == '\\' and i + 1 < n:
            cur = (cur or []) + [text[i + 1]]
            i += 2
        else:
            cur = (cur or []) + [c]
            i += 1
    if cur is not None:
        items.append(''.join(cur))
    return items


@applet
def a_xargs(sh, argv):
    opts, cmd = getopt(argv[1:], '0rtn:I:d:P:L:s:i', {'null': '0', 'no-run-if-empty': 'r',
                                                       'max-args': 'n', 'replace': 'I',
                                                       'delimiter': 'd', 'verbose': 't',
                                                       'max-procs': 'P', 'max-lines': 'L'},
                       posix=True)
    o = dict(opts)
    if not cmd:
        cmd = ['echo']
    text = sh.dec(sh.read_all(0))
    if '0' in o:
        items = [x for x in text.split('\0') if x != '']
    elif 'd' in o:
        d = o['d'].replace('\\n', '\n').replace('\\t', '\t').replace('\\0', '\0')
        items = text.split(d)
        if items and items[-1] == '':
            items.pop()
    elif 'I' in o:
        items = [l for l in split_lines(text) if l.strip() != '']
    elif 'L' in o:
        # -L N: 入力 N 行ごとに 1 回実行する(行の中は空白で分割)
        nlines = max(to_int(o['L']), 1)
        lines = [l for l in split_lines(text) if l.strip() != '']
        worst_l = 0
        for k in range(0, len(lines), nlines):
            st = sh.exec_argv(cmd + _xargs_split(' '.join(lines[k:k + nlines])), nofunc=True)
            worst_l = max(worst_l, 0 if st == 0 else (124 if st == 255 else
                                                      (st if st in (126, 127) else 123)))
        return worst_l
    else:
        items = _xargs_split(text)
    worst = 0

    def run(args):
        if 't' in o:
            sh.err(' '.join(args) + '\n')
        return sh.exec_argv(args, nofunc=True)

    def note(st):
        if st == 0:
            return 0
        if st == 255:
            return 124
        if st >= 126:
            return st if st in (126, 127) else 125
        return 123

    if 'I' in o:
        rep = o['I']
        for it in items:
            it = it.strip()
            worst = max(worst, note(run([a.replace(rep, it) for a in cmd])))
        return worst
    if not items:
        if 'r' in o:
            return 0
        return note(run(cmd))
    per = to_int(o['n']) if 'n' in o else None
    limit = 30000 if IS_WIN else 120000
    batch = []
    size = sum(len(a) + 1 for a in cmd)
    cur = size
    for it in items:
        if batch and ((per and len(batch) >= per) or cur + len(it) + 1 > limit):
            worst = max(worst, note(run(cmd + batch)))
            batch = []
            cur = size
        batch.append(it)
        cur += len(it) + 1
    if batch:
        worst = max(worst, note(run(cmd + batch)))
    return worst


@applet
def a_timeout(sh, argv):
    opts, rest = getopt(argv[1:], 's:k:v', {'signal': 's', 'kill-after': 'k',
                                            'preserve-status': 'p', 'foreground': 'f'},
                        posix=True)
    o = dict(opts)
    if len(rest) < 2:
        raise UsageError('missing operand')
    secs = _duration(rest[0])
    cmd = rest[1:]
    root = sh.root
    sub = sh.clone()
    with root.lock:
        root.job_seq += 1
        jid = root.job_seq
    sub.job_id = jid
    result = [0]

    def target():
        result[0] = sub.run_isolated(_ArgvNode(cmd))

    t = threading.Thread(target=target)
    t.daemon = True
    t.start()
    t.join(secs if secs > 0 else None)
    if not t.is_alive():
        return result[0]
    root.killed.add(jid)
    hard = o.get('s', '').upper().replace('SIG', '') in ('KILL', '9')
    for p, j in list(root.children.items()):
        if j == jid:
            try:
                p.kill() if hard else p.terminate()
            except OSError:
                pass
    t.join(_duration(o['k']) if 'k' in o else 5)
    if t.is_alive():
        for p, j in list(root.children.items()):
            if j == jid:
                try:
                    p.kill()
                except OSError:
                    pass
        t.join(5)
    return result[0] if 'p' in o else (137 if hard else 124)


class _ArgvNode(object):
    """展開済み argv をそのまま実行するための疑似ノード。"""

    def __init__(self, argv):
        self.argv = argv


def _run_argv_node(sh, node):
    return sh.exec_argv(node.argv, nofunc=True)


def _install():
    from ..interp import Interp
    Interp._handlers[_ArgvNode] = _run_argv_node


_install()


@applet
def a_hostname(sh, argv):
    import socket
    name = socket.gethostname()
    if '-s' in argv[1:]:
        name = name.split('.')[0]
    sh.out(name + '\n')
    return 0


@applet
def a_whoami(sh, argv):
    import getpass
    try:
        sh.out(getpass.getuser() + '\n')
    except Exception:
        sh.out((sh.getvar('USERNAME') or sh.getvar('USER') or 'unknown') + '\n')
    return 0


@applet
def a_uname(sh, argv):
    u = platform.uname()
    fields = {'s': 'Windows_NT' if IS_WIN else u.system, 'n': u.node, 'r': u.release,
              'v': u.version, 'm': u.machine, 'o': 'Windows' if IS_WIN else 'GNU/Linux'}
    flags = ''.join(a[1:] for a in argv[1:] if a.startswith('-') and not a.startswith('--'))
    if '--all' in argv[1:] or 'a' in flags:
        flags = 'snrvmo'
    if not flags:
        flags = 's'
    sh.out(' '.join(fields[c] for c in 'snrvmo' if c in flags) + '\n')
    return 0


@applet
def a_id(sh, argv):
    flags = ''.join(a[1:] for a in argv[1:] if a.startswith('-'))
    if IS_WIN:
        uid = gid = 0
        import getpass
        try:
            uname = getpass.getuser()
        except Exception:
            uname = 'user'
        gname = 'users'
    else:
        import grp
        import pwd
        uid, gid = os.geteuid(), os.getegid()
        try:
            uname = pwd.getpwuid(uid).pw_name
        except KeyError:
            uname = str(uid)
        try:
            gname = grp.getgrgid(gid).gr_name
        except KeyError:
            gname = str(gid)
    if 'u' in flags:
        sh.out((uname if 'n' in flags else str(uid)) + '\n')
    elif 'g' in flags:
        sh.out((gname if 'n' in flags else str(gid)) + '\n')
    else:
        sh.out('uid=%d(%s) gid=%d(%s)\n' % (uid, uname, gid, gname))
    return 0


@applet
def a_nproc(sh, argv):
    sh.out('%d\n' % (os.cpu_count() or 1))
    return 0


@applet
def a_tput(sh, argv):
    if argv[1:2] == ['cols']:
        sh.out('80\n')
    elif argv[1:2] == ['lines']:
        sh.out('24\n')
    elif argv[1:2] == ['colors']:
        sh.out('8\n')
    return 0


@applet
def a_winpath(sh, argv):
    """パス表記の変換(cygpath 互換の一部)。-w: C:\\a\\b  -m: C:/a/b  -u: /c/a/b  -a: 絶対化"""
    opts, names = getopt(argv[1:], 'wmua', {'windows': 'w', 'mixed': 'm', 'unix': 'u',
                                            'absolute': 'a'})
    o = dict(opts)
    out = []
    for n in names:
        p = osdep.map_virtual(n) if IS_WIN else n
        if 'a' in o or (IS_WIN and n.startswith('/tmp')):
            p = os.path.normpath(sh.abspath(n))
        p = p.replace('\\', '/')
        if 'w' in o:
            p = p.replace('/', '\\')
        elif 'u' in o:
            m = re.match(r'([A-Za-z]):(/.*|$)', p)
            if m:
                p = '/' + m.group(1).lower() + (m.group(2) or '/')
        out.append(p + '\n')
    sh.out(''.join(out))
    return 0


a_cygpath = a_winpath


@applet(usage=2)
def a_sh(sh, argv):
    """sh / bash として呼ばれたとき: bashwin 自身を別シェルとしてプロセス内実行する。

    スクリプトが `bash other.sh` や `sh -c '...'` を呼んでも、本物の bash 無しで動く。
    """
    from ..interp import Interp, VERSION
    from ..parser import parse, ParseError
    from .. import shbuiltins
    args = argv[1:]
    opts = []
    command = None
    check = False
    stdin_mode = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--':
            i += 1
            break
        if a == '--version':
            sh.out('bashwin %s (bash-compatible interpreter)\n' % VERSION)
            return 0
        if a == '-c':
            if i + 1 >= len(args):
                raise UsageError('-c: option requires an argument')
            command = args[i + 1]
            i += 2
            break
        if a == '-n':
            check = True
        elif a == '-s':
            stdin_mode = True
        elif a in ('-o', '+o') and i + 1 < len(args):
            opts.append([a, args[i + 1]])
            i += 1
        elif a in ('--norc', '--noprofile', '--posix', '-l', '--login', '-i'):
            pass
        elif len(a) > 1 and a[0] in '-+' and not a.startswith('--'):
            flags = a[1:].replace('c', '')
            if flags:
                opts.append([a[0] + flags])
            if 'c' in a[1:]:
                if i + 1 >= len(args):
                    raise UsageError('-c: option requires an argument')
                command = args[i + 1]
                i += 2
                break
        else:
            break
        i += 1
    rest = args[i:]
    script = None
    if command is not None:
        argv0 = rest[0] if rest else argv[0]
        pos = rest[1:]
    elif rest and not stdin_mode:
        script = rest[0]
        argv0 = script
        pos = rest[1:]
    else:
        argv0 = argv[0]
        pos = rest
    if check:
        try:
            if command is not None:
                code = command
            elif script is not None:
                code = sh.read_script(sh.abspath(script))
            else:
                code = sh.dec(sh.read_all(0))
            parse(code)
        except ParseError as e:
            sh.err('%s: line %d: %s\n' % (argv0, e.line, e.msg))
            return 2
        except OSError as e:
            sh.err('%s: %s: %s\n' % (argv[0], script, e.strerror or e))
            return 127
        return 0
    child = Interp(env=sh.export_env(), argv0=argv0, args=pos, cwd=sh.cwd, fds=dict(sh.fds),
                   root=sh.root)
    child.job_id = sh.job_id
    child.is_subshell = True
    for o in opts:
        st = shbuiltins.b_set(child, ['set'] + o)
        if st:
            return st
    saved = sh.root.name
    try:
        if command is not None:
            sh.root.name = argv0
            return child.run_code(command)
        if script is not None:
            return child.run_file(sh.abspath(script))
        return child.run_code(sh.dec(sh.read_all(0)))
    finally:
        sh.root.name = saved


a_bash = a_sh
