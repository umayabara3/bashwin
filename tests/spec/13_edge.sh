#### quoting inside command substitution inside quotes
echo "a $(echo "b $(echo 'c d')" | tr a-z A-Z) e"
echo "$(echo ')')" "$(echo '(')"
echo "$(case x in x) echo matched;; esac)"
echo "`echo "inner \`echo nested\`"`"
#### case inside command substitution with unbalanced paren
r=$(case abc in a*) echo starts-a ;; *) echo other ;; esac); echo $r
#### backslash handling
echo \a \\ \$ \" \'
echo "\a \\ \$ \" \n"
echo '\a \\ \$'
echo a\
b
printf '%s\n' 'x\ny' "x\ny" x\ny
#### dollar quoting variants
x=val
echo "$x" "${x}" "$x"y "${x}y" "$xy" "\$x" '$x' $'$x'
echo "${x}$x${x}"
echo $x$x
#### empty and whitespace args
f() { echo "$#"; }
f "" '' "$e" $e "  " ''""
f "$@" "$*"
set -- "" ""; f "$@"; f "$*"; f $@ ; f $*
#### word splitting edge cases
x='  a  b  '
set -- $x; echo "$#:$1:$2"
set -- x$x; echo "$#:$1:$2"
set -- $x"y"; echo "$#:$1:$2"
set -- "$x"y; echo "$#:[$1]"
IFS=; set -- $x; echo "$#:[$1]"; unset IFS
#### glob chars in variables and quoting
touch 'a b.txt' c.txt
for f in *.txt; do echo "[$f]"; done
p="*.txt"; for f in $p; do echo "[$f]"; done
for f in "$p"; do echo "[$f]"; done
echo [abc].txt "[abc].txt" \[abc\].txt
q='?'; echo ${q}.txt
#### glob with special names [posix]
touch -- '-dash' 'has*star' '[bracket]' 'q?mark'
echo *dash
echo has\**
echo \[*
ls -- *mark
#### nested arrays and indirection
a=(x y z); idx=(2 0 1)
for i in "${idx[@]}"; do printf '%s ' "${a[$i]}"; done; echo
ref=a[1]; echo "${!ref}"
n=2; echo "${a[n]}" "${a[$n]}" "${a[n-1]}" "${a[$((n-2))]}"
#### array holes and iteration order
a=(); a[5]=five; a[2]=two; a[9]=nine
echo "${a[@]}" "${!a[@]}" ${#a[@]}
for k in "${!a[@]}"; do printf '%s:%s ' "$k" "${a[$k]}"; done; echo
a+=(ten); echo "${!a[@]}"
#### array quoting forms
a=("a b" "" c)
printf '<%s>' "${a[@]}"; echo
printf '<%s>' "${a[*]}"; echo
printf '<%s>' ${a[@]}; echo
printf '<%s>' "x${a[@]}y"; echo
b=("${a[@]/#/pre-}"); printf '<%s>' "${b[@]}"; echo
#### unset array elements in loop
a=(1 2 3 4 5 6)
for i in "${!a[@]}"; do (( a[i] % 2 == 0 )) && unset 'a[i]'; done
echo "${a[@]}"
a=("${a[@]}"); echo "${!a[@]}"
#### string to array by IFS and back
s="a:b:c"; IFS=: read -ra parts <<< "$s"
echo "${#parts[@]}"
joined=$(IFS=-; echo "${parts[*]}"); echo "$joined"
old=$IFS; IFS=,; out="${parts[*]}"; IFS=$old; echo "$out"
#### arithmetic edge cases
echo $(( 7 / 2 )) $(( -7 / 2 )) $(( 7 % -3 )) $(( 2 ** 10 )) $(( 1 << 62 ))
echo $(( 9223372036854775807 + 1 ))
echo $(( 0x7fffffffffffffff )) $(( -9223372036854775807 - 1 ))
echo $(( 1 ? 2 : 3 )) $(( 0 ? 2 : 3 )) $(( 1 ? 0 ? 4 : 5 : 6 ))
x=3; echo $(( x += 2, x * 2 )) $x
echo $(( 010 + 0x10 + 10 )) $(( 16#ff )) $(( 36#z )) $(( 2#1111 ))
echo $(( (2 + 3) * (4 - 1) )) $(( 2 + 3 * 4 - 1 )) $(( 10 - 2 - 3 )) $(( 2 ** 3 ** 2 ))
echo $(( !0 + !1 )) $(( ~0 )) $(( 5 > 3 && 2 > 1 )) $(( 5 > 3 || 1 / 0 ))
#### arithmetic division by zero
echo $(( 1 / 0 )) 2>/dev/null; echo "st=$?"
(( x = 5 % 0 )) 2>/dev/null; echo "st=$?"
echo continues
#### arithmetic with spaces and newlines
echo $((
  1 +
  2
))
x=5
if (( x > 3 &&
      x < 10 )); then echo inrange; fi
#### integer comparisons with leading zeros and negatives
[ 010 -eq 10 ] && echo dec
(( 010 == 8 )) && echo oct
[ -5 -lt 3 ] && echo neg
[[ 10 -gt 9 ]] && echo numeric
[[ 10 > 9 ]] || echo lexical
#### if with complex conditions
a=5; b=10; s="text"
if [ "$a" -lt "$b" ] && [ -n "$s" ] || [ -z "$s" ]; then echo c1; fi
if [[ $a -lt $b && ( -n $s || -z $s ) ]]; then echo c2; fi
if (( a < b )) && [[ $s == t* ]]; then echo c3; fi
if ! [ "$a" -gt "$b" ]; then echo c4; fi
if [ "$a" -gt "$b" ]; then echo no; elif [ "$a" -eq 5 ]; then echo c5; fi
#### nested functions and variable scope
outer() { local v=1; inner() { v=$((v+1)); echo "inner v=$v"; }; inner; echo "outer v=$v"; }
outer; echo "global v=[${v:-unset}]"
inner; echo "global v=[${v:-unset}]"
#### local and unset interplay
x=global
f() { local x=local; unset x; echo "after unset: [${x:-empty}]"; }
f; echo $x
g() { local x; echo "[${x-unset}]"; x=set; echo "[$x]"; }
g; echo $x
#### positional params in functions and set
f() { set -- new1 new2; echo "$1 $#"; }
set -- old; f; echo "$1 $#"
g() { echo "$0" | grep -c case; echo "${0##*/}"; }
g
#### shift in loops
set -- a b c d
while [ $# -gt 0 ]; do printf '%s(%d) ' "$1" $#; shift; done; echo
set -- 1 2 3; while (( $# )); do echo -n "$1"; shift; done; echo
#### heredoc edge cases
cat <<EOF
  leading spaces kept
	tab kept
$(echo "cmd sub")
\$escaped \\backslash \`tick\`
"quotes" 'kept'
EOF
cat <<EOF | wc -l
a

c
EOF
cat <<'END'
no $expansion `here` \n
END
#### heredoc with variables containing special chars
v='a$b`c\d"e'
cat <<EOF
[$v]
EOF
#### multiple heredocs and redirects
cat <<A <<B
ignored
A
used
B
cat > out.txt <<EOF
to file
EOF
cat out.txt
#### pipeline with functions and loops
gen() { for i in 3 1 2; do echo $i; done; }
gen | sort | while read -r n; do echo "n=$n"; done | tail -1
gen | { sum=0; while read -r n; do sum=$((sum+n)); done; echo $sum; }
#### stdin inheritance in loops
printf 'a\nb\nc\n' > in.txt
while read -r l; do
  echo "line $l"
  cat > /dev/null
done < in.txt
while read -r l; do echo "line $l"; cat /dev/null; done < in.txt
#### read from fd while running commands
exec 3< in.txt
while read -r l <&3; do echo "got $l"; echo "$l" | tr a-z A-Z; done
exec 3<&-
#### command substitution strips only trailing newlines
v=$(printf '\n\nmid\n\n\n'); echo "[$v]" | od -c | head -2 | tr -s ' '
v=$(printf 'a\n\nb'); echo "${#v}"
#### exit status propagation
f() { return $1; }
f 0 && echo zero
f 1 || echo one
f 255; echo $?
f 256; echo $?
(exit 3) || echo "sub $?"
! (exit 3); echo $?
true; false; true; echo $?
#### dollar-question in various spots
false; x=$?; echo $x
false; echo "$?" "$?"
true; if [ $? -eq 0 ]; then echo ok; fi
false || { echo "st in group: $?"; }
f() { false; return $?; }; f; echo $?
#### colon in parameter and ternary-like idioms
unset v; : "${v:=default}"; echo $v
x=5; y=$([ $x -gt 3 ] && echo big || echo small); echo $y
[ -n "$x" ] && z=set || z=unset; echo $z
#### test with tricky strings
x="-f"; [ "$x" = "-f" ] && echo dash-f
x="("; [ "$x" = "(" ] && echo paren
x="!"; [ "$x" ] && echo bang
x=""; [ -z "$x" -a -z "$x" ] && echo both-empty
[ "a" = "a" -a "b" = "b" ] && echo and
[ "=" = "=" ] && echo eq-eq
#### string comparison operators
[[ a < b && b > a ]] && echo lex
[[ "abc" == "abc" ]] && echo same
[[ abc != ABC ]] && echo case-sens
[ "a" \< "b" ] && echo test-lt
[[ -z $unset && -n "x" ]] && echo zn
[[ $unset == "" ]] && echo unset-empty
#### pattern matching variety
for s in abc a.c a/c 'a c' ABC abc123; do
  case $s in
    a?c) echo "$s:q";;
    *[0-9]) echo "$s:digit";;
    [A-Z]*) echo "$s:upper";;
    *) echo "$s:other";;
  esac
done
[[ file.tar.gz == *.tar.* ]] && echo multi-star
[[ abc == [a-c][a-c][a-c] ]] && echo classes
[[ a-b == a[-]b ]] && echo dash-class
[[ "]" == []] ]] && echo rbracket
#### parameter expansion on special values
set -- "one two" three
echo "${1% *}" "${1#* }" "${2^^}" "${#1}" "${@: -1}" "${*:1:1}"
echo "${@:2}" "${@:1:1}"
x=/a/b/; echo "${x%/}" "${x%%/}" "${x#/}"
p="a.b.c.d"; echo "${p%.*.*}" "${p#*.*.}"
#### replace special characters
s='a/b\c$d*e'
echo "${s//\//-}" "${s//\\/-}" "${s//\$/-}" "${s//\*/-}"
t="hello"; echo "${t/l/L}" "${t//l/L}" "${t/#h/H}" "${t/%o/O}" "${t/x/y}" "${t//?/.}"
u="a b c"; echo "${u// /}" "${u// /__}"
#### length and substring with multibyte
m="日本語abc"
echo ${#m} "${m:0:2}" "${m:3}" "${m: -3}" "${m//本/X}" "${m%abc}" "${m#日}"
#### export and subprocess env details
export E1="with space"
$PY -c 'import os; print(repr(os.environ["E1"]), "E3" in os.environ)'
E3=x
$PY -c 'import os; print("E3" in os.environ)'
export E3
$PY -c 'import os; print(os.environ["E3"])'
unset E1; $PY -c 'import os; print("E1" in os.environ)'
#### argument passing to external preserves bytes
$PY -c 'import sys; print(sys.argv[1:])' '' 'a b' "tab	x" 'q"uote' "s'q" 'star*' '$dollar' 'back\slash' '日本語'
#### eval with quotes and variables
a='x y'; eval "b=\"\$a\""; echo "[$b]"
cmd="echo 'single quoted' \"double \$a\""; eval "$cmd"
eval 'echo "$a"' '|' tr a-z A-Z
n=3; eval "v$n=dyn"; echo $v3
#### trap with functions and signals list
cleanup() { echo "cleanup called"; }
trap cleanup EXIT
trap 'echo int' INT
trap -p | sort | sed 's/SIG//'
trap - INT
( trap 'echo sub trap' EXIT )
echo before-exit
#### exit trap sees status and can change it
trap 'st=$?; echo "saw $st"; exit 9' EXIT
(exit 4)
exit 4
#### set -e in complex script
set -e
f() { echo "f start"; false || true; echo "f end"; }
f
x=$(echo "sub ok"; true)
[ -n "$x" ]
for i in 1 2; do [ $i -eq 1 ] && continue; echo "i=$i"; done
case x in y) false;; esac
if ! false; then echo neg; fi
{ true && true; }
echo "reached end"
#### pipefail with early exit consumers
set -o pipefail
seq 1 1000 | head -1; echo "st=$?"
printf 'a\nb\n' | grep -q a; echo "st=$?"
#### unusual but valid syntax
if true;then echo no-space;fi
for i in 1;do echo $i;done
{ echo brace;}
(echo paren)
[ 1 = 1 ]&&echo and
false||echo or
echo a;echo b
x=1;y=2;echo $x$y
case a in a)echo c;;esac
f(){ echo fn;};f
while false;do :;done;echo w
#### comments in odd places
echo a # trailing
# full line
echo "not # a comment" 'nor # this' not\#this a#b
if true; then # comment after then
  echo in-if
fi # comment after fi
for i in 1 2 # comment in for
do echo $i; done
case x in # comment
  x) echo cx ;; # after
