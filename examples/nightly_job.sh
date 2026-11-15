#!/bin/bash
# 夜間バッチの見本: 入力ファイルを検査し、集計し、古いログを掃除する。
#   bashwin nightly_job.sh <入力ディレクトリ> <出力ディレクトリ> [保持日数]
# bash でも bashwin でも同じ結果になる(tests で突き合わせ済みの構文だけを使用)。
set -euo pipefail

readonly IN_DIR=${1:?usage: nightly_job.sh IN_DIR OUT_DIR [KEEP_DAYS]}
readonly OUT_DIR=${2:?usage: nightly_job.sh IN_DIR OUT_DIR [KEEP_DAYS]}
readonly KEEP_DAYS=${3:-7}
readonly LOG="$OUT_DIR/job.log"

log() { printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" | tee -a "$LOG"; }
die() { log ERROR "$*"; exit 9; }

on_exit() {
  local rc=$?
  rm -f "$OUT_DIR/.work.tmp"
  if [ "$rc" -eq 0 ]; then log INFO "job finished rc=0"; else log ERROR "job failed rc=$rc"; fi
}

mkdir -p "$OUT_DIR"
trap on_exit EXIT
[ -d "$IN_DIR" ] || die "input directory not found: $IN_DIR"

log INFO "start in=$IN_DIR out=$OUT_DIR keep=${KEEP_DAYS}d"

# 1) 入力検査: ヘッダと列数
shopt -s nullglob
files=("$IN_DIR"/*.csv)
[ "${#files[@]}" -gt 0 ] || die "no input files"
ok=0; ng=0
for f in "${files[@]}"; do
  name=${f##*/}
  header=$(head -1 "$f")
  if [ "$header" != "date,region,amount" ]; then
    log WARN "skip $name: unexpected header"; ng=$((ng + 1)); continue
  fi
  bad=$(awk -F, 'NR > 1 && (NF != 3 || $3 !~ /^[0-9]+$/)' "$f" | wc -l)
  if [ "$bad" -gt 0 ]; then
    log WARN "skip $name: $bad malformed rows"; ng=$((ng + 1)); continue
  fi
  tail -n +2 "$f" >> "$OUT_DIR/.work.tmp"
  ok=$((ok + 1))
done
log INFO "validated ok=$ok ng=$ng"
[ "$ok" -gt 0 ] || die "no valid input"

# 2) 集計: 地域別の合計・件数・平均
sort -t, -k2,2 -k1,1 "$OUT_DIR/.work.tmp" |
  awk -F, '{sum[$2] += $3; cnt[$2]++}
           END {for (r in sum) printf "%s,%d,%d,%.1f\n", r, sum[r], cnt[r], sum[r] / cnt[r]}' |
  sort > "$OUT_DIR/summary.csv"
total=$(cut -d, -f2 "$OUT_DIR/summary.csv" | paste -sd+ | sed 's/^$/0/')
log INFO "summary rows=$(wc -l < "$OUT_DIR/summary.csv") total=$((total))"

# 3) 後片付け: 保持期間を過ぎたログを削除
removed=$(find "$OUT_DIR" -maxdepth 1 -name '*.old.log' -mtime +"$KEEP_DAYS" -print -delete | wc -l)
log INFO "cleanup removed=$removed"
