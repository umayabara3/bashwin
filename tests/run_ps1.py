#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""トランスパイラーの実行検証: 変換 -> PowerShell で実行 -> 正解データ(golden)と突き合わせ。

    python tests/run_ps1.py [--report tests/REPORT_ps1.md] [-k 絞り込み] [-v]

テストケース(tests/spec)のうち変換可能なものを .ps1 に変換し、PowerShell で実行して、
本物の bash から取った正解データ(tests/golden: 標準出力のバイト列と終了コード)と比べる。
Windows では powershell.exe(Windows PowerShell 5.1)、それ以外では pwsh を使う。

実行ポリシーの回避フラグは付けない。ローカルの未署名スクリプトを実行できない設定
(Restricted / AllSigned)の場合は、その旨を表示して終了する。
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
sys.path.insert(0, REPO)
IS_WIN = os.name == 'nt'

from bashwin.ps_emit import transpile  # noqa: E402
from run_golden import load_cases  # noqa: E402

# bash と意図的に違う動きをするケース(理由つき)。失敗には数えず、レポートに別枠で載せる。
BY_DESIGN = {
    ('13_edge.sh', 'arithmetic division by zero'):
        '展開エラー(0 除算)のとき bash は「その行の残り」だけを捨てて続行するが、'
        '生成物は安全側に倒して終了コード 1 でスクリプトを止める',
}


def find_powershell(arg):
    if arg:
        return arg
    for name in (('powershell.exe', 'pwsh.exe') if IS_WIN else ('pwsh', 'powershell')):
        p = shutil.which(name)
        if p:
            return p
    return None


