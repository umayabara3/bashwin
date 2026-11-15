#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ゴールデン再生テスト(bash が無い環境 = Windows 実機用の計測キット)。

tests/golden/*.json には「本物の bash 5.2 が出した stdout と終了コード」が入っている。
このスクリプトは同じケースを手元の Python + bashwin で実行して突き合わせる。

    python tests/run_golden.py              # 全ケース
    python tests/run_golden.py -k awk -v    # 絞り込み + 差分表示
    python tests/run_golden.py --report out.md
    python tests/run_golden.py --pyz dist/bashwin.pyz   # 配布物そのものを検査

Windows では [posix] タグ付きケース(シンボリックリンク、パーミッションビット、
大文字小文字を区別するファイル名など)を自動で除外する。
"""
from __future__ import print_function

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SPEC = os.path.join(HERE, 'spec')
GOLD = os.path.join(HERE, 'golden')
IS_WIN = os.name == 'nt'


def load_cases(path):
    cases = {}
    name = None
    buf = []
    with open(path, 'rb') as f:
        text = f.read().decode('utf-8').replace('\r\n', '\n')
    for line in text.split('\n'):
        if line.startswith('#### '):
            if name is not None:
                cases[name] = '\n'.join(buf) + '\n'
            head = line[5:].strip()
            while head.endswith(']') and '[' in head:
                head = head[:head.rindex('[')].strip()
            name = head
            buf = []
        elif name is not None:
            buf.append(line)
    if name is not None:
        cases[name] = '\n'.join(buf)
    return cases


RUNNER = [sys.executable, '-m', 'bashwin']


def run_case(script, env, timeout):
    d = os.path.realpath(tempfile.mkdtemp(prefix='bwcase-'))
    try:
        with open(os.path.join(d, 'case.sh'), 'wb') as f:
            f.write(script.encode('utf-8'))
        e = dict(env)
        home = d.replace('\\', '/')
        e['HOME'] = home
        e['TMPDIR'] = home
        try:
            p = subprocess.Popen(RUNNER + ['case.sh'], cwd=d, env=e,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            out, err = p.communicate(timeout=timeout)
            return out, p.returncode, err
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
            return out + b'<<TIMEOUT>>', -999, err
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-k', default='', help='ケース名/ファイル名の部分一致で絞り込む')
    ap.add_argument('-v', action='store_true', help='不一致の内容を表示する')
    ap.add_argument('--timeout', type=int, default=60)
    ap.add_argument('--report', default=None, help='Markdown レポートの出力先')
    ap.add_argument('--pyz', default=None, help='ソースではなく配布物 bashwin.pyz で実行する')
    args = ap.parse_args()
    if args.pyz:
        RUNNER[:] = [sys.executable, os.path.abspath(args.pyz)]

    env = dict(os.environ)
    for k in list(env):
        if k.startswith('BASHWIN_') or k in ('BASH_ENV', 'ENV', 'IFS'):
            del env[k]
    pydir = os.path.dirname(sys.executable)
    env.update({'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
                'PY': sys.executable.replace('\\', '/'), 'PYTHONPATH': REPO,
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'})
    if IS_WIN:
        env['PATH'] = pydir       # 外部コマンドに頼らず内蔵コマンドだけで動くことを確かめる
    else:
        binroot = tempfile.mkdtemp(prefix='bwbin-')
        env['PATH'] = binroot

    results = []
    skipped = 0
    t0 = time.time()
    for fn in sorted(os.listdir(GOLD)):
        if not fn.endswith('.json'):
            continue
        with open(os.path.join(GOLD, fn), encoding='utf-8') as f:
            gold = json.load(f)
        scripts = load_cases(os.path.join(SPEC, fn[:-5] + '.sh'))
        for name in sorted(gold):
            if args.k and args.k not in name and args.k not in fn:
                continue
            g = gold[name]
            if IS_WIN and 'posix' in g.get('tags', []):
                skipped += 1
                continue
            exp_out = base64.b64decode(g['stdout_b64'])
            out, rc, err = run_case(scripts[name], env, args.timeout)
            ok = out == exp_out and rc == g['rc']
            results.append((fn, name, ok, exp_out, g['rc'], out, rc, err))
            if not ok:
                print('FAIL %s :: %s' % (fn, name))
                if args.v:
                    print('  --- expected rc=%s\n%s' % (g['rc'], exp_out.decode('utf-8', 'replace')))
                    print('  --- actual   rc=%s\n%s' % (rc, out.decode('utf-8', 'replace')))
                    if err.strip():
                        print('  --- stderr\n%s' % err.decode('utf-8', 'replace')[-1500:])
    total = len(results)
    passed = sum(1 for r in results if r[2])
    summary = '%d/%d passed, %d skipped (%.1fs)  Python %s on %s' % (
        passed, total, skipped, time.time() - t0, sys.version.split()[0], sys.platform)
    print('\n' + summary)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write('# ゴールデン再生テスト結果\n\n- %s\n- 実行ファイル: `%s`\n\n' % (summary,
                                                                              sys.executable))
            fails = [r for r in results if not r[2]]
            if not fails:
                f.write('不一致なし。\n')
            for fn, name, ok, eo, erc, ao, arc, err in fails:
                f.write('## %s :: %s\n\n期待 (rc=%s)\n```\n%s\n```\n実際 (rc=%s)\n```\n%s\n```\n' % (
                    fn, name, erc, eo.decode('utf-8', 'replace'), arc,
                    ao.decode('utf-8', 'replace')))
                if err.strip():
                    f.write('stderr\n```\n%s\n```\n' % err.decode('utf-8', 'replace')[-1500:])
                f.write('\n')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
