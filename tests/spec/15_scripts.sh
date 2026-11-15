#### script: backup rotation with tar and find
#!/usr/bin/env bash
set -eu
SRC=data; DEST=backups; KEEP=3
mkdir -p "$SRC/sub" "$DEST"
for i in 1 2 3; do echo "file $i" > "$SRC/f$i.txt"; done
echo nested > "$SRC/sub/n.txt"
backup_once() {
  local stamp=$1 archive
  archive="$DEST/backup_${stamp}.tar.gz"
  tar -czf "$archive" "$SRC"
  [[ -s $archive ]] || { echo "empty archive" >&2; return 1; }
  echo "created ${archive##*/} ($(tar -tzf "$archive" | grep -c 'txt$') files)"
}
for d in 20261110 20261111 20261112 20261113 20261114; do backup_once "$d"; done
count=$(ls "$DEST" | wc -l)
echo "before prune: $count"
ls -1 "$DEST" | sort | head -n -"$KEEP" | while read -r old; do
  rm -f "$DEST/$old"; echo "pruned $old"
done
echo "after prune: $(ls "$DEST" | wc -l)"
latest=$(ls -1 "$DEST" | sort | tail -1)
mkdir restore && tar -xzf "$DEST/$latest" -C restore
diff -r "$SRC" restore/"$SRC" >/dev/null 2>&1 && echo "restore verified" || {
  # diff -r が使えない環境向けの代替確認
  a=$(cd "$SRC" && find . -type f | sort | xargs cat | md5sum)
  b=$(cd restore/"$SRC" && find . -type f | sort | xargs cat | md5sum)
  [ "$a" = "$b" ] && echo "restore verified"
}
#### script: deploy with getopts and generated config
#!/bin/bash
set -o errexit -o nounset -o pipefail
usage() { cat <<EOF
Usage: deploy [-e ENV] [-p PORT] [-n] SERVICE...
  -e ENV   target environment (default: dev)
  -p PORT  base port (default: 8000)
  -n       dry run
EOF
}
ENV=dev; PORT=8000; DRY=0
set -- -e prod -p 9000 -n api worker "batch job"
while getopts ":e:p:nh" opt; do
  case "$opt" in
    e) ENV=$OPTARG ;;
    p) PORT=$OPTARG ;;
    n) DRY=1 ;;
    h) usage; exit 0 ;;
    :) echo "option -$OPTARG needs a value" >&2; exit 2 ;;
    \?) echo "unknown option -$OPTARG" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