def run_ps(ps, extra, path, cwd, env, timeout):
    cmd = [ps, '-NoProfile', '-NonInteractive'] + extra + ['-File', path]
    try:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(timeout=timeout)
        return out, p.returncode, err
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        return out + b'<<TIMEOUT>>', -999, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ps', default=None, help='PowerShell の実行ファイル(既定: powershell.exe / pwsh)')
    ap.add_argument('--execution-policy', default=None,
                    help='指定したときだけ -ExecutionPolicy <値> を付ける(既定では付けない)')
    ap.add_argument('-k', default='', help='ケース名/ファイル名の部分一致で絞り込む')
    ap.add_argument('-v', action='store_true', help='不一致の内容を表示する')
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--report', default=None, help='Markdown レポートの出力先')
    ap.add_argument('--keep', default=None, help='生成した .ps1 を残すフォルダ')
    ap.add_argument('--list', action='store_true', help='変換可能なケースの一覧だけ出す(実行しない)')
    args = ap.parse_args()

    # ---- 変換(PowerShell が無くてもここまでは動く)
    todo = []
    rejected = 0
    for fn in sorted(os.listdir(GOLD)):
        if not fn.endswith('.json') or fn.startswith(('80_', '90_')):
            continue
        with open(os.path.join(GOLD, fn), encoding='utf-8') as f:
            gold = json.load(f)
        spec = fn[:-5] + '.sh'
        scripts = load_cases(os.path.join(SPEC, spec))
        for name in sorted(gold):
            if args.k and args.k not in name and args.k not in fn:
                continue
            g = gold[name]
            if IS_WIN and 'posix' in g.get('tags', []):
                continue
            text, problems, err = transpile(scripts[name], 'case.sh')
            if text is None:
                rejected += 1
                continue
            todo.append((spec, name, text, base64.b64decode(g['stdout_b64']), g['rc']))
    print('transpilable: %d case(s); outside the subset: %d' % (len(todo), rejected))
    if args.keep:
        os.makedirs(args.keep, exist_ok=True)
        for k, (spec, name, text, eo, erc) in enumerate(todo):
            with open(os.path.join(args.keep, '%03d_%s.ps1' % (k, spec[:2])), 'wb') as f:
                f.write(('# %s :: %s\n' % (spec, name)).encode('ascii', 'replace') + text.encode('ascii'))
    if args.list:
        for spec, name, text, eo, erc in todo:
            print('  %s :: %s' % (spec, name))
        return 0

    ps = find_powershell(args.ps)
    if not ps:
        print('PowerShell が見つかりません(--ps で場所を指定してください)。')
        return 2
    extra = ['-ExecutionPolicy', args.execution_policy] if args.execution_policy else []
    env = dict(os.environ)
    for k in list(env):
        if k.startswith('BASHWIN_') or k in ('BASH_ENV', 'ENV', 'IFS'):
            del env[k]
    env.update({'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
                'PY': sys.executable.replace('\\', '/'), 'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONIOENCODING': 'utf-8', 'POWERSHELL_UPDATECHECK': 'Off'})
    if not IS_WIN:
        env.setdefault('DOTNET_SYSTEM_GLOBALIZATION_INVARIANT', '1')

    # ---- 事前確認: PowerShell のバージョンと、スクリプトを実行できる設定か
    probe = os.path.realpath(tempfile.mkdtemp(prefix='bwps1-'))
    try:
        with open(os.path.join(probe, 'probe.ps1'), 'wb') as f:
            f.write(b"[System.Console]::Out.Write('probe-ok ' + $PSVersionTable.PSVersion.ToString())\n"
                    b"exit 7\n")
        out, rc, err = run_ps(ps, extra, os.path.join(probe, 'probe.ps1'), probe, env, args.timeout)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if rc != 7 or not out.startswith(b'probe-ok'):
        print('PowerShell でスクリプトを実行できませんでした: %s' % ps)
        print('  終了コード %s / 出力 %r' % (rc, out[:200]))
        print('  エラー出力:\n%s' % err.decode('utf-8', 'replace')[-1500:])
        print('  実行ポリシーが Restricted / AllSigned の場合、未署名のローカルスクリプトは実行できません。\n'
              '  管理者に確認のうえ、許可された方法(署名する、RemoteSigned の端末で実行する、または\n'
              '  --execution-policy で明示的に指定する)で再実行してください。')
        return 2
    version = out.decode('ascii', 'replace').split(' ', 1)[1].strip()
    print('PowerShell %s (%s)' % (version, ps))

    results = []
    t0 = time.time()
    for spec, name, text, exp_out, exp_rc in todo:
        d = os.path.realpath(tempfile.mkdtemp(prefix='bwps1-'))
        try:
            with open(os.path.join(d, 'case.ps1'), 'wb') as f:
                f.write(text.encode('ascii'))
            e = dict(env)
            e['HOME'] = d.replace('\\', '/')
            e['TMPDIR'] = e['HOME']
            out, rc, err = run_ps(ps, extra, os.path.join(d, 'case.ps1'), d, e, args.timeout)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        ok = out == exp_out and rc == exp_rc
        why = BY_DESIGN.get((spec, name))
        results.append((spec, name, ok, why, exp_out, exp_rc, out, rc, err))
        if not ok:
            print('%s %s :: %s' % ('DIFF(by design)' if why else 'FAIL', spec, name))
            if args.v:
                print('  --- expected rc=%s\n%s' % (exp_rc, exp_out.decode('utf-8', 'replace')))
                print('  --- actual   rc=%s\n%s' % (rc, out.decode('utf-8', 'replace')))
                if err.strip():
                    print('  --- stderr\n%s' % err.decode('utf-8', 'replace')[-1500:])
    counted = [r for r in results if not r[3]]
    passed = sum(1 for r in counted if r[2])
    fails = [r for r in counted if not r[2]]
    design = [r for r in results if r[3]]
    summary = '%d/%d passed, %d by-design difference(s), %d outside the subset (%.1fs)  PowerShell %s on %s' % (
        passed, len(counted), len(design), rejected, time.time() - t0, version, sys.platform)
    print('\n' + summary)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write('# トランスパイラー実行検証の結果\n\n- %s\n- PowerShell: `%s`\n- 比較対象: 本物の bash から取った'
                    '正解データ(標準出力のバイト列と終了コード)\n\n' % (summary, ps))
            if not fails:
                f.write('不一致なし。\n\n')
            for spec, name, ok, why, eo, erc, ao, arc, err in fails:
                f.write('## 不一致: %s :: %s\n\n期待 (rc=%s)\n```\n%s\n```\n実際 (rc=%s)\n```\n%s\n```\n' % (
                    spec, name, erc, eo.decode('utf-8', 'replace'), arc, ao.decode('utf-8', 'replace')))
                if err.strip():
                    f.write('stderr\n```\n%s\n```\n' % err.decode('utf-8', 'replace')[-1500:])
                f.write('\n')
            if design:
                f.write('## 設計上の差異(失敗に数えない)\n\n')
                for spec, name, ok, why, eo, erc, ao, arc, err in design:
                    f.write('- %s :: %s — %s(今回の実行結果: %s)\n' % (
                        spec, name, why, 'bash と一致' if ok else 'bash と不一致 rc=%s' % arc))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
