#!/bin/bash
# トランスパイラー(--ps1)向けの書き方の見本: EXE を順に呼び、終了コードで分岐する夜間ジョブ。
# bash でも、bashwin インタープリターでも、変換後の PowerShell でも同じに動く範囲だけを使っている。
#   python bashwin.pyz --ps1 examples/ps1/etl_job.sh   ->  examples/ps1/etl_job.ps1
#   powershell -NoProfile -File etl_job.ps1 D:\data\in D:\data\out 3
set -eu

usage() { echo "usage: $0 <input-dir> <output-dir> [retries]" >&2; exit 2; }

[ "$#" -ge 2 ] || usage
IN_DIR="$1"
OUT_DIR="$2"
RETRIES="${3:-3}"
LOG="$OUT_DIR/job.log"
TOOL="${EXPORT_TOOL:-export_tool.exe}"

log() { echo "[job] $1" >> "$LOG"; }

[ -d "$IN_DIR" ] || { echo "input directory not found: $IN_DIR" >&2; exit 3; }
[ -d "$OUT_DIR" ] || { echo "output directory not found: $OUT_DIR" >&2; exit 3; }

log "start in=$IN_DIR out=$OUT_DIR retries=$RETRIES"

# 1 ステップを最大 RETRIES 回まで試す。標準出力と標準エラーはログへ。
run_step() {
    local name="$1" attempt=1 rc=0
    shift
    while true; do
        rc=0
        "$@" >> "$LOG" 2>&1 || rc=$?
        if [ "$rc" -eq 0 ]; then
            log "step $name ok (attempt $attempt)"
            return 0
        fi
        log "step $name failed rc=$rc (attempt $attempt)"
        if [ "$attempt" -ge "$RETRIES" ]; then
            return "$rc"
        fi
        attempt=$((attempt + 1))
    done
}

failed=0
for step in extract transform load; do
    case "$step" in
        extract)
            run_step "$step" "$TOOL" --mode extract --from "$IN_DIR" || failed=$((failed + 1)) ;;
        transform)
            run_step "$step" "$TOOL" --mode transform --work "$OUT_DIR" || failed=$((failed + 1)) ;;
        load)
            if [ "$failed" -eq 0 ]; then
                run_step "$step" "$TOOL" --mode load --to "$OUT_DIR" || failed=$((failed + 1))
            else
                log "step load skipped"
            fi ;;
    esac
done

if [ "$failed" -gt 0 ]; then
    log "finished with $failed failed step(s)"
    echo "job failed: $failed step(s); see $LOG" >&2
    exit 1
fi
log "finished ok"
echo "job ok"
