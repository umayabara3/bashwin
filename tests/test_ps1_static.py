#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""トランスパイラーの静的検査(PowerShell を実行せずに確かめられること)。

    python3 tests/test_ps1_static.py

確かめること:
  1. ランタイムと生成物が ASCII のみで、括弧・引用符の対応が取れている
  2. PowerShell 7 専用の構文・API を使っていない(5.1 で読める書き方だけ)
  3. 呼んでいる関数・使っている変数がすべて定義されている(綴り違いの検出)
  4. 大文字小文字だけが違う変数名がない(PowerShell は区別しないので衝突する)
  5. サブセット外の構文は必ず変換を止める(fail-closed)
  6. テストコーパス全件で生成器が落ちない。同じ入力からは同じ出力が出る

これは「PowerShell 上で正しく動く」ことの証明ではない。動作の検証は tests/run_ps1.py。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from bashwin.ps_emit import transpile, runtime_text, MARKER  # noqa: E402
from run_golden import load_cases  # noqa: E402

FAILS = []


def check(cond, what):
    if not cond:
        FAILS.append(what)
        print('FAIL: %s' % what)


class ScanError(Exception):
    pass


def scan(text):
    """PowerShell のソースから「コード部分」だけを取り出す(文字列の中身とコメントは空白にする)。

    二重引用符の文字列の中の $( ... ) はコードとして残す。括弧の対応が崩れていれば ScanError。
    """
    out = []
    stack = []
    i = 0
    n = len(text)
    line = 1
    while i < n:
        c = text[i]
        nxt = text[i + 1:i + 2]
        if c == '\n':
            line += 1
        if stack and stack[-1] == 'DQ':
            if c == '`':
                out.append('  ')
                i += 2
                continue
            if c == '"':
                if nxt == '"':
                    out.append('  ')
                    i += 2
                    continue
                stack.pop()
                out.append('"')
            elif c == '$' and nxt == '(':
                stack.append('$(')
                out.append('$(')
                i += 2
                continue
            else:
                out.append('\n' if c == '\n' else ' ')
            i += 1
            continue
        if c == '#' and (i == 0 or text[i - 1] in ' \t\n({;'):
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
            continue
        if c == '<' and nxt == '#':
            raise ScanError('line %d: block comment is not expected' % line)
        if c == '@' and nxt in ('"', "'"):
            raise ScanError('line %d: here-string is not expected' % line)
        if c == "'":
            j = i + 1
            while True:
                j = text.find("'", j)
                if j < 0:
                    raise ScanError('line %d: unterminated single-quoted string' % line)
                if text[j + 1:j + 2] == "'":
                    j += 2
                    continue
                break
            if '\n' in text[i:j]:
                raise ScanError('line %d: newline inside a single-quoted string' % line)
            out.append("'" + ' ' * (j - i - 1) + "'")
            i = j + 1
            continue
        if c == '"':
            stack.append('DQ')
            out.append('"')
        elif c == '`':
            out.append('  ')
            i += 2
            continue
        elif c in '({[':
            stack.append(c)
            out.append(c)
        elif c in ')}]':
            want = {')': ('(', '$('), '}': ('{',), ']': ('[',)}[c]
            if not stack or stack[-1] not in want:
                raise ScanError('line %d: unbalanced %s' % (line, c))
            stack.pop()
            out.append(c)
        else:
            out.append(c)
        i += 1
    if stack:
        raise ScanError('unterminated %s at end of text' % stack[-1])
    return ''.join(out)


# PowerShell 7 でしか使えない書き方、または 5.1/.NET Framework に無い API
FORBIDDEN = [
    (r'&&', 'pipeline chain operator &&'), (r'\|\|', 'pipeline chain operator ||'),
    (r'\?\?', 'null-coalescing operator'), (r'\?\.', 'null-conditional operator'),
    (r'\)\s\?\s', 'ternary operator'), (r'\$Is(Windows|Linux|MacOS|CoreCLR)\b', '$IsWindows etc.'),
    (r'-Parallel\b', 'ForEach-Object -Parallel'), (r'^\s*(class|enum|using)\s', 'class/enum/using'),
    (r'\.ArgumentList\b', 'ProcessStartInfo.ArgumentList'), (r'Join-String', 'Join-String'),
    (r'::Latin1\b', 'Encoding.Latin1'), (r'::new\(', '::new( (kept out for clarity)'),
    (r'-AsHashtable', 'ConvertFrom-Json -AsHashtable'), (r'\$PSStyle', '$PSStyle'),
    (r'\|\s*%', 'alias %'), (r'\bWrite-(Output|Host)\b', 'Write-Output/Write-Host (stdout goes through __w)'),
]
AUTOMATIC = set('true false null _ args PSCommandPath Matches ErrorActionPreference'.split())


