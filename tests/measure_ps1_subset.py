#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代替案(Bash -> PowerShell トランスパイラー)の適用可能範囲を実測する。

テストコーパス(tests/spec の全ケース)を「PowerShell 変換可能サブセット」判定器に
かけ、何件が変換可能か、何が変換を妨げているかを集計する。
    python3 tests/measure_ps1_subset.py [--report tests/REPORT_ps1_subset.md]
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from bashwin.ps_subset import check  # noqa: E402
from run_golden import load_cases  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', default=os.path.join(HERE, 'REPORT_ps1_subset.md'))
    args = ap.parse_args()
    per_file = collections.OrderedDict()
    cats = collections.Counter()
    ok_names = []
    total = ok = 0
    for fn in sorted(os.listdir(os.path.join(HERE, 'spec'))):
        if not fn.endswith('.sh') or fn.startswith(('80_', '90_')):
            continue
        cases = load_cases(os.path.join(HERE, 'spec', fn))
        n_ok = 0
        for name in sorted(cases):
            problems, err = check(cases[name])
            total += 1
            if not problems and not err:
                ok += 1
                n_ok += 1
                ok_names.append('%s :: %s' % (fn, name))
            for c in set(p[1] for p in problems):
                cats[c] += 1
        per_file[fn] = (len(cases), n_ok)
    lines = ['# PowerShell 変換可能サブセットの実測\n',
             '対象: tests/spec のテストケース %d 件(bashwin 固有・設計差異の検証用を除く)\n' % total,
             '- 変換可能サブセットに収まる: **%d 件 (%.1f%%)**' % (ok, 100.0 * ok / total),
             '- サブセット外(変換不可): %d 件 (%.1f%%)\n' % (total - ok, 100.0 * (total - ok) / total),
             '## ファイル別\n', '| ファイル | ケース数 | 変換可能 |', '|---|---:|---:|']
    for fn, (n, k) in per_file.items():
        lines.append('| %s | %d | %d |' % (fn, n, k))
    lines += ['\n## 変換を妨げている要因(該当ケース数、重複あり)\n', '| 要因 | ケース数 |', '|---|---:|']
    for c, n in cats.most_common():
        lines.append('| %s | %d |' % (c, n))
    lines += ['\n## 変換可能と判定されたケース\n'] + ['- %s' % x for x in ok_names]
    text = '\n'.join(lines) + '\n'
    with open(args.report, 'w', encoding='utf-8') as f:
        f.write(text)
    print('transpilable: %d / %d (%.1f%%)' % (ok, total, 100.0 * ok / total))
    for c, n in cats.most_common(12):
        print('  %-18s %d' % (c, n))


if __name__ == '__main__':
    main()