[[ $# -ge 1 ]] || { usage; exit 2; }
[[ $PORT =~ ^[0-9]+$ ]] || { echo "bad port"; exit 2; }
declare -a services=("$@")
declare -A ports
i=0
for s in "${services[@]}"; do ports[$s]=$((PORT + i)); i=$((i + 1)); done
mkdir -p "conf/$ENV"
for s in "${services[@]}"; do
  safe=${s// /_}
  cat > "conf/$ENV/$safe.conf" <<EOF
[service]
name = $s
env = $ENV
port = ${ports[$s]}
workers = $(( ${#s} % 3 + 1 ))
EOF
done
printf '%-12s %-6s %s\n' SERVICE PORT FILE
for s in "${services[@]}"; do printf '%-12s %-6d %s\n' "$s" "${ports[$s]}" "conf/$ENV/${s// /_}.conf"; done
grep -h '^port' conf/"$ENV"/*.conf | sort
(( DRY )) && echo "dry run: nothing deployed" || echo "deployed ${#services[@]} services"
usage | head -1
#### script: monitoring report with awk sed grep
#!/bin/bash
cat > access.log <<'EOF'
10.0.0.1 - - [15/Nov/2026:01:00:01 +0900] "GET /index.html HTTP/1.1" 200 1043
10.0.0.2 - - [15/Nov/2026:01:00:02 +0900] "GET /api/users HTTP/1.1" 200 512
10.0.0.1 - - [15/Nov/2026:01:00:03 +0900] "POST /api/login HTTP/1.1" 401 88
10.0.0.3 - - [15/Nov/2026:01:00:04 +0900] "GET /missing HTTP/1.1" 404 0
10.0.0.2 - - [15/Nov/2026:01:01:10 +0900] "GET /api/users HTTP/1.1" 500 23
10.0.0.1 - - [15/Nov/2026:01:02:00 +0900] "GET /index.html HTTP/1.1" 200 1043
EOF
echo "== requests per client =="
awk '{print $1}' access.log | sort | uniq -c | sort -k1,1nr -k2 | awk '{printf "%-10s %d\n", $2, $1}'
echo "== status classes =="
awk '{c[substr($9, 1, 1) "xx"]++} END {for (k in c) print k, c[k]}' access.log | sort
echo "== bytes by path =="
awk '{b[$7] += $10} END {for (p in b) printf "%8d %s\n", b[p], p}' access.log | sort -k1,1nr -k2
echo "== errors =="
grep -E '" (4|5)[0-9]{2} ' access.log | sed -E 's/^([0-9.]+) .*"([A-Z]+) ([^ ]+) [^"]*" ([0-9]+) .*/\4 \2 \3 from \1/'
echo "== per minute =="
sed -E 's/.*\[[^:]+:([0-9]{2}:[0-9]{2}):.*/\1/' access.log | uniq -c | sed 's/^ *//'
total=$(wc -l < access.log); errs=$(grep -cE '" [45][0-9]{2} ' access.log)
printf 'error rate: %d/%d = %d%%\n' "$errs" "$total" $(( errs * 100 / total ))
threshold=40
if (( errs * 100 / total > threshold )); then echo "ALERT: error rate above ${threshold}%"; else echo "OK: below ${threshold}%"; fi
#### script: tiny test framework with subshells and traps
#!/bin/bash
PASS=0; FAIL=0; CURRENT=
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"; echo "cleaned: $([ -d "$workdir" ] && echo no || echo yes)"' EXIT
assert_eq() { if [ "$1" = "$2" ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "  FAIL [$CURRENT]: expected '$2' got '$1'"; fi; }
assert_ok() { if "$@" >/dev/null 2>&1; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "  FAIL [$CURRENT]: $*"; fi; }
assert_fail() { if "$@" >/dev/null 2>&1; then FAIL=$((FAIL + 1)); echo "  FAIL [$CURRENT]: expected failure: $*"; else PASS=$((PASS + 1)); fi; }
run_test() { CURRENT=$1; echo "- $1"; "$1"; }
slugify() { echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g'; }
test_slugify() {
  assert_eq "$(slugify 'Hello, World!')" "hello-world"
  assert_eq "$(slugify '  Multiple   Spaces ')" "multiple-spaces"
  assert_eq "$(slugify 'already-ok')" "already-ok"
}
test_files() {
  ( cd "$workdir" && echo x > a.txt && mkdir d )
  assert_ok test -f "$workdir/a.txt"
  assert_ok test -d "$workdir/d"
  assert_fail test -f "$workdir/nope"
  assert_eq "$(cat "$workdir/a.txt")" "x"
}
test_isolation() {
  local v=outer
  ( v=inner; exit 3 ); assert_eq "$?" "3"
  assert_eq "$v" "outer"
  assert_eq "$(v=sub; echo $v)" "sub"
}
test_expected_failure() { assert_eq "$(echo actual)" "different"; }
for t in test_slugify test_files test_isolation test_expected_failure; do run_test "$t"; done
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 1 ]
#### script: data transformation pipeline with here-docs and functions
#!/bin/bash
set -euo pipefail
cat > raw.tsv <<EOF
id	name	score	grade
1	Alice Smith	92.5	A
2	bob jones	78	C
3	CAROL WHITE	85.25	B
4	dave  brown		F
EOF
normalize_name() { local n=$1 out= w; for w in $n; do w=${w,,}; out+="${w^} "; done; echo "${out% }"; }
{
  IFS=$'\t' read -r -a header
  echo "${header[*]}" | tr ' ' ','
  while IFS=$'\t' read -r id name score grade; do
    name=$(normalize_name "$name")
    [ -n "$score" ] || score=0
    printf '%s,%s,%.1f,%s\n' "$id" "$name" "$score" "$grade"
  done
} < raw.tsv > clean.csv
cat clean.csv
echo "--- stats"
awk -F, 'NR > 1 {n++; s += $3; if ($3 > max) {max = $3; top = $2}} END {printf "n=%d mean=%.2f top=%s(%.1f)\n", n, s / n, top, max}' clean.csv
echo "--- by grade"
tail -n +2 clean.csv | cut -d, -f4 | sort | uniq -c | while read -r c g; do printf '%s:%s ' "$g" "$c"; done; echo
echo "--- json"
{
  echo '['
  tail -n +2 clean.csv | while IFS=, read -r id name score grade; do
    printf '  {"id": %d, "name": "%s", "score": %s, "pass": %s}' "$id" "$name" "$score" "$([ "$grade" != F ] && echo true || echo false)"
    echo
  done | sed '$!s/$/,/'
  echo ']'
} > out.json
cat out.json
grep -c '"pass": true' out.json
#### script: state machine and queue processing
#!/bin/bash
declare -a queue=("build:app" "test:app" "fail:lint" "deploy:app" "build:docs")
declare -A state attempts
log=()
process() {
  local item=$1 kind=${1%%:*} target=${1#*:}
  attempts[$item]=$(( ${attempts[$item]:-0} + 1 ))
  case $kind in
    build) state[$target]=built ;;
    test) [[ ${state[$target]:-} == built ]] && state[$target]=tested || return 1 ;;
    deploy) [[ ${state[$target]:-} == tested ]] && state[$target]=deployed || return 1 ;;
    fail) (( attempts[$item] >= 2 )) || return 2 ;;
    *) return 127 ;;
  esac
}
round=0
while (( ${#queue[@]} > 0 && round < 5 )); do
  round=$((round + 1)); retry=()
  for item in "${queue[@]}"; do
    if process "$item"; then log+=("r$round ok $item"); else log+=("r$round retry($?) $item"); retry+=("$item"); fi
  done
  queue=("${retry[@]+"${retry[@]}"}")
done
printf '%s\n' "${log[@]}"
for t in $(printf '%s\n' "${!state[@]}" | sort); do echo "$t=${state[$t]}"; done
echo "rounds=$round remaining=${#queue[@]}"
#### script: text report formatting with printf and padding
#!/bin/bash
items=("Widget:4:3.50" "Gadget Pro:10:12.25" "Thing:1:0.99" "超合金ロボ:2:1500")
line() { printf '%*s\n' "$1" '' | tr ' ' "${2:--}"; }
printf '%-14s %5s %10s %10s\n' Item Qty Price Total
line 42
subtotal_cents=0
for it in "${items[@]}"; do
  IFS=: read -r name qty price <<< "$it"
  cents=$(awk -v p="$price" 'BEGIN {printf "%d", p * 100 + 0.5}')
  total=$(( cents * qty ))
  subtotal_cents=$(( subtotal_cents + total ))
  printf '%-14s %5d %10s %10s\n' "$name" "$qty" "$price" "$(( total / 100 )).$(printf '%02d' $(( total % 100 )))"
done
line 42 =
tax=$(( subtotal_cents * 10 / 100 ))
printf '%-31s %10s\n' Subtotal "$(( subtotal_cents / 100 )).$(printf '%02d' $(( subtotal_cents % 100 )))"
printf '%-31s %10s\n' 'Tax (10%)' "$(( tax / 100 )).$(printf '%02d' $(( tax % 100 )))"
grand=$(( subtotal_cents + tax ))
printf '%-31s %10s\n' TOTAL "$(( grand / 100 )).$(printf '%02d' $(( grand % 100 )))"
echo "items=${#items[@]} longest=$(printf '%s\n' "${items[@]%%:*}" | awk '{ if (length($0) > m) m = length($0) } END { print m }')"
