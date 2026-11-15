# -*- coding: utf-8 -*-
"""コマンドライン入口。

インタープリター本体は大きなスタックを持つワーカースレッドで動かす
(深い関数再帰でメインスレッドのスタックを溢れさせないため。Windows の
メインスレッドは既定 1MB)。メインスレッドは Ctrl+C / SIGTERM を受けて
ワーカーに伝えるだけ。
"""
from __future__ import print_function

import os
import signal
import sys
import threading

USAGE = """usage: bashwin [options] [script [args...]]
       bashwin [options] -c 'commands' [name [args...]]

options:
  -c CMD           run commands from string
  -s               read the script from standard input
  -n, --check      syntax check only (nothing is executed)
  -e -u -x -f      same as `set -e/-u/-x/-f`
  -o NAME          same as `set -o NAME` (errexit nounset pipefail xtrace igncr ...)
  --inventory      list the commands a script uses (builtins / applets / external)
  --ps1            transpile the script to a self-contained PowerShell 5.1 file (.ps1)
  --ps1-out FILE   where --ps1 writes (default: next to the script; `-` = stdout)
  --ps1-tools external   treat Unix tool names (grep, sed ...) as external programs
  --ps1-force      let --ps1 overwrite a file that bashwin did not generate
  --ps1-check      report whether the script fits the PowerShell-transpilable subset
  --applets        list built-in commands
  --version        show version
  -h, --help       show this help

environment:
  BASHWIN_ENCODING         text encoding for data and output (default: utf-8)
  BASHWIN_PREFER_EXTERNAL  1 = prefer external programs over built-in applets
  BASHWIN_PATHMAP          0 = disable /c/..., /tmp, /dev/null mapping on Windows
"""


def _setup_threads():
    big = sys.maxsize > 2 ** 32
    for size in ((64, 16, 8) if big else (8, 4)):
        try:
            threading.stack_size(size * 1024 * 1024)
            break
        except (ValueError, RuntimeError):
            continue
    sys.setrecursionlimit(30000 if big else 6000)


def main(argv):
    from .interp import Interp, Root, VERSION
    opts = []
    command = None
    check = False
    from_stdin = False
    ps1 = False
    ps1_gen = False
    ps1_out = None
    ps1_tools = 'block'
    ps1_force = False
    inventory = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--':
            i += 1
            break
        if a in ('-h', '--help'):
            sys.stdout.write(USAGE)
            return 0
        if a == '--version':
            sys.stdout.write('bashwin %s (Python %s, %s)\n' % (
                VERSION, sys.version.split()[0], sys.platform))
            return 0
        if a == '--applets':
            from . import applets, shbuiltins
            sys.stdout.write('shell builtins:\n  %s\n' % ' '.join(sorted(shbuiltins.BUILTINS)))
            sys.stdout.write('applets:\n  %s\n' % ' '.join(sorted(applets.REGISTRY)))
            return 0
        if a in ('-n', '--check'):
            check = True
        elif a == '--ps1-check':
            ps1 = True
        elif a == '--ps1':
            ps1_gen = True
        elif a == '--ps1-force':
            ps1_force = True
        elif a in ('--ps1-out', '--ps1-tools'):
            i += 1
            if i >= len(argv):
                sys.stderr.write('bashwin: %s: option requires an argument\n' % a)
                return 2
            if a == '--ps1-out':
                ps1_out = argv[i]
            elif argv[i] in ('block', 'external'):
                ps1_tools = argv[i]
            else:
                sys.stderr.write('bashwin: --ps1-tools: block or external\n')
                return 2
        elif a == '--inventory':
            inventory = True
        elif a == '-c':
            i += 1
            if i >= len(argv):
                sys.stderr.write('bashwin: -c: option requires an argument\n')
                return 2
            command = argv[i]
            i += 1
            break
        elif a == '-s':
            from_stdin = True
        elif a == '-o' or a == '+o':
            i += 1
            if i >= len(argv):
                sys.stderr.write('bashwin: -o: option requires an argument\n')
                return 2
            opts.append((a[0] == '-', 'o', argv[i]))
        elif len(a) > 1 and a[0] in '-+' and not a.startswith('--'):
            for ch in a[1:]:
                opts.append((a[0] == '-', ch, None))
        else:
            break
        i += 1
    rest = argv[i:]

    script = None
    if command is None and not from_stdin:
        if rest:
            script = rest[0]
            rest = rest[1:]
        else:
            from_stdin = True

    if ps1 or ps1_gen or inventory:
        if script is None:
            sys.stderr.write('bashwin: a script file is required\n')
            return 2
        if inventory:
            from .inventory import inventory_file
            return inventory_file(script)
        from .ps_emit import check_file, transpile_file
        if ps1_gen:
            return transpile_file(script, ps1_out, ps1_tools, ps1_force)
        return check_file(script, ps1_tools)

    if command is not None:
        argv0 = rest[0] if rest else 'bashwin'
        args = rest[1:]
    else:
        argv0 = script if script is not None else 'bashwin'
        args = rest

    _setup_threads()
    root = Root(argv0)
    sh = Interp(argv0=argv0, args=args, root=root)
    from . import shbuiltins
    for on, ch, name in opts:
        flag = ('-' if on else '+') + ch
        st = shbuiltins.b_set(sh, ['set', flag] + ([name] if name is not None else []))
        if st:
            return st

    if check:
        from .parser import parse, ParseError
        try:
            if command is not None:
                code = command
            elif script is not None:
                code = sh.read_script(script)
            else:
                code = sh.dec(sh.read_all(0))
            parse(code)
        except ParseError as e:
            sys.stderr.write('%s: line %d: %s\n' % (argv0, e.line, e.msg))
            return 2
        except OSError as e:
            sys.stderr.write('bashwin: %s: %s\n' % (script, e.strerror or e))
            return 127
        return 0

    result = [1]

    def work():
        try:
            if command is not None:
                result[0] = sh.run_code(command)
            elif script is not None:
                result[0] = sh.run_file(script)
            else:
                result[0] = sh.run_code(sh.dec(sh.read_all(0)))
        except BaseException:
            import traceback
            sys.stderr.write('bashwin: internal error\n' + traceback.format_exc())
            result[0] = 70

    def on_term(signum, frame):
        root.pending_signals.append('TERM')

    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError, AttributeError):
        pass
    t = threading.Thread(target=work)
    t.start()
    while t.is_alive():
        try:
            t.join(0.25)
        except KeyboardInterrupt:
            root.pending_signals.append('INT')
    root.cleanup()
    return result[0]


def entry():
    st = main(sys.argv[1:])
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(st or 0)
