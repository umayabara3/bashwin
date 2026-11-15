#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""差分テスト: 同じスクリプトを「本物の bash」と「bashwin」で実行して突き合わせる。

  python3 tests/run_diff.py            # 全ケース実行、golden を更新、レポート出力
  python3 tests/run_diff.py -k array   # 名前に array を含むケースだけ
  python3 tests/run_diff.py -v         # 失敗ケースの差分を表示

比較対象は stdout(バイト一致)と終了コード。stderr は文言が違うので比較しない。
bashwin 側の PATH には python3 しか置かない => 内蔵コマンドだけで動くことの証明。
golden/ には bash の出力を保存し、bash の無い環境(Windows)での再生テストに使う。
"""
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


def load_cases(path):
    """'#### 名前 [タグ]' 区切りでケースを読む。"""
    cases = []
    name = None
    tags = []
    buf = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith('#### '):
                if name is not None:
                    cases.append((name, tags, ''.join(buf)))
                head = line[5:].strip()
                tags = []
                while head.endswith(']') and '[' in head:
                    k = head.rindex('[')
                    tags.append(head[k + 1:-1])
                    head = head[:k].strip()
                name = head
                buf = []
            elif name is not None:
                buf.append(line)
    if name is not None:
        cases.append((name, tags, ''.join(buf)))
    return cases


def run(cmd, script, env, timeout=30):
    d = tempfile.mkdtemp(prefix='bwcase-')
    try:
        with open(os.path.join(d, 'case.sh'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(script)
        e = dict(env)
        e['HOME'] = d
        e['TMPDIR'] = d
        try:
            p = subprocess.run(cmd + ['case.sh'], cwd=d, env=e, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            return p.stdout, p.returncode, p.stderr
        except subprocess.TimeoutExpired as ex:
            return (ex.stdout or b'') + b'<<TIMEOUT>>', -999, ex.stderr or b''
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-k', default='')
    ap.add_argument('-v', action='store_true')
    ap.add_argument('--no-golden', action='store_true')
    ap.add_argument('--report', default=os.path.join(HERE, 'REPORT_diff.md'))
    args = ap.parse_args()

    pybin = tempfile.mkdtemp(prefix='bwbin-')
    os.symlink(sys.executable, os.path.join(pybin, 'python3'))
    base_env = {'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TZ': 'UTC', 'PY': 'python3'}
    env_bash = dict(base_env, PATH='/usr/bin:/bin')
    env_bw = dict(base_env, PATH=pybin, PYTHONPATH=REPO, PYTHONDONTWRITEBYTECODE='1')
    bash_ver = subprocess.run(['bash', '--version'], stdout=subprocess.PIPE).stdout.decode().split('\n')[0]

    results = []
    differs = []
    t0 = time.time()
    for fn in sorted(os.listdir(SPEC)):
        if not fn.endswith('.sh'):
            continue
        gold = {}
        for name, tags, script in load_cases(os.path.join(SPEC, fn)):
            if args.k and args.k not in name and args.k not in fn:
                continue
            if 'own' in tags:
                # bashwin 固有機能: bash では動かさず、スクリプト内の '#= ' 行を期待値にする
                exp = ''.join(l[3:] + '\n' for l in script.split('\n') if l.startswith('#= '))
                eo, erc, eerr = exp.encode('utf-8'), 0, b''
            else:
                eo, erc, eerr = run(['bash'], script, env_bash)
            ao, arc, aerr = run([sys.executable, '-m', 'bashwin'], script, env_bw)
            ok = (eo == ao and erc == arc)
            if 'differs' in tags:
                # 設計上あえて bash と違う挙動。合否には数えず、bashwin 側の出力を golden にする
                differs.append((fn, name, script, eo, erc, ao, arc))
                gold[name] = {'tags': tags, 'rc': arc,
                              'stdout_b64': base64.b64encode(ao).decode('ascii')}
                continue
            results.append((fn, name, ok))
            gold[name] = {'tags': tags, 'rc': erc,
                          'stdout_b64': base64.b64encode(eo).decode('ascii')}
            if not ok:
                print('FAIL %s :: %s' % (fn, name))
                if args.v:
                    print('  --- bash    rc=%s\n%s' % (erc, eo.decode('utf-8', 'replace')))
                    print('  --- bashwin rc=%s\n%s' % (arc, ao.decode('utf-8', 'replace')))
                    if aerr.strip():
                        print('  --- bashwin stderr\n%s' % aerr.decode('utf-8', 'replace')[-1500:])
        if not args.k and not args.no_golden:
            with open(os.path.join(GOLD, fn[:-3] + '.json'), 'w', encoding='utf-8') as f:
                json.dump(gold, f, indent=1, sort_keys=True)
    shutil.rmtree(pybin, ignore_errors=True)
    total = len(results)
    passed = sum(1 for r in results if r[2])
    print('\n%d/%d passed (%.1fs)  reference: %s' % (passed, total, time.time() - t0, bash_ver))
    if not args.k:
        by_file = {}
        for fn, name, ok in results:
            a = by_file.setdefault(fn, [0, 0, []])
            a[0] += 1
            a[1] += ok
            if not ok:
                a[2].append(name)
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write('# 差分テスト結果(bash 実物との突き合わせ)\n\n')
            f.write('- 基準: `%s`\n- 対象: bashwin on Python %s (%s)\n' % (
                bash_ver, sys.version.split()[0], sys.platform))
            f.write('- 判定: stdout のバイト一致 + 終了コード一致\n')
            f.write('- 結果: **%d / %d 合格**\n\n' % (passed, total))
            f.write('| ファイル | ケース数 | 合格 | 不一致 |\n|---|---:|---:|---|\n')
            for fn in sorted(by_file):
                a = by_file[fn]
                f.write('| %s | %d | %d | %s |\n' % (fn, a[0], a[1], ', '.join(a[2]) or '-'))
            if differs:
                f.write('\n## 設計上の差異(合否に数えない)\n\n')
                for fn, name, script, eo, erc, ao, arc in differs:
                    f.write('### %s\n\n```sh\n%s```\n\n' % (name, script))
                    f.write('| | 終了コード | stdout |\n|---|---:|---|\n')
                    f.write('| bash | %d | `%s` |\n' % (erc, eo.decode('utf-8', 'replace').replace('\n', '\\n')))
                    f.write('| bashwin | %d | `%s` |\n\n' % (arc, ao.decode('utf-8', 'replace').replace('\n', '\\n')))
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
