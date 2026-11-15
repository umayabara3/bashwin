# -*- coding: utf-8 -*-
"""アプレット共通の部品(オプション解析、入力の逐次読み、出力バッファ)。"""
from __future__ import unicode_literals

import functools
import os


class UsageError(Exception):
    pass


def applet(fn=None, usage=1):
    """アプレット用デコレータ。UsageError を「コマンド名: メッセージ」+ 終了コードに変換する。
    使い方エラーの終了コードは GNU に合わせる(多くは 1、grep/sort/diff 等は 2)。"""
    def deco(f):
        @functools.wraps(f)
        def wrapper(sh, argv):
            try:
                return f(sh, argv) or 0
            except UsageError as e:
                sh.err('%s: %s\n' % (argv[0], e))
                return usage
        return wrapper
    if fn is not None:
        return deco(fn)
    return deco


def getopt(args, short, longmap=None, posix=False):
    """GNU 風オプション解析。[(文字, 値|True)], 残り引数 を返す。

    short は 'nrk:t:' 形式。longmap は {'ignore-case': 'i'} のような長い名前の対応表。
    posix=True なら最初の非オプションで解析を止める(xargs, env など)。
    """
    takes = set()
    flags = set()
    j = 0
    while j < len(short):
        c = short[j]
        if j + 1 < len(short) and short[j + 1] == ':':
            takes.add(c)
            j += 2
        else:
            flags.add(c)
            j += 1
    opts = []
    rest = []
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if a == '--':
            rest.extend(args[i + 1:])
            break
        if a.startswith('--') and len(a) > 2:
            name, eq, val = a[2:].partition('=')
            if longmap is None or name not in longmap:
                raise UsageError("unrecognized option '--%s'" % name)
            c = longmap[name]
            if c in takes:
                if not eq:
                    i += 1
                    if i >= n:
                        raise UsageError("option '--%s' requires an argument" % name)
                    val = args[i]
                opts.append((c, val))
            else:
                opts.append((c, True))
        elif len(a) > 1 and a[0] == '-':
            k = 1
            while k < len(a):
                c = a[k]
                if c in takes:
                    val = a[k + 1:]
                    if not val:
                        i += 1
                        if i >= n:
                            raise UsageError("option requires an argument -- '%s'" % c)
                        val = args[i]
                    opts.append((c, val))
                    break
                elif c in flags:
                    opts.append((c, True))
                    k += 1
                else:
                    raise UsageError("invalid option -- '%s'" % c)
        else:
            if posix:
                rest.extend(args[i:])
                break
            rest.append(a)
        i += 1
    return opts, rest


class Out(object):
    """出力バッファ。行ごとの write システムコールを避ける。"""

    def __init__(self, sh, fd=1):
        self.sh = sh
        self.fd = fd
        self.buf = []
        self.size = 0

    def write(self, s):
        self.buf.append(s)
        self.size += len(s)
        if self.size > 65536:
            self.flush()

    def flush(self):
        if self.buf:
            data = ''.join(self.buf)
            self.buf = []
            self.size = 0
            self.sh.write_fd(self.fd, self.sh.enc(data))


def open_inputs(sh, cmd, files, errs):
    """(名前, バイナリファイル) を順に返す。'-' と引数なしは標準入力。"""
    if not files:
        files = ['-']
    for name in files:
        if name == '-':
            f = sh.fds.get(0)
            if f is not None:
                yield name, f
            continue
        p = sh.abspath(name)
        try:
            if os.path.isdir(p):
                raise IsADirectoryError(21, 'Is a directory')
            f = open(p, 'rb', buffering=0)
        except OSError as e:
            sh.err('%s: %s: %s\n' % (cmd, name, e.strerror or e))
            errs.append(1)
            continue
        try:
            yield name, f
        finally:
            f.close()


def iter_chunks(f):
    while True:
        try:
            b = f.read(65536)
        except OSError:
            break
        if not b:
            break
        yield b


def iter_lines(sh, f, out=None):
    """行(改行を除いた str)と「改行で終わっていたか」を返す。

    次の塊を待つ前に out を flush するので、パイプの途中でも出力が滞らない。
    """
    buf = b''
    dec = sh.dec
    while True:
        if out is not None and out.buf:
            out.flush()
        try:
            chunk = f.read(65536)
        except OSError:
            chunk = b''
        if not chunk:
            break
        if b'\n' in chunk:
            parts = (buf + chunk).split(b'\n')
            buf = parts.pop()
            for p in parts:
                yield dec(p), True
        else:
            buf += chunk
    if buf:
        yield dec(buf), False


def read_text(sh, cmd, files, errs):
    """全入力を連結した str を返す(小さな入力向け)。"""
    chunks = []
    for name, f in open_inputs(sh, cmd, files, errs):
        chunks.extend(iter_chunks(f))
    return sh.dec(b''.join(chunks))


def split_lines(text):
    """str -> 行のリスト(末尾の改行 1 個は行を作らない)。"""
    if not text:
        return []
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    return lines


def to_int(s, what='number'):
    try:
        return int(s)
    except ValueError:
        raise UsageError("invalid %s: '%s'" % (what, s))