esac
#### long pipelines and many args
seq 1 500 | sed 's/$/x/' | grep -c x
echo $(seq 1 300) | wc -w
printf '%s\n' $(seq 1 100) | sort -n | tail -1
set -- $(seq 1 200); echo $# ${200} ${100}
#### deep nesting of substitutions
echo $(echo $(echo $(echo $(echo $(echo deep)))))
x=$(( $(( $(( 1 + 2 )) * 3 )) + $(echo 4) )); echo $x
echo "${x:-${y:-${z:-fallback}}}" "${nope:-${y:-${z:-fallback}}}"
#### variable names edge
_a=1; a_1=2; A=3; a1b2=4
echo $_a $a_1 $A $a1b2 ${_a}x "$a_1"x
#### assignment with command and special chars
url='http://host:8080/path?q=1&r=2#frag'
echo "$url" | cut -d/ -f3
host=${url#*//}; host=${host%%/*}; port=${host##*:}; echo "${host%:*} $port"
kv='key=value=with=equals'; echo "${kv%%=*}" "${kv#*=}"
#### printf corner cases
printf '%s|%s|\n' a
printf '%d|%d\n' 5
printf '%5s|%-5s|%05d|%+d|% d\n' ab cd 42 7 7
printf '%.0f %.1f %5.1f\n' 2.5 2.25 3.14159
printf '%s\n' "multi
line"
printf '%%|%c|%5c|\n' xyz q
printf 'tab\there\\n literal\n'
printf '%b' 'a\nb\n'
printf '%03d:%02d\n' 7 5 12 30
printf '%s %s\n' "$(printf '%q' 'a b')" "$(printf '%q' '')"
printf '%x %o %X %#x %#o\n' 255 8 255 255 8
printf '%10.3f|\n%-10.3f|\n' 3.14159 3.14159
printf "%s\n" -n -e --
#### echo corner cases
echo -n; echo
echo -e 'a\x41\101A'
echo -e '\ttab\\n'
echo '-n' "-e"
echo - -- -x
echo -ne '\n'
echo -en 'x\n'
echo -nn; echo
echo -n -e 'q\n'
#### read corner cases
read -r a b c <<< "1 2"; echo "[$a][$b][$c]"
read -r a b <<< "1 2 3 4"; echo "[$a][$b]"
read -r a <<< "  spaced  "; echo "[$a]"
IFS=, read -r a b c <<< "x,,z"; echo "[$a][$b][$c]"
IFS=, read -r a b <<< "x,y,"; echo "[$a][$b]"
IFS=, read -r a b <<< "x,y,,"; echo "[$a][$b]"
IFS=: read -r a b <<< ":lead"; echo "[$a][$b]"
read -r a <<< ""; echo "[$a] st=$?"
echo -n "no newline" | { read -r a; echo "[$a] st=$?"; }
#### while read with IFS and -r preserving
printf 'a\\b  c\n  d\te  \n' > r.txt
while IFS= read -r line; do printf '[%s]\n' "$line"; done < r.txt
while read -r line; do printf '[%s]\n' "$line"; done < r.txt
while read line; do printf '[%s]\n' "$line"; done < r.txt
#### sort numeric and mixed
printf '10\n2\n-1\n0.5\nabc\n\n' | sort -n
printf '2 b\n10 a\n2 a\n' | sort -k1,1n -k2,2
printf 'b,2\na,10\nc,1\n' | sort -t, -k2 -n
printf 'x\nX\ny\nY\n' | sort -u
printf '3\n1\n2\n' | sort -c 2>/dev/null; echo "st=$?"
printf '1\n2\n3\n' | sort -c; echo "st=$?"
#### sed more complex scripts
printf 'a=1\nb=2\n# c=3\n' | sed -n '/^#/!s/\([a-z]*\)=\(.*\)/\2:\1/p'
echo "one two three" | sed 's/\(one\) \(two\)/\2 \1/;s/three/3/'
printf 'x\ny\nz\n' | sed -n '2{p;q}'
printf 'a\nb\nc\nd\n' | sed '1d;$d'
printf 'a\nb\nc\n' | sed '/b/,$d'
echo "aXbXc" | sed 's/X/\n/g' | wc -l
echo "hello" | sed 's/./\U&/' 
echo "hello world" | sed -E 's/\b(.)/\u\1/g'
printf 'l1\nl2\nl3\n' | sed '2s/^/# /'
echo "a,b;c" | sed 's/[,;]/ /g'
echo "x" | sed -e 'a\' -e 'appended'
printf 'k v\n' | sed 's/\(.*\) \(.*\)/"\1": "\2"/'
#### grep more options
printf 'foo\nbar\nfoobar\n' > g.txt
grep -c '' g.txt
grep -vc foo g.txt
grep -n 'o\{2\}' g.txt
grep -E 'foo|bar' g.txt | wc -l
grep -E '^(foo)?bar$' g.txt
grep -o 'o*' g.txt
grep -iw FOO g.txt
grep -e foo -e bar -c g.txt
grep -F -x foo g.txt
echo 'a.b' | grep -F '.'
echo 'a*b' | grep 'a\*b'
echo 'ab' | grep -E 'a.?b'
echo '[x]' | grep -F '[x]'
echo 'tab	sep' | grep -c '	'
#### cut and tr combos
echo "a:b:c" | cut -d: -f1,3 | tr : -
echo "  many   spaces  " | tr -s ' ' | cut -d' ' -f2-3
echo "abcdef" | cut -c2-4,6
echo "ABC" | tr 'A-Z' 'a-z' | tr -d 'b'
echo "a1b2c3" | tr -cd '0-9'; echo
echo "hello" | tr 'el' 'ip'
printf 'a\tb\n' | tr '\t' ','
#### wc and counting idioms
printf 'a b\nc\n' | wc -lwc | tr -s ' ' | sed 's/^ //'
count=$(printf 'x\ny\nz\n' | wc -l); echo $((count + 0))
[ "$(printf '' | wc -l)" -eq 0 ] && echo zero-lines
n=$(ls | wc -l); echo $((n))
#### find and loops with spaces safe
mkdir -p 'd 1/sub'; touch 'd 1/f a' 'd 1/sub/f b'
find 'd 1' -type f | sort | while IFS= read -r f; do echo "<$f>"; done
find 'd 1' -type f -exec basename {} \; | sort
find 'd 1' -name 'f *' | wc -l
#### background jobs ordering with wait
{ sleep 0.2; echo second; } &
echo first
wait
echo third
#### subshell variable and cd isolation in pipelines
x=1
echo | x=2
echo "x=$x"
echo data | { read v; x=$v; echo "in: $x"; }
echo "out: $x"
mkdir sub; ( cd sub; touch inside ); ls sub; [ ! -e inside ] && echo "cwd isolated"
#### exec with redirection persists
exec > redirected.txt
echo "to file"
exec >&2
cat redirected.txt >&2 2>/dev/null
wc -l < redirected.txt >&2 2>/dev/null
echo done >&2 2>/dev/null
#### exported empty variable [posix]
export EMPTYV=
$PY -c 'import os; print(repr(os.environ.get("EMPTYV")))'
#### wait -n returns first finished job
( sleep 0.3; exit 7 ) &
( exit 3 ) &
wait -n; echo "first=$?"
wait; echo all
#### nameref and function export are refused loudly
f() { local -n ref=$1; ref=changed; }
v=orig; f v 2>/dev/null; echo "st=$? v=$v" | sed 's/st=[1-9][0-9]*/st=nonzero/;s/v=.*/v=?/'
#### nullglob does not eat the test bracket or unterminated brackets
shopt -s nullglob
x=5
[ "$x" -gt 0 ] && echo "bracket command survives nullglob"
if [ -n "$x" ]; then echo ok; fi
echo [ a [b c] d[
echo *.none "|" [zzz] "|" x[
files=(*.none); echo "${#files[@]}"
shopt -u nullglob
echo [ [abc [zzz]
touch a b
echo [ab] [a-b] [!a]
