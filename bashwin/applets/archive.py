# -*- coding: utf-8 -*-
"""圧縮・アーカイブ系アプレット: gzip gunzip zcat tar zip unzip(標準ライブラリのみ)。"""
from __future__ import unicode_literals

import gzip as _gzip
import io
import os
import tarfile
import zipfile

from .. import osdep
from .common import applet, getopt, UsageError, iter_chunks


@applet
def a_gzip(sh, argv):
    opts, files = getopt(argv[1:], 'dckfv123456789nq', {'decompress': 'd', 'stdout': 'c',
                                                        'keep': 'k', 'force': 'f'})
    o = dict(opts)
    name0 = argv[0]
    decomp = 'd' in o or name0 in ('gunzip', 'zcat')
    to_stdout = 'c' in o or name0 == 'zcat'
    level = 6
    for c in '123456789':
        if c in o:
            level = int(c)
    if not files:
        data = sh.read_all(0)
        try:
            sh.out_bytes(_gzip.decompress(data) if decomp
                         else _gzip.compress(data, level, mtime=0))
        except (OSError, EOFError) as e:
            sh.err('%s: stdin: %s\n' % (name0, e))
            return 1
        return 0
    st = 0
    for n in files:
        p = sh.abspath(n)
        try:
            with open(p, 'rb') as f:
                data = f.read()
            res = _gzip.decompress(data) if decomp else _gzip.compress(data, level, mtime=0)
            if to_stdout:
                sh.out_bytes(res)
                continue
            dst = (p[:-3] if p.endswith('.gz') else p + '.out') if decomp else p + '.gz'
            if os.path.exists(dst) and 'f' not in o:
                sh.err('%s: %s already exists; not overwritten\n' % (name0, os.path.basename(dst)))
                st = 1
                continue
            with open(dst, 'wb') as f:
                f.write(res)
            if 'k' not in o:
                os.remove(p)
        except (OSError, EOFError) as e:
            sh.err('%s: %s: %s\n' % (name0, n, getattr(e, 'strerror', None) or e))
            st = 1
    return st


a_gunzip = a_gzip
a_zcat = a_gzip


@applet
def a_tar(sh, argv):
    args = argv[1:]
    if args and not args[0].startswith('-'):
        args = ['-' + args[0]] + args[1:]
    opts, names = getopt(args, 'cxtzjJvf:C:pO', {'create': 'c', 'extract': 'x', 'list': 't',
                                                 'gzip': 'z', 'bzip2': 'j', 'xz': 'J',
                                                 'verbose': 'v', 'file': 'f', 'directory': 'C',
                                                 'exclude': 'X'})
    o = dict(opts)
    archive = o.get('f', '-')
    comp = 'gz' if 'z' in o else ('bz2' if 'j' in o else ('xz' if 'J' in o else ''))
    base = sh.abspath(o['C']) if 'C' in o else sh.cwd
    try:
        if 'c' in o:
            if not comp:
                for ext, c in (('.tar.gz', 'gz'), ('.tgz', 'gz'), ('.tar.bz2', 'bz2'),
                               ('.tar.xz', 'xz')):
                    if archive.endswith(ext):
                        comp = c
            buf = io.BytesIO() if archive == '-' else None
            tf = tarfile.open(fileobj=buf, mode='w:' + comp) if buf is not None else \
                tarfile.open(sh.abspath(archive), 'w:' + comp)
            with tf:
                for n in names:
                    tf.add(os.path.join(base, n), arcname=n.replace('\\', '/'))
                    if 'v' in o:
                        sh.err(n + '\n')
            if buf is not None:
                sh.out_bytes(buf.getvalue())
            return 0
        if archive == '-':
            tf = tarfile.open(fileobj=io.BytesIO(sh.read_all(0)), mode='r:*')
        else:
            tf = tarfile.open(sh.abspath(archive), 'r:*')
        with tf:
            members = tf.getmembers()
            if names:
                wanted = [n.rstrip('/') for n in names]
                members = [m for m in members if any(
                    m.name == w or m.name.startswith(w + '/') for w in wanted)]
            if 't' in o:
                sh.out(''.join(m.name + ('/' if m.isdir() else '') + '\n' for m in members))
                return 0
            if 'x' in o:
                root = os.path.realpath(base)
                for m in members:
                    dest = os.path.realpath(os.path.join(base, m.name))
                    if not (dest == root or dest.startswith(root + os.sep)):
                        sh.err("tar: %s: refusing to extract outside the target directory\n"
                               % m.name)
                        return 2
                    if m.issym() or m.islnk():
                        link = os.path.realpath(os.path.join(os.path.dirname(dest), m.linkname))
                        if not (link == root or link.startswith(root + os.sep)):
                            sh.err("tar: %s: refusing link pointing outside\n" % m.name)
                            return 2
                    if 'O' in o:
                        f = tf.extractfile(m)
                        if f is not None:
                            sh.out_bytes(f.read())
                        continue
                    tf.extract(m, base)
                    if 'v' in o:
                        sh.out(m.name + '\n')
                return 0
        raise UsageError('You must specify one of the -c, -x, -t options')
    except (OSError, tarfile.TarError) as e:
        sh.err('tar: %s\n' % (getattr(e, 'strerror', None) or e))
        return 2


