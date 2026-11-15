#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Windows 固有ロジックの机上シミュレーション(Linux 上で ntpath を使って実行)。

注意: これは「Windows で動いた」ことの証明ではない。OS に触らない純粋なロジック
(終了コードの正規化、仮想パスの対応付け、起動方法の判定、パス結合)だけを、
Windows の規則(ntpath)に差し替えて確かめる。実機での確認は run_golden.py で行う。

    python tests/test_winlogic.py
"""
import ntpath
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bashwin import osdep  # noqa: E402

REAL_PATH = os.path
REAL_IS_WIN = osdep.IS_WIN


class _NtPathShim(object):
    """ntpath の規則で文字列処理しつつ、存在確認だけは実ファイルシステムに問い合わせる。"""

    def __getattr__(self, name):
        return getattr(ntpath, name)

    @staticmethod
    def _real(p):
        return p.replace('\\', '/')

    def isfile(self, p):
        return REAL_PATH.isfile(self._real(p))

    def isdir(self, p):
        return REAL_PATH.isdir(self._real(p))

    def exists(self, p):
        return REAL_PATH.exists(self._real(p))


class WinLogic(unittest.TestCase):
    def setUp(self):
        osdep.IS_WIN = True
        os.path = _NtPathShim()

    def tearDown(self):
        osdep.IS_WIN = REAL_IS_WIN
        os.path = REAL_PATH

    def test_norm_status(self):
        n = osdep.norm_status
        self.assertEqual(n(0), 0)
        self.assertEqual(n(1), 1)
        self.assertEqual(n(255), 255)
        self.assertEqual(n(256), 255)            # 下位 8bit が 0 でも「成功」に化けさせない
        self.assertEqual(n(0xC0000005), 5)       # アクセス違反
        self.assertEqual(n(0xC000013A), 0x3A)    # Ctrl+C
        self.assertEqual(n(16), 16)              # robocopy の 16 など
        self.assertEqual(n(65536), 255)
        self.assertNotEqual(n(-1), 0)

    def test_map_virtual(self):
        m = osdep.map_virtual
        self.assertEqual(m('/dev/null'), 'NUL')
        self.assertEqual(m('/c/Users/jun'), 'C:/Users/jun')
        self.assertEqual(m('/d'), 'D:/')
        self.assertEqual(m('/usr/bin'), '/usr/bin')          # 2 文字以上はドライブ扱いしない
        self.assertEqual(m('rel/path'), 'rel/path')
        self.assertEqual(m('C:/already'), 'C:/already')
        self.assertEqual(m('//server/share/x'), '//server/share/x')
        os.path = REAL_PATH
        tmp = tempfile.gettempdir().replace('\\', '/')
        os.path = _NtPathShim()
        self.assertEqual(m('/tmp'), tmp)
        self.assertEqual(m('/tmp/a/b.txt'), tmp + '/a/b.txt')
        self.assertEqual(m('/tmpx'), '/tmpx')

    def test_path_join_rules(self):
        cwd = 'C:/work/dir'
        j = os.path.join
        self.assertEqual(j(cwd, 'a/b').replace('\\', '/'), 'C:/work/dir/a/b')
        self.assertEqual(j(cwd, 'C:/x/y'), 'C:/x/y')
        self.assertEqual(j(cwd, 'D:/other'), 'D:/other')
        self.assertEqual(j(cwd, '//srv/share/f'), '//srv/share/f')
        self.assertEqual(j(cwd, osdep.map_virtual('/c/x')), 'C:/x')
        # cd の正規化(.. の解決)と表示形式
        self.assertEqual(osdep.unix_path(os.path.normpath(j(cwd, '../x'))), 'C:/work/x')
        self.assertEqual(osdep.unix_path(os.path.normpath(j(cwd, 'a/./b/..'))), 'C:/work/dir/a')
        self.assertEqual(osdep.unix_path('C:\\Users\\x'), 'C:/Users/x')

    def _tmpdir(self):
        # 一時ディレクトリの作成だけは本物の os.path で行う
        os.path = REAL_PATH
        try:
            return tempfile.mkdtemp(prefix='bwsim-')
        finally:
            os.path = _NtPathShim()

    def _rmtree(self, d):
        import shutil
        os.path = REAL_PATH
        try:
            shutil.rmtree(d, ignore_errors=True)
        finally:
            os.path = _NtPathShim()

    def _mk(self, d, name, content=b''):
        p = REAL_PATH.join(d, name)
        with open(p, 'wb') as f:
            f.write(content)
        return p

    def test_launch_spec(self):
        d = self._tmpdir()
        try:
            exe = self._mk(d, 'tool.exe')
            cmd = self._mk(d, 'job.cmd')
            ps1 = self._mk(d, 'job.ps1')
            py = self._mk(d, 'job.py')
            sh = self._mk(d, 'job.sh', b'echo hi\n')
            she = self._mk(d, 'tool', b'#!/usr/bin/env bash\necho hi\n')
            pyshe = self._mk(d, 'pytool', b'#!/usr/bin/python3\nprint(1)\n')
            plain = self._mk(d, 'noext', b'echo hi\n')
            ls = osdep.launch_spec
            self.assertEqual(ls(exe, ['tool', 'a']), ('exec', [exe, 'a']))
            kind, line = ls(cmd, ['job', 'a b', 'c'])
            self.assertEqual(kind, 'cmdline')
            self.assertIn('/d /s /c', line)
            self.assertIn('"a b"', line)
            self.assertTrue(line.rstrip().endswith('c"'))
            kind, argv = ls(ps1, ['job', 'x'])
            self.assertEqual(kind, 'exec')
            self.assertEqual(argv[0], 'powershell.exe')
            self.assertIn('-File', argv)
            self.assertNotIn('-ExecutionPolicy', argv)       # 実行ポリシーは回避しない
            self.assertEqual(ls(py, ['job'])[1][:2], [sys.executable, py])
            self.assertEqual(ls(sh, ['job']), ('script', sh))
            self.assertEqual(ls(she, ['tool']), ('script', she))
            self.assertEqual(ls(pyshe, ['pytool', 'z'])[1], [sys.executable, pyshe, 'z'])
            self.assertEqual(ls(plain, ['noext']), ('script', plain))
        finally:
            self._rmtree(d)

    def test_find_command_pathext(self):
        d = self._tmpdir()
        try:
            self._mk(d, 'tool.exe')
            self._mk(d, 'tool.cmd')
            self._mk(d, 'only.cmd')
            self._mk(d, 'script.sh')
            self._mk(d, 'bare')
            fc = osdep.find_command
            cwd = '/sim'      # ドライブ無しにして、実在する一時ディレクトリへ解決させる
            pathvar = 'Z:\\missing;' + d
            ext = '.COM;.EXE;.BAT;.CMD'
            self.assertTrue(fc('tool', pathvar, cwd, ext).replace('\\', '/').endswith('/tool.exe'))
            self.assertTrue(fc('only', pathvar, cwd, ext).replace('\\', '/').endswith('/only.cmd'))
            self.assertTrue(fc('tool.cmd', pathvar, cwd, ext).replace('\\', '/').endswith('/tool.cmd'))
            self.assertTrue(fc('script.sh', pathvar, cwd, ext).replace('\\', '/').endswith('/script.sh'))
            self.assertTrue(fc('bare', pathvar, cwd, ext).replace('\\', '/').endswith('/bare'))
            self.assertIsNone(fc('nothing', pathvar, cwd, ext))
            # PATH は ';' 区切り(':' では分割しない)
            self.assertIsNone(fc('tool', 'Z:\\missing:' + d, cwd, ext))
        finally:
            self._rmtree(d)

    def test_cmdline_quoting(self):
        import subprocess
        q = subprocess.list2cmdline
        self.assertEqual(q(['a b']), '"a b"')
        self.assertEqual(q(['q"x']), 'q\\"x')
        self.assertEqual(q(['']), '""')
        self.assertEqual(q(['C:\\dir\\', 'x']), 'C:\\dir\\ x')
        self.assertEqual(q(['C:\\my dir\\']), '"C:\\my dir\\\\"')


if __name__ == '__main__':
    unittest.main(verbosity=2)
