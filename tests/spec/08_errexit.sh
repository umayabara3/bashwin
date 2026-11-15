#### errexit stops script
set -e
echo before
false
echo never
#### errexit exit status
set -e
( exit 7 )
echo never
#### errexit not triggered in conditions
set -e
if false; then echo no; fi
false || echo "or ok"
false && echo no
! false
while false; do :; done
until true; do :; done
echo survived
#### errexit and-or last element
set -e
true && false
echo never
#### errexit middle of and-or
set -e
false && true
echo "survived $?"
#### errexit in function
set -e
f() { false; echo "never in f"; }
f
echo never
#### errexit function in condition is ignored
set -e
f() { false; echo "continues in f"; }
if f; then echo "f ok"; fi
f || echo no
echo end
#### errexit with command substitution assignment
set -e
x=$(false)
echo never
#### errexit local masks failure
set -e
f() { local x=$(false); echo "local ok"; }
f
echo end
#### errexit in pipeline
set -e
false | true
echo "pipe ok"
true | false
echo never
#### errexit pipefail
set -eo pipefail
false | true
echo never
#### errexit in subshell
set -e
( false; echo "never in sub" )
echo never
#### errexit subshell contained
set -e
( false; echo no ) || echo "sub failed handled"
echo end
#### errexit with exit trap
set -e
trap 'echo "trap status $?"' EXIT
false
echo never
#### errexit off again
set -e
set +e
false
echo "still here"
#### nounset stops script
set -u
echo "$nope"
echo never
#### nounset allows defaults and special
set -u
echo "${nope:-ok}" "${nope-ok}" "[${nope+x}]" $# "$@" "$*"
arr=()
echo "${#arr[@]}"
echo end
#### nounset positional
set -u
f() { echo "${1:-none}"; }
f
( echo "$1" ) 2>/dev/null || echo "unbound positional"
#### pipefail status
set -o pipefail
true | true; echo $?
(exit 2) | (exit 3) | true; echo $?
(exit 2) | true | (exit 0); echo $?
#### strict mode typical header
set -euo pipefail
IFS=$'\n\t'
items="a b"
for i in $items; do echo "[$i]"; done
count=$(printf '1\n2\n' | wc -l)
echo "count=$count"
grep -q zzz <<< "abc" || echo "grep miss handled"
echo done
#### error message then continue without errexit
nonexistent_command_abc 2>/dev/null
echo "st=$?"
echo continuing
#### exit in function exits script
f() { echo in; exit 3; echo no; }
f
echo never
#### exit inside pipeline stage only exits stage
echo x | { read l; exit 5; }
echo "after pipeline $?"
#### exit inside command substitution
v=$(echo a; exit 2; echo b)
echo "$v $?"
#### return outside function
return 2>/dev/null
echo "st=$? continues"
#### errexit and arithmetic
set -e
(( 1 ))
x=0
(( x )) || echo "zero handled"
(( x++ )) || true
echo "x=$x"
#### errexit negation and compound
set -e
! true
{ false; } || echo grouped
[[ a == b ]] || echo dbl
[ a = b ] || echo sgl
echo end
#### ERR trap with errexit
set -e
trap 'echo "ERR trap"' ERR
trap 'echo "EXIT trap"' EXIT
false
echo never
#### command not found status
set +e
nonexistent_xyz_123 2>/dev/null; echo $?
./nonexistent_script.sh 2>/dev/null; echo $?
#### expansion error discards the rest of the line
readonly RO=1
RO=2 2>/dev/null; echo "same line is skipped"
echo "next line st=$?"
for i in 1 2 3; do echo "i=$i"; echo $((1/0)) 2>/dev/null; echo never; done; echo never-same-line
echo "after loop st=$?"
f() { echo in-f; echo $((1/0)) 2>/dev/null; echo never-in-f; }
f; echo never-same-line
echo "after func st=$?"
( echo in-sub; echo $((1/0)) 2>/dev/null; echo never ); echo "subshell contained st=$?"
x=$(echo in-cs; echo $((1/0)) 2>/dev/null; echo never); echo "cmdsub st=$? [$x]"
(( 1/0 )) 2>/dev/null; echo "arith command only fails st=$?"
eval 'echo $((1/0)) 2>/dev/null; echo never'; echo "eval contained"
set -e
echo $((1/0)) 2>/dev/null; echo never
echo "errexit does not fire on expansion errors"
#### errexit ignores compound commands whose failure was in an ignored context
set -e
if true; then false && true; fi
echo "after if st=$?"
{ false && true; }
echo "after group"
for i in 1; do false && true; done
echo "after for"
case x in x) false && true;; esac
echo "after case"
n=0; while [ $n -lt 1 ]; do n=1; false && true; done
echo "after while"
f() { if true; then false && true; fi; }
f
echo "not reached: a function call is a simple command"
#### errexit still fires for a failing subshell and pipeline
set -e
( false && true )
echo "not reached: subshell"
#### ERR trap follows the same compound-command rule
trap 'echo ERR-fired' ERR
if true; then false && true; fi
{ false && true; }
echo "no trap yet"
false
echo "st=$?"
