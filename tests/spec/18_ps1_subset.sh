#### ps1 external command arguments are passed exactly
"$PY" -c 'import sys; sys.stdout.buffer.write(("|".join(sys.argv[1:])+"\n").encode())' "a b" 'c"d' 'e\f' 'g\"h' "tail\\" "" 'x y\' '-n' '%PATH%'
#### ps1 external exit status and conditions
"$PY" -c 'import sys; sys.exit(3)'; echo "st=$?"
"$PY" -c 'import sys; sys.exit(0)' && echo ok
if "$PY" -c 'import sys; sys.exit(1)'; then echo yes; else echo "no $?"; fi
! "$PY" -c 'import sys; sys.exit(1)'; echo "neg=$?"
nonexistent_tool_xyz 2>/dev/null; echo "missing=$?"
#### ps1 command substitution of an external command
v=$("$PY" -c 'import sys; sys.stdout.buffer.write(b"line1\nline2\n\n\n")')
echo "[$v]"
n=$("$PY" -c 'import sys; sys.stdout.buffer.write(b"42")')
echo $((n + 1))
e=$("$PY" -c 'import sys; sys.exit(7)'); echo "st=$? [$e]"
echo "inline $("$PY" -c 'import sys; sys.stdout.buffer.write(b"X\n")') end"
#### ps1 redirect external and builtin output to files
echo first > out.txt
"$PY" -c 'import sys; sys.stdout.buffer.write(b"second\n")' >> out.txt
echo third >> out.txt
[ -s out.txt ] && echo nonempty
"$PY" -c 'import sys; sys.stdout.buffer.write(open(sys.argv[1],"rb").read())' out.txt
: > out.txt
[ -s out.txt ] || echo emptied
echo x > /nonexistent-dir-bw/out.txt 2>/dev/null || echo "redirect failed $?"
#### ps1 stderr redirections
"$PY" -c 'import sys; sys.stdout.buffer.write(b"o\n"); sys.stdout.flush(); sys.stderr.write("e\n")' 2>/dev/null
"$PY" -c 'import sys; sys.stderr.write("e\n")' 2> err.txt
[ -s err.txt ] && echo captured-stderr
v=$("$PY" -c 'import sys; sys.stderr.buffer.write(b"E\n")' 2>&1); echo "[$v]"
v=$(echo to-stderr >&2; echo to-stdout); echo "[$v]"
echo both > both.txt 2>&1; [ -s both.txt ] && echo both-ok
{ echo g1; echo g2; } > grp.txt
"$PY" -c 'import sys; sys.stdout.buffer.write(open(sys.argv[1],"rb").read())' grp.txt
for i in 1 2; do echo "loop $i"; done > loop.txt
"$PY" -c 'import sys; sys.stdout.buffer.write(open(sys.argv[1],"rb").read())' loop.txt
#### ps1 environment export and unset reach child processes
export BW_A="hello world"
BW_B=shell-only
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_A","<unset>")+"|"+os.environ.get("BW_B","<unset>")+"\n").encode())'
BW_A=changed
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_A","<unset>")+"\n").encode())'
unset BW_A
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_A","<unset>")+"\n").encode())'
f() { local BW_C=inner; export BW_C; "$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_C","<unset>")+"\n").encode())'; }
f
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_C","<unset>")+"\n").encode())'
v=$(export BW_D=in-subshell; "$PY" -c 'import os,sys; sys.stdout.buffer.write(os.environ.get("BW_D","<unset>").encode())'); echo "$v"
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.environ.get("BW_D","<unset>")+"\n").encode())'
#### ps1 cd changes the directory of child processes
start=$PWD
"$PY" -c 'import os; os.mkdir("sub")'
cd sub
[ "$PWD" = "$start/sub" ] && echo pwd-ok
[ "$(pwd)" = "$PWD" ] && echo pwd-builtin-ok
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.path.basename(os.getcwd())+"\n").encode())'
echo x > here.txt
cd ..
[ -f sub/here.txt ] && echo file-in-sub
[ -d sub ] && [ ! -f sub ] && [ -e sub ] && echo dir
cd nonexistent 2>/dev/null || echo "cd failed $?"
cd - > /dev/null
"$PY" -c 'import os,sys; sys.stdout.buffer.write((os.path.basename(os.getcwd())+"\n").encode())'
v=$(cd ..; "$PY" -c 'import os,sys; sys.stdout.buffer.write(os.path.basename(os.getcwd()).encode())')
[ "$PWD" = "$start/sub" ] && echo "cd in substitution did not leak"
#### ps1 positional parameters set shift and at
set -- one "two words" three
echo "$# $1"
shift
echo "$# $1"
for a in "$@"; do echo "<$a>"; done
show() { echo "$# [$1] [$2]"; }
show "$@" extra
show
shift 5 || echo "shift failed"
set --
echo "$#"
for a in "$@"; do echo never; done
for a; do echo never; done
echo done
#### ps1 loops break continue and c-style for
for ((i = 0; i < 5; i++)); do
  if (( i == 1 )); then continue; fi
  if (( i == 4 )); then break; fi
  echo "i=$i"
