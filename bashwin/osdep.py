# -*- coding: utf-8 -*-
"""OS 依存の処理(Windows / POSIX の差をここに閉じ込める)。

方針:
  * プロセスのカレントディレクトリは変更しない(os.chdir しない)。
    インタープリターは論理 cwd を持ち、ファイル操作は常に絶対パスに解決する。
    => サブシェルやパイプライン段をスレッドで安全に動かせる。
  * Windows でも区切りは '/' を正とする('\\' は bash ではエスケープ文字)。
  * MSYS のような暗黙のパス書き換えは外部コマンドの引数には行わない。
    対象は bashwin 自身が開くパスだけ(/dev/null, /tmp, /c/...)。
"""
import os
import subprocess
import sys
import tempfile

IS_WIN = os.name == 'nt'
_SHELLS = ('sh', 'bash', 'dash', 'ash', 'ksh', 'bashwin')
_PATHMAP = os.environ.get('BASHWIN_PATHMAP', '1') != '0'


def unix_path(p):
    return p.replace('\\', '/') if IS_WIN else p


def norm_status(rc):
    """子プロセスの終了コードを 0-255 に正規化する。

    Windows の終了コードは 32bit。下位 8bit が 0 でも元が非 0 なら 255 にして、
    「失敗が成功に見える」事故(例: 256 -> 0)を防ぐ。
    """
    if rc < 0:
        if IS_WIN:
            return (rc & 0xFF) or 255
        return 128 + (-rc)
    if rc > 255:
        return (rc & 0xFF) or 255
    return rc


def map_virtual(p):
    """bashwin 自身が開くパスの仮想マッピング(Windows のみ)。"""
    if not IS_WIN or not _PATHMAP or not p.startswith('/'):
        return p
    if p == '/dev/null':
        return 'NUL'
    if p == '/tmp' or p.startswith('/tmp/'):
        return unix_path(tempfile.gettempdir()) + p[4:]
    if len(p) >= 2 and p[1].isalpha() and (len(p) == 2 or p[2] == '/'):
        return p[1].upper() + ':' + (p[2:] or '/')
    return p


def find_command(name, pathvar, cwd, pathext=None):
    """PATH からコマンドを探して絶対パスを返す。無ければ None。"""
    if IS_WIN:
        exts = [e.lower() for e in (pathext or '.COM;.EXE;.BAT;.CMD').split(';') if e]
        has_sep = '/' in name or '\\' in name
        dirs = [None] if has_sep else [d for d in (pathvar or '').split(';') if d]
        cur_ext = os.path.splitext(name)[1].lower()
        for d in dirs:
            base = os.path.join(cwd, map_virtual(name)) if d is None \
                else os.path.join(cwd, d, name)
            cands = []
            if cur_ext:
                cands.append(base)
            cands.extend(base + e for e in exts)
            if not cur_ext:
                cands.append(base)
            for c in cands:
                if os.path.isfile(c):
                    return c
        return None
    if '/' in name:
        p = os.path.join(cwd, name)
        return p if os.path.isfile(p) else None
    for d in (pathvar or '').split(':'):
        p = os.path.join(cwd, d or '.', name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _shebang(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(256)
    except OSError:
        return None
    if not head.startswith(b'#!'):
        return None
    line = head.split(b'\n', 1)[0].decode('utf-8', 'replace').strip()
    parts = line[2:].split()
    if not parts:
        return None
    interp = os.path.basename(parts[0].replace('\\', '/'))
    rest = parts[1:]
    if interp == 'env':
        rest = [x for x in rest if not x.startswith('-')]
        if not rest:
            return None
        interp = os.path.basename(rest[0])
        rest = rest[1:]
    return interp, rest


def launch_spec(path, argv):
    """起動方法を決める。

    ('script', path)        : bashwin 自身がプロセス内で実行する sh/bash スクリプト
    ('exec', [argv...])     : そのまま起動
    ('cmdline', str)        : Windows のコマンドライン文字列で起動(.bat/.cmd)
    """
    ext = os.path.splitext(path)[1].lower()
    if IS_WIN:
        if ext in ('.exe', '.com'):
            return ('exec', [path] + argv[1:])
        if ext in ('.bat', '.cmd'):
            comspec = os.environ.get('COMSPEC') or 'cmd.exe'
            inner = subprocess.list2cmdline([path.replace('/', '\\')] + argv[1:])
            return ('cmdline', '"%s" /d /s /c "%s"' % (comspec, inner))
        if ext == '.ps1':
            # 実行ポリシーの回避フラグは付けない(統制は環境側の設定に従う)
            return ('exec', ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', path]
                    + argv[1:])
        if ext in ('.py', '.pyw'):
            return ('exec', [sys.executable, path] + argv[1:])
    sb = _shebang(path)
    if sb is not None:
        interp, rest = sb
        if interp in _SHELLS:
            return ('script', path)
        if IS_WIN:
            if interp.startswith('python'):
                return ('exec', [sys.executable, path] + argv[1:])
            return ('exec', [interp] + rest + [path] + argv[1:])
        return ('exec', [path] + argv[1:])
    if IS_WIN and ext in ('.sh', ''):
        return ('script', path)
    return ('exec', [path] + argv[1:])


def default_home():
    h = os.environ.get('HOME')
    if h:
        return unix_path(h)
    if IS_WIN:
        h = os.environ.get('USERPROFILE')
        if h:
            return unix_path(h)
    return unix_path(os.path.expanduser('~'))


def is_executable(path):
    if IS_WIN:
        if os.path.isdir(path):
            return True
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        exts = [e.lower() for e in os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD').split(';')]
        return ext in exts or ext in ('.sh', '.py', '.ps1') or _shebang(path) is not None
    return os.access(path, os.X_OK)
