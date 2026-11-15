#### define and call
greet() { echo "hello $1"; }
greet world
function alt { echo "alt $1"; }
alt form
function both() { echo both; }
both
#### function args
f() { echo "$# [$1] [$2] [$*]"; }
f
f a
f "a b" c
#### return values
ok() { return 0; }
ng() { return 42; }
ok; echo $?
ng; echo $?
last() { false; }
last; echo $?
implicit() { true; }
implicit; echo $?
#### local variables
x=global
f() { local x=local; echo $x; }
f; echo $x
g() { x=changed; }
g; echo $x
h() { local y; y=1; echo "y=$y"; }
h; echo "y=[$y]"
#### local shadows and dynamic scope
v=outer
inner() { echo "inner sees $v"; }
outer() { local v=middle; inner; }
outer
inner
#### local with command substitution status
f() { local r=$(false); echo "st=$?"; }
f
g() { local r; r=$(false); echo "st=$?"; }
g
#### recursion
fact() { if [ $1 -le 1 ]; then echo 1; else echo $(( $1 * $(fact $(( $1 - 1 ))) )); fi; }
fact 5
fact 10
fib() { local n=$1; (( n < 2 )) && { echo $n; return; }; echo $(( $(fib $((n-1))) + $(fib $((n-2))) )); }
fib 10
#### recursion with accumulator (no subshell)
total=0
sumto() { (( $1 == 0 )) && return; total=$((total + $1)); sumto $(( $1 - 1 )); }
sumto 100
echo $total
#### function output capture
get() { echo "captured value"; }
v=$(get)
echo "[$v]"
#### function modifies positional of caller? no
f() { shift; echo "in: $*"; }
set -- a b c
f x y z
echo "out: $*"
#### function with redirection
log() { echo "log: $*"; } >&2
log hidden 2>/dev/null
out() { echo "to file"; } > fn.txt
out; cat fn.txt
#### function in pipeline and subshell
up() { tr a-z A-Z; }
echo hello | up
( up <<< inner )
#### functions calling functions
a() { b "$@" | c; }
b() { for x in "$@"; do echo "$x"; done; }
c() { sort -r; }
a 1 3 2
#### unset function
f() { echo f; }
f
unset -f f
f 2>/dev/null; echo $?
#### function overrides command
echo() { command echo "wrapped: $*"; }
echo test
unset -f echo
echo plain
#### FUNCNAME
f() { echo "in ${FUNCNAME[0]}"; g; }
g() { echo "in ${FUNCNAME[0]} from ${FUNCNAME[1]}"; }
f
#### return from nested loops
f() { for i in 1 2 3; do for j in a b; do [ $i$j = 2a ] && return 5; echo $i$j; done; done; }
f; echo "ret=$?"
#### declare -f and type
f() { :; }
declare -F f
type -t f
type -t echo
type -t if
type -t nonexistent_cmd_xyz; echo "st=$?"
#### early return and cleanup pattern
process() {
  local f=$1
  [ -n "$f" ] || { echo "no arg"; return 1; }
  echo "processing $f"
}
process; echo $?
process item; echo $?
#### local array and nameless args
f() { local args=("$@"); echo "${#args[@]}: ${args[*]}"; local i; for i in "${!args[@]}"; do echo "$i=${args[i]}"; done; }
f x "y z"
#### function sets global via printf -v
setv() { printf -v "$1" '%s' "$2"; }
setv myvar "hello there"
echo "$myvar"
#### default args pattern
f() { local a=${1:-default} b=${2:-$a}; echo "$a $b"; }
f; f x; f x y
#### command builtin bypass
ls() { echo "fake ls"; }
ls
command -v ls >/dev/null && echo exists
#### functions and exit status chains
check() { [ "$1" -gt 0 ] 2>/dev/null; }
check 5 && echo positive
check 0 || echo not-positive
check abc || echo not-number
#### large recursion depth
depth() { (( $1 >= 200 )) && { echo "reached $1"; return; }; depth $(( $1 + 1 )); }
depth 0
