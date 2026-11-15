#### batch job wrapper with logging and exit code
#!/bin/bash
set -uo pipefail
LOG=job.log
log() { printf '[%s] %s\n' "$1" "$2" >> "$LOG"; }
run_step() {
  local name=$1; shift
  log INFO "start $name"
  if "$@" >> "$LOG" 2>&1; then log INFO "end $name rc=0"; return 0
  else local rc=$?; log ERROR "end $name rc=$rc"; return $rc; fi
}
run_step extract echo "extracting"
run_step transform false
rc=$?
run_step load echo "loading"
cat "$LOG"
echo "final rc=$rc"
exit $rc
#### config file parser
cat > app.conf <<'EOF'
# comment line
host = db01.example.local
port=5432

name = "prod db"
empty=
EOF
declare -A cfg
while IFS='=' read -r key val; do
  key=${key%%#*}; key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
  [ -z "$key" ] && continue
  val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
  val=${val#\"}; val=${val%\"}
  cfg[$key]=$val
done < app.conf
for k in host port name empty; do echo "$k=[${cfg[$k]}]"; done
echo "count=${#cfg[@]}"
#### log rotation
mkdir -p logs
for i in 1 2 3; do echo "log $i" > logs/app.log.$i; done
echo current > logs/app.log
rotate() {
  local f=$1 keep=$2 i
  [ -f "$f.$keep" ] && rm -f "$f.$keep"
  for ((i=keep-1; i>=1; i--)); do
    [ -f "$f.$i" ] && mv "$f.$i" "$f.$((i+1))"
  done
  [ -f "$f" ] && mv "$f" "$f.1"
  : > "$f"
}
rotate logs/app.log 3
ls logs
cat logs/app.log.1 logs/app.log.2 logs/app.log.3
wc -c < logs/app.log
#### csv aggregation report
cat > sales.csv <<'EOF'
date,region,amount
2026-11-01,east,100
2026-11-01,west,200
2026-11-02,east,150
2026-11-02,west,50
2026-11-03,east,300
EOF
declare -A total count
while IFS=, read -r d region amt; do
  [ "$d" = date ] && continue
  total[$region]=$(( ${total[$region]:-0} + amt ))
  count[$region]=$(( ${count[$region]:-0} + 1 ))
done < sales.csv
for r in $(printf '%s\n' "${!total[@]}" | sort); do
  printf '%-6s total=%4d count=%d avg=%d\n' "$r" "${total[$r]}" "${count[$r]}" $(( total[$r] / count[$r] ))
done
grand=0; for r in "${!total[@]}"; do grand=$((grand + total[$r])); done
echo "grand=$grand"
#### argument parsing with long options
usage() { echo "usage: prog [-v] [--name N] file..."; }
verbose=0; name=default; files=()
set -- -v --name=alice --count 3 a.txt -- -b.txt
while [ $# -gt 0 ]; do
  case $1 in
    -v|--verbose) verbose=1;;
    --name=*) name=${1#*=};;
    --name) shift; name=$1;;
    --count) shift; count=$1;;
    -h|--help) usage; exit 0;;
    --) shift; files+=("$@"); break;;
    -*) echo "unknown option $1"; exit 2;;
    *) files+=("$1");;
  esac
  shift
done
echo "verbose=$verbose name=$name count=$count files=${files[*]} n=${#files[@]}"
#### retry with backoff
attempt=0
flaky() { attempt=$((attempt+1)); [ $attempt -ge 3 ]; }
retry() {
  local max=$1 n=1; shift
  until "$@"; do
    if [ $n -ge $max ]; then echo "failed after $n"; return 1; fi
    echo "retry $n"
    n=$((n+1))
  done
  echo "ok after $n"
}
retry 5 flaky
attempt=-10
retry 2 flaky; echo "rc=$?"
#### lock file and cleanup trap
LOCK=job.lock
cleanup() { rm -f "$LOCK" work.tmp; echo "cleanup rc=$?"; }
trap cleanup EXIT
if [ -e "$LOCK" ]; then echo "already running"; exit 1; fi
echo $$ > "$LOCK"
echo data > work.tmp
[ -f "$LOCK" ] && echo "lock held"
echo "working"
exit 0
#### directory sync and compare
mkdir -p src/sub dst
echo a > src/a.txt; echo b > src/sub/b.txt; echo old > dst/a.txt; echo stale > dst/stale.txt
( cd src && find . -type f | sort ) > src.list
( cd dst && find . -type f | sort ) > dst.list
while read -r f; do
  if [ ! -f "dst/$f" ]; then mkdir -p "dst/$(dirname "$f")"; cp "src/$f" "dst/$f"; echo "NEW $f"
  elif ! cmp -s "src/$f" "dst/$f"; then cp "src/$f" "dst/$f"; echo "UPD $f"
  else echo "SAME $f"; fi
