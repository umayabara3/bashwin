#### date formats fixed epoch
date -u -d @0 +%Y-%m-%d
date -u -d @1700000000 '+%Y-%m-%d %H:%M:%S'
date -u -d @1700000000 +%s
date -u -d @1700000000 '+%a %b %e %j %u %w'
date -u -d @1700000000 '+%y%m%d %I%p %Z'
date -u -d @86400 +%F
date -u -d @1700000000 +%T
date -u -d @1700000000 '+%A %B'
date -u -d @1700000000 +%D
date -u -d @1700000000 +%R
#### date string parsing
date -u -d '2026-11-15' +%s
date -u -d '2026-11-15 12:34:56' +%s
date -u -d '2026-01-31 +1 day' +%F
date -u -d '2026-03-01 -1 day' +%F
date -u -d '2026-01-15 +1 month' +%F
date -u -d '2026-01-15 1 year ago' +%F
date -u -d '2024-02-28 +2 days' +%F
date -u -d '2026-11-15 +3 hours' '+%F %H'
date -u -d '2026-11-15T08:00:00' +%H
date -u -d '20261115' +%F
#### date default and arithmetic
date -u -d @0
[ "$(date +%Y)" -ge 2024 ] && echo year-ok
s=$(date +%s); [ "$s" -gt 1700000000 ] && echo epoch-ok
d1=$(date -u -d '2026-11-15' +%s); d2=$(date -u -d '2026-11-01' +%s); echo $(( (d1-d2)/86400 ))
#### date invalid
date -d 'not a date at all' 2>/dev/null; echo "st=$?"
#### printf time format
printf '%(%Y-%m-%d)T\n' 0
printf '%(%H:%M)T\n' 3600
#### sleep
sleep 0.1; echo slept
sleep 0; echo "st=$?"
#### xargs
printf 'a\nb\nc\n' | xargs echo
printf 'a b c' | xargs -n 1 echo
printf 'a\nb\n' | xargs -I{} echo "item: {}"
printf '1 2 3 4 5' | xargs -n 2 echo
echo "'quoted arg' plain" | xargs -n 1 echo
printf '' | xargs -r echo never; echo "st=$?"
printf 'x\0y' | xargs -0 -n1 echo
mkdir xd; printf 'f1\nf2\n' | xargs -I{} touch xd/{}; ls xd
#### xargs with find
mkdir xf; touch xf/a.txt xf/b.txt
find xf -name '*.txt' | sort | xargs -n1 basename
find xf -type f | xargs wc -l | tail -1
#### env and printenv
export MYVAR=hello
env | grep '^MYVAR='
printenv MYVAR
printenv NOPE; echo "st=$?"
env FOO=bar $PY -c 'import os; print(os.environ["FOO"])'
env -u MYVAR $PY -c 'import os; print(os.environ.get("MYVAR"))'
#### which and command
command -v cat >/dev/null && echo has-cat
which nonexistent_tool_xyz >/dev/null 2>&1; echo "st=$?"
#### true false colon exit codes via python
$PY -c 'import sys; sys.exit(3)'; echo $?
$PY -c 'print("from python")'
echo piped | $PY -c 'import sys; print(sys.stdin.read().strip().upper())'
$PY -c 'import sys; sys.stderr.write("err\n"); print("out")' 2>/dev/null
$PY -c 'import sys; print(sys.argv[1:])' a "b c" 'd"e'
#### external in pipeline both sides
$PY -c 'print("x\ny\nz")' | grep -c .
seq 1 3 | $PY -c 'import sys; print(sum(int(l) for l in sys.stdin))'
$PY -c 'print("a b")' | { read -r p q; echo "$q$p"; }
#### external with redirects
$PY -c 'print("to file")' > ext.txt; cat ext.txt
$PY -c 'import sys; print(sys.stdin.read().strip())' < ext.txt
$PY -c 'import sys; sys.stderr.write("E\n")' 2> err.txt; cat err.txt
$PY -c 'import sys; print("o"); sys.stderr.write("e\n")' > both.txt 2>&1; sort both.txt
$PY -c 'print("appended")' >> ext.txt; wc -l < ext.txt
#### external cwd and env inheritance
mkdir sub; cd sub
$PY -c 'import os; print(os.path.basename(os.getcwd()))'
cd ..
X=1 Y=2 $PY -c 'import os; print(os.environ["X"], os.environ["Y"])'
#### heredoc to external
$PY - <<'EOF'
print("python from heredoc")
EOF
$PY -c 'import sys; print(len(sys.stdin.read()))' <<< "12345"
#### command substitution of external
v=$($PY -c 'print("captured")'); echo "[$v]"
n=$($PY -c 'import sys; sys.exit(9)'); echo "st=$?"
lines=$($PY -c 'print("a\nb\nc")' | wc -l); echo $lines
#### script calling script
cat > child.sh <<'EOF'
#!/bin/bash
echo "child args: $* (${#})"
echo "child sees EXPORTED=$EXPORTED LOCALV=[$LOCALV]"
exit 6
EOF
chmod +x child.sh
export EXPORTED=yes; LOCALV=no
./child.sh a b; echo "st=$?"
bash_like=$(./child.sh x | head -1); echo "$bash_like"
#### sourced vs executed scope
echo 'SV=set_by_script' > sv.sh; chmod +x sv.sh
echo '#!/bin/sh' | cat - sv.sh > sv2.sh; chmod +x sv2.sh
./sv2.sh; echo "[${SV}]"
. ./sv.sh; echo "[${SV}]"
#### uname hostname whoami exist
[ -n "$(uname)" ] && echo uname-ok
[ -n "$(hostname)" ] && echo hostname-ok
[ -n "$(whoami)" ] && echo whoami-ok
[ "$(nproc)" -ge 1 ] && echo nproc-ok
#### random and seconds
r=$RANDOM; [ "$r" -ge 0 ] && [ "$r" -le 32767 ] && echo random-ok
[ "$RANDOM$RANDOM$RANDOM" != "$RANDOM$RANDOM$RANDOM" ] && echo random-varies
[ "$SECONDS" -ge 0 ] && echo seconds-ok
#### LINENO
echo $LINENO
echo $LINENO
f() { echo $LINENO; }
f
#### dollar-dollar and bang
[ "$$" -gt 0 ] && echo pid-ok
sleep 0 & [ -n "$!" ] && echo bang-ok; wait
#### timeout
timeout 5 echo fast; echo "st=$?"
timeout 0.3 sleep 5; echo "st=$?"
timeout 2 $PY -c 'import time; time.sleep(0.05); print("done")'; echo "st=$?"
#### nested quotes in command substitution
echo "$(echo "a b" | sed "s/ /_/")"
echo "$(printf '%s\n' "x y" 'p q' | sort | tr '\n' ',')"
#### here-doc with command in loop
for n in 1 2; do
cat <<EOF
item $n: $(( n * 10 ))
EOF
done
#### arithmetic in various contexts
a=(5 6 7); i=1
echo ${a[i+1]} ${a[$((i-1))]} ${a[$i]}
x=3; s="abcdefgh"; echo ${s:x:x-1} ${s:$((x*2))}
for ((i=0;i<${#a[@]};i++)); do printf '%d ' $((a[i]*2)); done; echo
#### string manipulation cookbook
s="  padded  "; t="${s#"${s%%[![:space:]]*}"}"; t="${t%"${t##*[![:space:]]}"}"; echo "[$t]"
csv="a,b,c"; IFS=, read -ra f <<< "$csv"; echo ${#f[@]} ${f[1]}
path="a/b/c"; echo "${path//\//.}"
str=hello; echo "${str:0:1}" "${str: -1}" "${#str}"
rep=$(printf '=%.0s' {1..10}); echo $rep
up=$(echo mixed | tr '[:lower:]' '[:upper:]'); echo $up
[[ "hello world" == *"o w"* ]] && echo contains
x="a.b.c"; echo "${x%%.*}" "${x#*.}" "${x%.*}" "${x##*.}"
#### number formatting
printf '%05d\n' 42
printf '%.3f\n' 3.14159
printf '%8.2f|\n' 3.14159
printf '%-8s|%8s|\n' left right
printf '%x\n' 255
printf '%d items\n' "$(seq 1 7 | wc -l)"
n=1234567; printf "%'d\n" $n 2>/dev/null | wc -l
#### nproc-independent parallel pattern
for i in 1 2 3; do ( echo "task $i" > "out.$i" ) & done; wait
cat out.1 out.2 out.3
#### large loop performance sanity
s=0; for i in $(seq 1 2000); do s=$((s+i)); done; echo $s
i=0; while [ $i -lt 1000 ]; do i=$((i+1)); done; echo $i
