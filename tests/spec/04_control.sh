#### if elif else
x=2
if [ $x -eq 1 ]; then echo one
elif [ $x -eq 2 ]; then echo two
else echo other; fi
if false; then echo no; fi; echo "st=$?"
if true; then :; fi; echo "st=$?"
#### if with command status and negation
if ! false; then echo negated; fi
if echo cond >/dev/null; then echo yes; fi
if grep -q b <<< abc; then echo found; fi
! true; echo $?
! false; echo $?
#### and-or lists
true && echo a
false && echo b
false || echo c
true || echo d
false && echo e || echo f
true && false || echo g
true && true && echo h
false || false || echo i
echo "st=$?"
#### for loops
for i in 1 2 3; do echo $i; done
for i in a "b c" d; do echo "<$i>"; done
for i; do echo never; done
set -- p q
for i; do echo $i; done
for i in; do echo never; done
echo end
#### c-style for
for ((i=0; i<3; i++)); do echo $i; done
for ((i=10, j=0; i>j; i-=3, j++)); do echo "$i $j"; done
for (( ; ; )); do break; done; echo out
#### while and until
i=0
while [ $i -lt 3 ]; do echo $i; i=$((i+1)); done
until [ $i -le 0 ]; do i=$((i-1)); echo $i; done
while false; do echo never; done; echo "st=$?"
#### break and continue
for i in 1 2 3 4 5; do
  [ $i -eq 2 ] && continue
  [ $i -eq 4 ] && break
  echo $i
done
echo "after=$i"
#### nested break levels
for i in 1 2; do
  for j in a b c; do
    [ $j = b ] && continue 2
    [ $i = 2 ] && break 2
    echo $i$j
  done
done
echo done
#### case basics
for x in apple banana cherry 123 ""; do
  case $x in
    apple) echo A;;
    b*) echo B;;
    [0-9]*) echo NUM;;
    "") echo EMPTY;;
    *) echo OTHER;;
  esac
done
#### case alternation and fallthrough
case b in a|b|c) echo abc;; esac
case x in (x) echo paren;; esac
case 1 in 1) echo one;& 2) echo two;; 3) echo three;; esac
case 1 in 1) echo first;;& [0-9]) echo digit;;& *) echo any;; esac
case nomatch in a) echo a;; esac; echo "st=$?"
#### case with quotes and vars
v="a b"
case "$v" in "a b") echo spaced;; esac
p="a*"
case abc in $p) echo glob-var;; esac
case "a*" in "$p") echo literal-var;; esac
case abc in "$p") echo wrong;; *) echo not-literal;; esac
#### case character classes
for c in a Z 5 _ ' '; do
  case "$c" in
    [[:upper:]]) echo upper;;
    [[:lower:]]) echo lower;;
    [[:digit:]]) echo digit;;
    [[:space:]]) echo space;;
    *) echo other;;
  esac
done
#### while read loop
printf 'a 1\nb 2\nc 3\n' > data.txt
while read -r name num; do echo "$num:$name"; done < data.txt
sum=0
while read -r _ n; do sum=$((sum+n)); done < data.txt
echo $sum
#### while read from pipe (subshell)
count=0
printf 'x\ny\n' | while read -r l; do count=$((count+1)); echo "in:$count"; done
echo "out:$count"
#### loop with redirect out
for i in 1 2 3; do echo "line $i"; done > out.txt
cat out.txt
wc -l < out.txt
#### group commands
{ echo a; echo b; } | tr a-z A-Z
{ echo x; false; }; echo $?
#### subshell isolation
x=outer
( x=inner; echo $x )
echo $x
( cd /; [ "$PWD" != "$OLDPWD" ] && echo moved-in-subshell )
[ "$(pwd)" = "$HOME" ] && echo "cwd preserved"
( exit 7 ); echo $?
#### subshell exit does not exit parent
( echo in; exit 1; echo never )
echo "parent continues $?"
#### arithmetic command
(( 1 + 1 )); echo $?
(( 0 )); echo $?
x=5
(( x > 3 )) && echo big
(( x++ )); echo $x
if (( x == 6 )); then echo six; fi
#### double bracket tests
[[ abc == abc ]] && echo eq
[[ abc == a* ]] && echo glob
[[ abc != b* ]] && echo ne
[[ abc < abd ]] && echo lt
[[ -z "" && -n x ]] && echo zn
[[ 5 -gt 3 || 1 -gt 2 ]] && echo num
[[ ! -e /nonexistent/x ]] && echo notexist
x=
[[ $x == "" ]] && echo empty-unquoted-ok
y="a b"
[[ $y == "a b" ]] && echo nosplit
#### double bracket regex
[[ abc123 =~ ^[a-z]+[0-9]+$ ]] && echo m1
[[ abc =~ b ]] && echo m2
[[ abc =~ ^b ]] || echo m3
re='^([a-z]+)@([a-z.]+)$'
[[ user@example.com =~ $re ]] && echo "${BASH_REMATCH[1]} at ${BASH_REMATCH[2]}"
[[ "a.c" =~ a\.c ]] && echo m4
[[ "abc" =~ "a.c" ]] || echo m5
[[ foo.txt =~ \.(txt|log)$ ]] && echo m6
#### double bracket pattern quoting
p='a*'
[[ abc == $p ]] && echo pat
[[ abc == "$p" ]] || echo lit
[[ 'a*' == "$p" ]] && echo lit-eq
#### double bracket grouping
[[ ( a == a || a == b ) && c == c ]] && echo grouped
#### test builtin forms
test 1 -eq 1 && echo t1
[ a = a ] && echo t2
[ a != b ] && echo t3
[ -n "x" ] && echo t4
[ -z "" ] && echo t5
[ "x" ] && echo t6
[ "" ] || echo t7
[ 1 -lt 2 -a 3 -gt 2 ] && echo t8
[ 1 -gt 2 -o 3 -gt 2 ] && echo t9
[ ! -f /nonexistent ] && echo t10
[ \( a = a \) ] && echo t11
#### test file operators
touch file; mkdir dir
[ -e file ] && echo e
[ -f file ] && echo f
[ -d dir ] && echo d
[ -f dir ] || echo notf
[ -s file ] || echo empty
echo x > file
[ -s file ] && echo nonempty
[ -r file ] && [ -w file ] && echo rw
[ file -nt file ] || [ file -ot file ] || echo not-newer-or-older-than-itself
#### select-like menu with case in function
choose() { case $1 in 1) echo first;; 2) echo second;; *) return 1;; esac; }
choose 1; choose 2; choose 9 || echo invalid
#### deeply nested control
for i in 1 2; do
  if [ $i -eq 1 ]; then
    for j in a b; do
      case $j in a) while true; do echo "$i$j"; break; done;; *) echo other;; esac
    done
  else
    echo second
  fi
done
#### multi-line conditions
if [ 1 -eq 1 ] &&
   [ 2 -eq 2 ]
then
  echo both
fi
true |
  cat
echo ok
#### empty function body and colon
f() { :; }
f; echo $?
: ${unset_var:=default}
echo $unset_var