done < src.list
grep -vxFf src.list dst.list | while read -r f; do echo "EXTRA $f"; done
cat dst/a.txt dst/sub/b.txt
#### fixed-width record processing
cat > fixed.dat <<'EOF'
0001ALICE     000012050
0002BOB       000000999
0003CAROL     000100000
EOF
while IFS= read -r rec; do
  id=${rec:0:4}; name=${rec:4:10}; amt=${rec:14:9}
  name="${name%"${name##*[![:space:]]}"}"
  printf '%d|%s|%d.%02d\n' "$((10#$id))" "$name" "$((10#$amt / 100))" "$((10#$amt % 100))"
done < fixed.dat
#### date-stamped archive names
stamp() { date -u -d "@$1" +%Y%m%d_%H%M%S; }
base=1763164800
for off in 0 86400 172800; do echo "backup_$(stamp $((base+off))).tar.gz"; done
ym=$(date -u -d "@$base" +%Y-%m); echo "month=$ym"
prev=$(date -u -d "$(date -u -d "@$base" +%Y-%m-01) -1 day" +%Y-%m-%d); echo "prev_month_end=$prev"
#### validate input records
is_int() { [[ $1 =~ ^-?[0-9]+$ ]]; }
is_date() { [[ $1 =~ ^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$ ]]; }
is_email() { [[ $1 =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }
for v in 42 -7 4x ""; do is_int "$v" && echo "int:$v" || echo "bad-int:[$v]"; done
for v in 2026-11-15 2026-13-01 26-1-1; do is_date "$v" && echo "date:$v" || echo "bad-date:$v"; done
for v in a@b.co bad@ x.y; do is_email "$v" && echo "mail:$v" || echo "bad-mail:$v"; done
#### error summary from log
cat > app.log <<'EOF'
2026-11-15 01:00:01 INFO start
2026-11-15 01:00:02 ERROR db timeout
2026-11-15 01:00:03 WARN slow query
2026-11-15 01:00:04 ERROR db timeout
2026-11-15 01:00:05 ERROR disk full
2026-11-15 01:00:06 INFO end
EOF
echo "errors: $(grep -c ' ERROR ' app.log)"
grep ' ERROR ' app.log | cut -d' ' -f4- | sort | uniq -c | sort -rn | sed 's/^ *//'
awk_free_levels=$(cut -d' ' -f3 app.log | sort | uniq -c | sort -k2 | while read -r c l; do printf '%s=%s ' "$l" "$c"; done)
echo "$awk_free_levels"
first=$(grep -m1 ERROR app.log | cut -d' ' -f1,2); last=$(grep ERROR app.log | tail -1 | cut -d' ' -f1,2)
echo "first=$first last=$last"
if grep -q 'disk full' app.log; then echo "ALERT: disk"; fi
#### job dependency runner
declare -A deps=([load]="extract transform" [transform]="extract" [extract]="" [report]="load")
declare -A done_map
order=()
run_job() {
  local j=$1 d
  [ -n "${done_map[$j]:-}" ] && return 0
  for d in ${deps[$j]}; do run_job "$d"; done
  order+=("$j"); done_map[$j]=1
}
run_job report
echo "${order[*]}"
#### parallel workers with result collection
worker() { local id=$1; local sum=0 i; for ((i=1;i<=id*10;i++)); do sum=$((sum+i)); done; echo "$id $sum" > "res.$id"; }
for id in 1 2 3 4; do worker $id & done
wait
cat res.* | sort -n
total=0; while read -r _ s; do total=$((total+s)); done < <(cat res.*); echo "total=$total"
#### template rendering
name="Jun"; items=(alpha beta gamma)
render() {
cat <<EOF
Dear $name,
You have ${#items[@]} items:
$(for i in "${!items[@]}"; do printf '  %d. %s\n' $((i+1)) "${items[i]}"; done)
Total length: $(printf '%s' "${items[@]}" | wc -c)
EOF
}
render
#### function library with namespacing
lib::trim() { local s=$1; s="${s#"${s%%[![:space:]]*}"}"; printf '%s' "${s%"${s##*[![:space:]]}"}"; }
lib::join() { local IFS=$1; shift; echo "$*"; }
lib::contains() { local n=$1 h; shift; for h in "$@"; do [ "$h" = "$n" ] && return 0; done; return 1; }
lib::die() { echo "FATAL: $*" >&2; exit 1; }
echo "[$(lib::trim '   x y  ')]"
lib::join , a b c
lib::join '|' "p q" r
lib::contains b a b c && echo yes
lib::contains z a b c || echo no
( lib::die "boom" ) 2>/dev/null; echo "rc=$?"
#### menu dispatch table
cmd_start() { echo "starting $*"; }
cmd_stop() { echo "stopping"; }
cmd_status() { echo "status ok"; return 3; }
dispatch() {
  local c=$1; shift
  if declare -F "cmd_$c" >/dev/null; then "cmd_$c" "$@"; else echo "unknown: $c"; return 127; fi
}
dispatch start svc1 svc2
dispatch stop
dispatch status; echo "rc=$?"
dispatch bogus; echo "rc=$?"
#### checksum manifest verify
mkdir pkg; echo one > pkg/a; echo two > pkg/b
( cd pkg && sha256sum a b > MANIFEST )
( cd pkg && sha256sum -c MANIFEST )
echo tampered > pkg/b
( cd pkg && sha256sum -c MANIFEST 2>/dev/null ); echo "rc=$?"
#### sequence and zero padding
for i in $(seq -w 1 3); do echo "file_$i.dat"; done
for i in {08..11}; do printf '%s ' "$i"; done; echo
n=7; printf -v padded '%04d' "$n"; echo "$padded"
echo $(( 10#0008 + 1 ))
#### while with multiple conditions and counters
i=0; found=
items=(x y target z)
while [ $i -lt ${#items[@]} ] && [ -z "$found" ]; do
  [ "${items[$i]}" = target ] && found=$i
  i=$((i+1))
done
echo "found at ${found:-none}, scanned $i"
#### stdin dispatch reading commands
process() {
  local line cmd arg
  while read -r cmd arg; do
    case $cmd in
      add) sum=$((sum+arg));;
      sub) sum=$((sum-arg));;
      print) echo "sum=$sum";;
      \#*|"") ;;
      *) echo "bad command: $cmd";;
    esac
  done
}
sum=0
process <<'EOF'
add 10
# comment

add 5
sub 3
print
mul 2
print
EOF
#### strict script with sourced config and die
set -euo pipefail
cat > conf.sh <<'EOF'
APP_ENV=prod
RETENTION_DAYS=7
TARGETS=(db01 db02)
EOF
die() { echo "ERROR: $*"; exit 9; }
[ -f conf.sh ] || die "no config"
. ./conf.sh
: "${APP_ENV:?must be set}"
[ "$RETENTION_DAYS" -gt 0 ] || die "bad retention"
for t in "${TARGETS[@]}"; do echo "target=$t env=$APP_ENV keep=${RETENTION_DAYS}d"; done
[ "${#TARGETS[@]}" -eq 2 ] || die "unexpected targets"
[ "$APP_ENV" = dev ] && echo "dev only" || true
missing=${OPTIONAL_SETTING:-}
echo "optional=[$missing]"
die "intentional stop"
echo never