def assigned_vars(code):
    names = set(re.findall(r'\$(?:script:)?([A-Za-z_]\w*)\s*(?:=(?!=)|\+=|\+\+)', code))
    names |= set(re.findall(r'\bforeach\s*\(\s*\$(\w+)\s+in\b', code))
    for m in re.finditer(r'\bfunction\s+\w+\s*\(([^{]*?)\)\s*\{', code):
        names |= set(re.findall(r'\$(\w+)', m.group(1)))
    for m in re.finditer(r'\bparam\(([^{]*?)\)(?=\s)', code):
        names |= set(re.findall(r'\$(\w+)', m.group(1)))
    return names


def lint(code, defined_funcs, known_vars, label):
    for pat, what in FORBIDDEN:
        m = re.search(pat, code, re.M)
        check(m is None, '%s: uses %s near %r' % (label, what, m and code[max(0, m.start() - 30):m.end() + 20]))
    m = re.search(r'(?<![\$:\w])(__[A-Za-z_]\w*)\(', re.sub(r'\bfunction\s+\w+\(', 'function (', code))
    check(m is None, '%s: function called with method syntax (StrictMode error): %s' % (label, m and m.group(0)))
    used = set(re.findall(r'(?<![\$:\w])(__[A-Za-z_]\w*)', code))
    check(used <= defined_funcs, '%s: calls undefined function(s) %s' % (label, sorted(used - defined_funcs)))
    refs = set(re.findall(r'\$(?:script:)?([A-Za-z_]\w*)', code))
    unknown = refs - known_vars - AUTOMATIC
    check(not unknown, '%s: uses variable(s) never assigned: %s' % (label, sorted(unknown)))


