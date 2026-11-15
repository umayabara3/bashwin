#### script: array algorithms
#!/bin/bash
bubble_sort() { local -a a=("$@"); local n=${#a[@]} i j t
  for ((i = 0; i < n; i++)); do for ((j = 0; j < n - i - 1; j++)); do
    if (( a[j] > a[j+1] )); then t=${a[j]}; a[j]=${a[j+1]}; a[j+1]=$t; fi
  done; done; echo "${a[@]}"; }
reverse() { local -a out=(); local i; for ((i = $#; i >= 1; i--)); do out+=("${!i}"); done; echo "${out[@]}"; }
uniq_arr() { local -A seen=(); local -a out=(); local x; for x in "$@"; do [[ -n ${seen[$x]:-} ]] || { out+=("$x"); seen[$x]=1; }; done; echo "${out[@]}"; }
max() { local m=$1 x; for x in "$@"; do (( x > m )) && m=$x; done; echo "$m"; }
sum() { local s=0 x; for x in "$@"; do (( s += x )); done; echo "$s"; }
contains() { local needle=$1; shift; local x; for x in "$@"; do [[ $x == "$needle" ]] && return 0; done; return 1; }
nums=(5 3 9 1 7 3 5)
echo "sorted: $(bubble_sort "${nums[@]}")"
echo "reversed: $(reverse "${nums[@]}")"
echo "unique: $(uniq_arr "${nums[@]}")"
echo "max: $(max "${nums[@]}") sum: $(sum "${nums[@]}") n: ${#nums[@]}"
contains 9 "${nums[@]}" && echo "has 9"; contains 4 "${nums[@]}" || echo "no 4"
sieve() { local n=$1 i j; local -a c=(); for ((i = 2; i <= n; i++)); do c[i]=1; done
  for ((i = 2; i * i <= n; i++)); do (( c[i] )) && for ((j = i * i; j <= n; j += i)); do c[j]=0; done; done
  for ((i = 2; i <= n; i++)); do (( c[i] )) && printf '%d ' "$i"; done; echo; }
sieve 50
to_base() { local n=$1 b=$2 digits=0123456789abcdef out=; (( n == 0 )) && { echo 0; return; }
  while (( n > 0 )); do out=${digits:n % b:1}$out; (( n /= b )); done; echo "$out"; }
echo "$(to_base 255 2) $(to_base 255 16) $(to_base 255 8) $(to_base 0 2)"
matrix=(); rows=3; cols=3
for ((r = 0; r < rows; r++)); do for ((c = 0; c < cols; c++)); do matrix[r * cols + c]=$(( (r + 1) * (c + 1) )); done; done
for ((r = 0; r < rows; r++)); do line=; for ((c = 0; c < cols; c++)); do line+="${matrix[r * cols + c]} "; done; echo "${line% }"; done
#### script: ini parser and writer
#!/bin/bash
cat > settings.ini <<'EOF'
; global comment
[database]
host = db.internal
port = 5432
name = "app db"

[cache]
host=cache.internal
ttl = 300   ; trailing comment
enabled = true

[empty]
EOF
declare -A ini; declare -a sections=()
section=
while IFS= read -r line || [[ -n $line ]]; do
  line=${line%%;*}
  line="${line#"${line%%[![:space:]]*}"}"; line="${line%"${line##*[![:space:]]}"}"
  [[ -z $line ]] && continue
  if [[ $line =~ ^\[([A-Za-z0-9_]+)\]$ ]]; then section=${BASH_REMATCH[1]}; sections+=("$section"); continue; fi
  if [[ $line =~ ^([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
    key=${BASH_REMATCH[1]}; val=${BASH_REMATCH[2]}
    val=${val#\"}; val=${val%\"}
    ini[$section.$key]=$val
  fi
done < settings.ini
ini_get() { echo "${ini[$1.$2]:-${3:-}}"; }
echo "sections: ${sections[*]}"
echo "db: $(ini_get database host):$(ini_get database port)/$(ini_get database name)"
echo "ttl: $(ini_get cache ttl) missing: [$(ini_get cache nope)] default: $(ini_get cache nope fallback)"
for s in "${sections[@]}"; do
  n=0; for k in "${!ini[@]}"; do [[ $k == "$s".* ]] && n=$((n + 1)); done
  echo "[$s] keys=$n"
done
{ for s in "${sections[@]}"; do echo "[$s]"; for k in $(printf '%s\n' "${!ini[@]}" | sort); do [[ $k == "$s".* ]] && echo "${k#*.}=${ini[$k]}"; done; done; } > out.ini
cat out.ini
#### script: argument forwarding and quoting through layers
#!/bin/bash
show() { printf '%d:' $#; printf '[%s]' "$@"; echo; }
fwd_at() { show "$@"; }
fwd_star() { show "$*"; }
fwd_unq() { show $@; }
fwd_shift() { local first=$1; shift; show "$first" "--" "$@"; }
wrap() { local cmd=("$@"); "${cmd[@]}"; }
args=("one" "two words" "" "it's" 'q"uote' "tab	in" "*" "a  b")
fwd_at "${args[@]}"
fwd_star "${args[@]}"
fwd_unq "x y" z
fwd_shift "${args[@]:0:3}"
wrap show "${args[@]:1:2}"
wrap fwd_at -n -e "--flag=value with space"
set -- "${args[@]}"; show "$@"; show "${@:2:2}"; show "${@: -1}"
build=(); build+=(--name "My App"); build+=(--tags "a,b c"); [ -n "" ] && build+=(--never)
show "${build[@]}"
cmdline="echo literal string"; $cmdline
eval "show ${args[1]@Q} ${args[3]@Q}"
IFS=,; joined="${args[*]:0:2}"; unset IFS; show "$joined"
s='a b   c'; show $s; show "$s"; a=($s); show "${a[@]}"
#### script: error handling patterns
#!/bin/bash
set -uo pipefail
errors=()
try() { local out rc; out=$("$@" 2>&1); rc=$?; if (( rc != 0 )); then errors+=("$1 failed rc=$rc: ${out:-<no output>}"); fi; return $rc; }
ok_cmd() { echo fine; }
bad_cmd() { echo "something broke" >&2; return 3; }
silent_bad() { return 1; }
try ok_cmd && echo "ok_cmd passed"
try bad_cmd || echo "bad_cmd handled"
try silent_bad || echo "silent_bad handled"
try nonexistent_command_xyz || echo "missing handled rc=$?"
printf '%s\n' "${errors[@]}" | sed -E 's/(line [0-9]+: )//; s/^.*nonexistent_command_xyz.*$/nonexistent_command_xyz failed (not found)/'
echo "error count: ${#errors[@]}"
cleanup_ran=0
with_cleanup() { local tmp; tmp=$(mktemp); trap 'rm -f "$tmp"; cleanup_ran=1' RETURN 2>/dev/null || true; echo data > "$tmp"; [ -s "$tmp" ] && echo "tmp has data"; rm -f "$tmp"; }
with_cleanup
guard() { local v=${1:-}; [[ -n $v ]] || { echo "guard: empty"; return 64; }; [[ $v =~ ^[0-9]+$ ]] || { echo "guard: not a number: $v"; return 65; }; echo "guard: ok $v"; }
guard; echo "rc=$?"; guard abc; echo "rc=$?"; guard 42; echo "rc=$?"
pipeline_status() { false | true | (exit 5) | true; echo "pipe rc=$? status=${PIPESTATUS[*]}"; }
pipeline_status
( set -e; false; echo "not reached" ); echo "subshell errexit rc=$?"
result=$(set -e; echo partial; false; echo more) || echo "cmdsub failed with [$result]"
{ echo "block out"; false; } && echo no || echo "block failed"
case "$(false; echo $?)" in 1) echo "captured status 1";; esac
#### script: string utilities library
#!/bin/bash
str_repeat() { local s=$1 n=$2 out=; while (( n-- > 0 )); do out+=$s; done; printf '%s' "$out"; }
str_pad_left() { printf '%*s' "$2" "$1"; }
str_pad_right() { printf '%-*s' "$2" "$1"; }
str_center() { local s=$1 w=$2 l=${#1}; local left=$(( (w - l) / 2 )); printf '%*s%s%*s' "$left" '' "$s" $(( w - l - left )) ''; }
str_reverse() { local s=$1 out= i; for ((i = ${#s} - 1; i >= 0; i--)); do out+=${s:i:1}; done; printf '%s' "$out"; }
str_count() { local s=$1 sub=$2 n=0; while [[ $s == *"$sub"* ]]; do s=${s#*"$sub"}; n=$((n + 1)); done; echo $n; }
str_starts() { [[ $1 == "$2"* ]]; }
str_ends() { [[ $1 == *"$2" ]]; }
str_trim() { local s=$1; s="${s#"${s%%[![:space:]]*}"}"; printf '%s' "${s%"${s##*[![:space:]]}"}"; }
str_split() { local IFS=$2; read -ra PARTS <<< "$1"; }
str_join() { local d=$1; shift; local out=$1; shift; local x; for x in "$@"; do out+="$d$x"; done; printf '%s' "$out"; }
str_title() { local w out=; for w in $1; do out+="${w^} "; done; printf '%s' "${out% }"; }
is_palindrome() { local s=${1,,}; s=${s//[^a-z0-9]/}; [[ $s == "$(str_reverse "$s")" ]]; }
echo "[$(str_repeat ab 3)] [$(str_pad_left 42 6)] [$(str_pad_right hi 5)] [$(str_center mid 9)]"
echo "$(str_reverse stressed) $(str_count banana an) $(str_count aaaa aa) $(str_count abc x)"
str_starts foobar foo && echo starts; str_ends foobar bar && echo ends; str_starts foobar bar || echo not-starts
echo "[$(str_trim '   padded text  ')]"
str_split "a:b:c d" :; echo "${#PARTS[@]} [${PARTS[2]}]"
echo "$(str_join ', ' x y z) | $(str_join - solo) | $(str_title 'the quick brown fox')"
for p in "A man, a plan, a canal: Panama" "not a palindrome" "Was it a car or a cat I saw?"; do is_palindrome "$p" && echo "yes: $p" || echo "no: $p"; done
s="The Quick Brown Fox"; echo "${s,,} | ${s^^} | ${#s} | ${s// /_} | ${s:4:5} | ${s%% *} | ${s##* }"
words=($s); echo "${#words[@]} ${words[-1]} ${words[@]:1:2}"
vowels=${s//[^aeiouAEIOU]/}; echo "vowels=${#vowels} [$vowels]"
#### script: tree walk and size report
#!/bin/bash
mkdir -p proj/{src/{core,util},docs,tests}
printf '%0100d' 0 > proj/src/core/main.c; printf '%050d' 0 > proj/src/core/io.c
printf '%025d' 0 > proj/src/util/str.c; printf '%010d' 0 > proj/docs/readme.md
printf '%05d' 0 > proj/tests/t1.sh; : > proj/tests/empty.txt
walk() { local dir=$1 indent=$2 entry
  for entry in "$dir"/*; do
    [ -e "$entry" ] || continue
    if [ -d "$entry" ]; then echo "${indent}${entry##*/}/"; walk "$entry" "$indent  "
    else printf '%s%s (%d)\n' "$indent" "${entry##*/}" "$(wc -c < "$entry")"; fi
  done; }
echo "proj/"; walk proj "  "
echo "--- by extension"
find proj -type f | sed -E 's/.*\.([^./]+)$/\1/' | sort | uniq -c | awk '{printf "%-4s %d\n", $2, $1}'
echo "--- sizes per top dir"
for d in proj/*/; do total=0; while IFS= read -r f; do total=$(( total + $(wc -c < "$f") )); done < <(find "$d" -type f); printf '%-12s %4d\n' "${d#proj/}" "$total"; done
echo "--- largest"; find proj -type f -exec wc -c {} + | grep -v ' total$' | sort -rn | head -2 | awk '{print $2, $1}'
echo "--- empty"; find proj -type f -empty | sort
echo "--- depth"; find proj -mindepth 3 -type f | awk -F/ '{print NF - 1}' | sort -u | tr '\n' ' '; echo
echo "dirs=$(find proj -type d | wc -l) files=$(find proj -type f | wc -l)"
#### script: date range and schedule generation
#!/bin/bash
start=2026-11-13; days=6
is_weekend() { local dow; dow=$(date -u -d "$1" +%u); (( dow >= 6 )); }
for ((i = 0; i < days; i++)); do
  d=$(date -u -d "$start +$i day" +%Y-%m-%d)
  label=$(date -u -d "$d" '+%a %d %b')
  if is_weekend "$d"; then echo "$d ($label) weekend - skip"; else echo "$d ($label) run batch $(printf 'B%03d' $((i + 1)))"; fi
done
eom() { date -u -d "$(date -u -d "$1-01 +1 month" +%Y-%m-01) -1 day" +%d; }
for m in 2026-02 2024-02 2026-11 2026-12; do echo "$m has $(eom "$m") days"; done
age_days() { echo $(( ( $(date -u -d "$2" +%s) - $(date -u -d "$1" +%s) ) / 86400 )); }
echo "between: $(age_days 2026-01-01 2026-11-15) days"
quarter() { local m; m=$(date -u -d "$1" +%-m); echo "Q$(( (m - 1) / 3 + 1 ))"; }
echo "$(quarter 2026-02-10) $(quarter 2026-06-30) $(quarter 2026-11-15)"
ts=$(date -u -d '2026-11-15 13:45:10' +%s); echo "$ts $(date -u -d "@$ts" '+%H:%M') $(date -u -d "@$((ts + 3600 * 12))" '+%F %H')"
printf 'elapsed %02d:%02d:%02d\n' $((3725 / 3600)) $((3725 % 3600 / 60)) $((3725 % 60))
#### script: generated script execution and here-doc nesting
#!/bin/bash
cat > gen.sh <<'OUTER'
#!/bin/bash
name=${1:-world}
cat <<INNER
hello $name from generated script
args: $#
INNER
exit 7
OUTER
chmod +x gen.sh
./gen.sh; echo "rc=$?"
./gen.sh "quoted arg" extra; echo "rc=$?"
out=$(./gen.sh sub 2>&1 | head -1); echo "[$out]"
cat > lib.sh <<'EOF'
LIB_LOADED=1
lib_double() { echo $(( $1 * 2 )); }
EOF
cat > main.sh <<'EOF'
#!/bin/bash
here=$(cd "$(dirname "$0")" && pwd)
. "$here/lib.sh"
echo "loaded=$LIB_LOADED double=$(lib_double 21) base=$(basename "$0")"
EOF
chmod +x main.sh; ./main.sh
mkdir -p bin; mv main.sh lib.sh bin/; bin/main.sh
( cd bin && ./main.sh )
for n in 1 2; do
cat <<EOF
block $n: $(cat <<INNER
nested $n
INNER
)
EOF
done