done
for a in 1 2; do for b in x y z; do
  [ "$b" = y ] && continue 2
  [ "$a$b" = 2x ] && break 2
  echo "$a$b"
done; done
n=3; until [ "$n" -le 0 ]; do n=$((n - 1)); done; echo "n=$n"
while false; do :; done; echo "st=$?"
(( i = 10 )); (( i += 5 )); (( i-- )); (( ++i )); (( i -= 1 ))
echo "$i $((i * 2)) $((-i / 4)) $((i % 4)) $((i > 3 && i < 20)) $((!i)) $((i | 1)) $((i & 6)) $((0x10 + 010))"
#### ps1 parameter defaults and error exit
unset u; e=""
echo "[${u:-d1}] [${e:-d2}] [${e-d3}] [${u+alt}] [${e+alt}] [${e:+alt}]"
echo "[${u:=assigned}] [$u]"
echo "before"
echo "${missing:?must be set}" 2>/dev/null
echo "not reached"
#### ps1 nounset with positional parameters and defaults
set -u
f() { echo "${1:-none} $#"; }
f; f x
echo "${UNSET_VAR:-fallback}"
echo "$UNSET_VAR_2" 2>/dev/null
echo "not reached"
#### ps1 functions return values recursion and dynamic dispatch
fact() { if [ "$1" -le 1 ]; then echo 1; return; fi; local sub; sub=$(fact $(( $1 - 1 ))); echo $(( $1 * sub )); }
fact 10
status() { return "$1"; }
status 0 && echo zero
status 3 || echo "three $?"
status 300; echo "$?"
cmd=status; "$cmd" 4; echo "dyn $?"
cmd=echo; "$cmd" via-builtin
true() { echo "function wins"; }
true
counter=0
bump() { counter=$((counter + 1)); }
bump; bump; echo "counter=$counter"
#### ps1 case patterns classes and quoting
for w in apple Banana 42 a-b "x y" '*' ''; do
  case "$w" in
    [[:upper:]]*) echo "upper:$w" ;;
    [0-9][0-9]) echo "two digits" ;;
    *-*) echo "dash" ;;
    "*") echo "literal star" ;;
    *" "*) echo "space" ;;
    "") echo "empty" ;;
    a?p*|z) echo "apple-like" ;;
    *) echo "other" ;;
  esac
done
case abc in [!a]*) echo no ;; [a-c][^x]?) echo "class ok" ;; esac
#### ps1 tilde home and string tests
HOME=/custom/home
echo ~ ~/sub "~" a~b
x=~/data; echo "$x"
[[ "abc" < "abd" ]] && echo lt
[[ -n "$HOME" && ! -z "$HOME" ]] && echo nonempty
[ "$HOME" != "" ] && echo set
[[ $HOME == /custom/* ]] && echo prefix
#### ps1 errexit with external commands
set -e
"$PY" -c 'import sys; sys.exit(0)'
"$PY" -c 'import sys; sys.exit(2)' || echo "handled $?"
if "$PY" -c 'import sys; sys.exit(1)'; then echo no; fi
echo before
"$PY" -c 'import sys; sys.exit(9)'
echo "not reached"
#### ps1 output bytes are exact
echo "日本語 テスト"
echo 'single $x `bt` "dq"' "tab	end"
echo "back\\slash \$dollar \`tick\`"
x='a  b'; echo "$x" "[$x]"
echo -n "no newline"; echo
echo ""; echo
echo "curly “quotes” and ‘single’"
