# -*- coding: utf-8 -*-
"""内蔵コマンド(アプレット)。Windows に無い coreutils 相当を Python で提供する。

REGISTRY は 名前 -> (モジュール, 関数名)。起動時間を抑えるため遅延 import。
"""
import importlib

REGISTRY = {}
_loaded = {}


def register(module, names):
    for n in names.split():
        REGISTRY[n] = (module, 'a_' + n.replace('-', '_').replace('[', 'lb'))


def get(name):
    fn = _loaded.get(name)
    if fn is None:
        mod, attr = REGISTRY[name]
        fn = getattr(importlib.import_module('.' + mod, __name__), attr)
        _loaded[name] = fn
    return fn


register('textutils', 'cat head tail wc sort uniq cut tr tee grep egrep fgrep rev tac nl paste '
                      'seq yes base64 dos2unix unix2dos iconv md5sum sha1sum sha256sum '
                      'sha512sum diff cmp expr od')
register('sed', 'sed')
register('awk', 'awk')
register('fileutils', 'ls mkdir rmdir rm cp mv touch ln chmod chown chgrp mktemp realpath '
                      'readlink basename dirname find stat du')
register('sysutils', 'date sleep env printenv which xargs timeout hostname whoami uname id '
                     'nproc tput winpath cygpath sh bash')
register('archive', 'gzip gunzip zcat tar zip unzip')