def main():
    rt = runtime_text()
    check(all(ord(c) < 127 and (c >= ' ' or c == '\n') for c in rt), 'runtime: ASCII only, no tabs/CR')
    try:
        rt_code = scan(rt)
    except ScanError as e:
        check(False, 'runtime: %s' % e)
        rt_code = ''
    funcs = set(re.findall(r'^\s*function\s+(__\w+)', rt_code, re.M))
    rt_vars = assigned_vars(rt_code)
    lint(rt_code, funcs, rt_vars, 'runtime')
    by_lower = {}
    for v in rt_vars:
        by_lower.setdefault(v.lower(), set()).add(v)
    clash = sorted(sorted(s) for s in by_lower.values() if len(s) > 1)
    check(not clash, 'runtime: variable names differing only in case: %s' % clash)
    rt_lower = set(by_lower)

    # ---- コーパス全件: 落ちない・決定的・生成物の静的検査
    total = ok = 0
    for fn in sorted(os.listdir(os.path.join(HERE, 'spec'))):
        if not fn.endswith('.sh'):
            continue
        cases = load_cases(os.path.join(HERE, 'spec', fn))
        for name in sorted(cases):
            total += 1
            label = '%s :: %s' % (fn, name)
            try:
                text, problems, err = transpile(cases[name], 'case.sh')
                text2 = transpile(cases[name], 'case.sh')[0]
            except Exception as e:      # 生成器は入力が何であれ落ちてはいけない
                check(False, '%s: generator crashed: %r' % (label, e))
                continue
            check(text == text2, '%s: output is not deterministic' % label)
            if text is None:
                check(bool(problems) or bool(err), '%s: rejected without a reason' % label)
                continue
            ok += 1
            check(text.startswith(MARKER), '%s: marker line missing' % label)
            check(all(ord(c) < 127 and (c >= ' ' or c == '\n') for c in text), '%s: not plain ASCII' % label)
            body = text[text.index('# ---- translated from'):]
            try:
                code = scan(body)
            except ScanError as e:
                check(False, '%s: %s' % (label, e))
                continue
            body_vars = assigned_vars(code)
            lint(code, funcs, rt_vars | body_vars, label)
            bad_case = sorted(v for v in body_vars if v.lower() in rt_lower and v not in rt_vars)
            check(not bad_case, '%s: variable clashes with a runtime name by case: %s' % (label, bad_case))

    # ---- fail-closed: サブセット外は必ず止まる
    must_reject = [
        ('ls | wc -l', 'pipeline'), ('grep x file', 'unix-tool'), ('echo $x', 'unquoted'),
        ('a=(1 2 3)', 'array'), ('echo "${a[0]}"', 'array'), ('cat <<EOF\nx\nEOF', 'heredoc'),
        ('mytool < in.txt', 'stdin-redirect'), ('( cd /tmp; mytool )', 'subshell'),
        ('mytool &', 'background'), ('echo *.txt', 'glob'), ('echo {a,b}', 'brace'),
        ('echo ~root', 'tilde'), ('FOO=1 mytool', 'tmpenv'), ('x+=1', 'append'),
        ('echo "${x%.txt}"', 'param-op'), ('echo "${#x}"', 'param-op'), ('echo "$*"', 'special-param'),
        ('echo "$RANDOM"', 'special-var'), ('read line', 'builtin'), ('printf "%s\\n" a', 'builtin'),
        ('trap "echo bye" EXIT', 'builtin'), ('exec mytool', 'builtin'), ('eval "echo hi"', 'builtin'),
        ('source lib.sh', 'builtin'), ('echo -e "a\\tb"', 'echo-opt'), ('[[ a =~ b ]]', 'regex'),
        ('echo $(( 2 ** 3 ))', 'arith'), ('echo $(( 1 << 2 ))', 'arith'), ('echo $(( a ? 1 : 2 ))', 'arith'),
        ('case x in x) echo a;& y) echo b;; esac', 'case-fallthrough'), ('mytool 3>log', 'fd'),
        ('set -x', 'set-opt'), ('local x=1', 'local'), ('return 1', 'return'), ('break', 'loop-control'),
        ('f() { break; }; while true; do f; done', 'loop-control'), ('mytool <(a) <(b)', 'procsub'),
        ('echo "$(mytool | sort)"', 'pipeline'), ('for f in *.log; do echo "$f"; done', 'glob'),
        ('mytool > out_*.txt', 'glob'), ('[ -x file ]', 'test-op'), ('cd -P /tmp', 'builtin'),
    ]
    for src, cat in must_reject:
        text, problems, err = transpile(src)
        cats = set(p[1] for p in problems)
        check(text is None and cat in cats, 'fail-closed: %r must be rejected as [%s], got %s%s' % (
            src, cat, sorted(cats), '' if text is None else ' and produced output'))

    # ---- 代表的な受理例: 変換できること
    must_accept = [
        'set -euo pipefail\necho ok', 'x=1; [ "$x" -eq 1 ] && echo one || echo other',
        'f() { local a="$1"; echo "$a"; }; f "x y"', 'for a in "$@"; do echo "$a"; done',
        'mytool.exe --flag "$HOME/data" > "$HOME/out.log" 2>&1', 'echo err >&2',
        'n=$(( (n + 1) * 2 % 7 ))', 'case "$1" in start|stop) echo ok;; *) exit 2;; esac',
        '"$TOOL_DIR/run.cmd" "$@" || exit $?', 'while [ "$i" -lt 3 ]; do i=$((i+1)); done',
        'for ((i=0; i<3; i++)); do echo "$i"; done', 'echo "${x:-default}" "${y:+set}" "${z:=init}"',
        'cd ~/work && pwd', 'v=$(mytool --version) || echo failed',
    ]
    for src in must_accept:
        text, problems, err = transpile(src)
        check(text is not None, 'accept: %r was rejected: %s %s' % (src, problems, err))
        if text is not None:
            try:
                scan(text)
            except ScanError as e:
                check(False, 'accept: %r: %s' % (src, e))

    print('corpus: %d cases, %d transpiled, %d rejected' % (total, ok, total - ok))
    print('fail-closed checks: %d, accept checks: %d' % (len(must_reject), len(must_accept)))
    print('runtime: %d functions, %d lines' % (len(funcs), rt.count('\n')))
    if FAILS:
        print('\n%d static check(s) FAILED' % len(FAILS))
        return 1
    print('\nall static checks passed (this does not replace running tests/run_ps1.py)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