@applet
def a_zip(sh, argv):
    opts, names = getopt(argv[1:], 'rqj0123456789', {})
    o = dict(opts)
    if len(names) < 2:
        raise UsageError('usage: zip [-r] [-q] [-j] archive.zip files...')
    archive = sh.abspath(names[0])
    comp = zipfile.ZIP_STORED if '0' in o else zipfile.ZIP_DEFLATED
    st = 0
    with zipfile.ZipFile(archive, 'a' if os.path.exists(archive) else 'w', comp) as zf:
        def add(disp, full):
            arc = os.path.basename(disp) if 'j' in o else disp.replace('\\', '/').lstrip('/')
            if os.path.isdir(full):
                if 'r' in o:
                    for nm in sorted(os.listdir(full)):
                        add(disp.rstrip('/') + '/' + nm, os.path.join(full, nm))
                return
            zf.write(full, arc)
            if 'q' not in o:
                sh.out('  adding: %s\n' % arc)
        for n in names[1:]:
            full = sh.abspath(n)
            if not os.path.exists(full):
                sh.err('zip warning: name not matched: %s\n' % n)
                st = 12
                continue
            add(n, full)
    return st


@applet
def a_unzip(sh, argv):
    opts, names = getopt(argv[1:], 'lqod:p', {})
    o = dict(opts)
    if not names:
        raise UsageError('usage: unzip [-l] [-q] [-o] [-d dir] archive.zip')
    dest = sh.abspath(o['d']) if 'd' in o else sh.cwd
    try:
        with zipfile.ZipFile(sh.abspath(names[0])) as zf:
            infos = zf.infolist()
            if len(names) > 1:
                infos = [i for i in infos if i.filename in names[1:]]
            if 'l' in o:
                sh.out(''.join('%9d  %s\n' % (i.file_size, i.filename) for i in infos))
                return 0
            root = os.path.realpath(dest)
            for i in infos:
                target = os.path.realpath(os.path.join(dest, i.filename))
                if not (target == root or target.startswith(root + os.sep)):
                    sh.err('unzip: %s: refusing to extract outside the target directory\n'
                           % i.filename)
                    return 2
                if 'p' in o:
                    sh.out_bytes(zf.read(i))
                    continue
                if os.path.exists(target) and not os.path.isdir(target) and 'o' not in o:
                    sh.err('unzip: %s already exists (use -o to overwrite)\n' % i.filename)
                    return 1
                zf.extract(i, dest)
                if 'q' not in o:
                    sh.out('  inflating: %s\n' % i.filename)
    except (OSError, zipfile.BadZipFile) as e:
        sh.err('unzip: %s\n' % (getattr(e, 'strerror', None) or e))
        return 9
    return 0
