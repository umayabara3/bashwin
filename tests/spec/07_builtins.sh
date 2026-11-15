#### read basic
echo "one two three" > in.txt
read a b c < in.txt; echo "$c $b $a"
read a b < in.txt; echo "[$a] [$b]"
read a < in.txt; echo "[$a]"
read < in.txt; echo "[$REPLY]"
#### read whitespace handling
printf '  lead  trail  \n' > w.txt
read v < w.txt; echo "[$v]"
read < w.txt; echo "[$REPLY]"
IFS= read -r v < w.txt; echo "[$v]"
#### read -r and backslash
printf 'a\\tb c\\ d\n' > b.txt
read -r x y < b.txt; echo "[$x] [$y]"
read x y < b.txt; echo "[$x] [$y]"
#### read with IFS
echo "a:b:c:d" > c.txt
IFS=: read p q r < c.txt; echo "$p|$q|$r"
IFS=: read -r p q < c.txt; echo "$p|$q"
echo "$IFS" | wc -c
#### read eof status
printf 'no newline' > n.txt
read -r v < n.txt; echo "st=$? [$v]"
read -r v < /dev/null; echo "st=$? [$v]"
#### read loop last line without newline
printf 'a\nb' > l.txt
while read -r l || [ -n "$l" ]; do echo "<$l>"; done < l.txt
#### read -n and -d
echo abcdef > n.txt
read -n 3 v < n.txt; echo "[$v]"
printf 'x;y;z' > d.txt
read -d ';' v < d.txt; echo "[$v]"
#### read multiple lines sequentially
printf '1\n2\n3\n' > s.txt
{ read a; read b; read c; } < s.txt
echo $a$b$c
#### getopts basic
parse() {
  local OPTIND=1 opt
  while getopts "ab:c" opt; do
    case $opt in
      a) echo "flag a";;
      b) echo "b=$OPTARG";;
      c) echo "flag c";;
      *) echo "bad"; return 1;;
    esac
  done
  shift $((OPTIND-1))
  echo "rest: $*"
}
parse -a -b val -c file1 file2
parse -ac -bjoined x
parse -- -a
parse
#### getopts silent mode
parse() {
  local OPTIND=1 opt
  while getopts ":x:y" opt; do
    case $opt in
      x) echo "x=$OPTARG";;
      y) echo y;;
      :) echo "missing arg for $OPTARG";;
      \?) echo "unknown $OPTARG";;
    esac
  done
}
parse -y -z -x
parse -x v
#### set positional and options
set -- a b c
echo $# $2
set -- 
echo $#
set x y; echo $1
echo $- | grep -q e || echo "no errexit"
set -e; echo $- | grep -q e && echo "errexit on"; set +e
#### set -u
set -u
x=defined
echo "$x ${undef:-fallback}"
( echo "$undefined_var" ) 2>/dev/null; echo "st=$?"
set +u
echo "[$undefined_var]"
#### set -x trace
set -x
echo traced 2>/dev/null
x=1
set +x 2>/dev/null
echo "trace off"
#### shift
set -- 1 2 3 4 5
shift; echo $*
shift 2; echo $*
shift 5 2>/dev/null; echo "st=$? $*"
#### eval
cmd='echo evaluated'
eval $cmd
eval "x=5; y=\$((x*2))"; echo $y
v=name; eval "$v=value"; echo $name
eval 'for i in 1 2; do echo $i; done'
eval "false"; echo $?
#### source
cat > lib.sh <<'EOF'
lib_var=from_lib
lib_func() { echo "lib func $1"; }
return 3
echo never
EOF
source ./lib.sh; echo "st=$?"
echo $lib_var; lib_func x
. ./lib.sh
echo "dot ok"
#### source with args
echo 'echo "args: $# $1"' > a.sh
set -- orig
source ./a.sh passed
echo "$1"
source ./a.sh
#### trap EXIT
trap 'echo "exit trap $?"' EXIT
echo main
exit 4
#### trap EXIT in function and subshell
( trap 'echo sub-exit' EXIT; echo in-sub )
echo after-sub
trap 'echo outer-exit' EXIT
#### trap ERR
trap 'echo "err at status $?"' ERR
false
true
false || true
if false; then :; fi
echo done
#### trap reset and list
trap 'echo x' EXIT
trap - EXIT
trap 'echo final' EXIT
trap -p EXIT
#### export and env
export EXP=exported
PLAIN=plain
$PY -c 'import os; print(os.environ.get("EXP"), os.environ.get("PLAIN"))'
INLINE=inline $PY -c 'import os; print(os.environ.get("INLINE"))'
echo "[${INLINE}]"
export A=1 B=2; $PY -c 'import os; print(os.environ["A"]+os.environ["B"])'
export -n A; $PY -c 'import os; print(os.environ.get("A"))'
#### export in function and subshell
f() { export FV=fv; local LV=lv; }
f
$PY -c 'import os; print(os.environ.get("FV"), os.environ.get("LV"))'
( export SUB=1 ); echo "[${SUB}]"
#### temp env for function and builtin
show() { echo "T=$T"; }
T=temp show
echo "after: [$T]"
#### readonly
readonly RO=1
RO=2 2>/dev/null
echo "st=$? $RO"
( unset RO ) 2>/dev/null; echo "st=$?"
#### declare forms
declare x=1
declare -i n=5; n+=3; echo $n
n="2*3"; echo $n
declare -r c=const; echo $c
declare -u up=lower; echo $up
declare -l low=UPPER; echo $low
declare -x ex=1; $PY -c 'import os; print(os.environ["ex"])'
#### declare -p
x="a b"; declare -p x
a=(1 "2 3"); declare -p a
declare -i i=3; declare -p i
#### unset
x=1; unset x; echo "[${x-unset}]"
f() { :; }; unset -f f; type f 2>/dev/null; echo $?
unset nonexistent; echo $?
#### let
let "x = 2 + 3"; echo $x
let x++ "y = x * 2"; echo $x $y
let "z = 0"; echo "st=$?"
#### type and command -v
type echo | head -1
command -v echo
command -v nonexistent_xyz; echo "st=$?"
type nonexistent_xyz 2>/dev/null; echo "st=$?"
#### test string operators
[ abc \< abd ] && echo lt
[ "a b" = "a b" ] && echo eq-space
[ -z "$unset" ] && echo z
x="-n"; [ "$x" = "-n" ] && echo dash
[ "!" = "!" ] && echo bang
#### test numeric errors
[ abc -eq 1 ] 2>/dev/null; echo "st=$?"
[ 1 -eq 1 ]; echo "st=$?"
[ ] ; echo "st=$?"
#### colon and true false
: ignored args $(echo side-effect >&2) 2>/dev/null
true; echo $?
false; echo $?
#### cd and pwd
mkdir -p a/b
cd a/b; basename "$(pwd)"
cd ..; basename "$(pwd)"
cd - >/dev/null; basename "$PWD"
cd; [ "$PWD" = "$HOME" ] && echo home
cd /nonexistent 2>/dev/null; echo "st=$?"
#### pushd popd
mkdir -p p1/p2
pushd p1 >/dev/null; basename "$PWD"
pushd p2 >/dev/null; basename "$PWD"
popd >/dev/null; basename "$PWD"
popd >/dev/null; [ "$PWD" = "$HOME" ] && echo back
#### exit codes
( exit 0 ); echo $?
( exit 255 ); echo $?
( exit 256 ); echo $?
( exit -1 ); echo $?
#### wait for multiple jobs
for i in 1 2 3; do ( sleep 0.0$i; echo "job $i" ) & done
wait
echo all-done
#### kill background job
sleep 30 &
pid=$!
kill $pid
wait $pid 2>/dev/null
echo "killed st>128: $(( $? > 128 ))"
#### mapfile variants
printf 'a\nb\nc\n' | { mapfile -t arr; echo "${#arr[@]} ${arr[0]}${arr[2]}"; }
mapfile arr2 < <(printf 'x\ny\n'); printf '[%s]' "${arr2[@]}"; echo
#### printf to array element and var
arr=(); printf -v 'arr[2]' '%s' two; echo "${arr[2]}"
#### exec replaces shell
echo before
exec echo "exec'd"
echo never
#### OPTIND reset between calls
f() { local OPTIND=1 o; while getopts "a" o; do echo "got $o"; done; }
f -a; f -a
#### shopt nocasematch
shopt -s nocasematch
[[ ABC == abc ]] && echo ci
case HELLO in hello) echo ci-case;; esac
shopt -u nocasematch
[[ ABC == abc ]] || echo cs
