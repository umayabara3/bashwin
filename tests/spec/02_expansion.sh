#### default values
unset u; e=
echo "${u-def}" "${u:-def}" "${e-def}" "${e:-def}"
s=set
echo "${s-def}" "${s:-def}"
#### assign default
unset u
echo "${u:=assigned}" "$u"
e=
echo "${e=nochange}[$e]" "${e:=changed}[$e]"
#### alternate value
unset u; e=; s=v
echo "[${u+alt}]" "[${u:+alt}]" "[${e+alt}]" "[${e:+alt}]" "[${s+alt}]" "[${s:+alt}]"
#### error if unset
unset u
( echo "${u:?custom message}" ) 2>/dev/null
echo "status=$?"
( echo "${u?}" ) 2>/dev/null
echo "status=$?"
echo after
#### length
x=hello; e=
echo ${#x} ${#e}
set -- a b c
echo ${#@} ${#*} ${#1}
#### prefix removal
p=/usr/local/bin/tool.tar.gz
echo "${p#*/}" "${p##*/}"
echo "${p#/usr}" "${p#nomatch}"
echo "${p##*.}" "${p#*.}"
#### suffix removal
p=/usr/local/bin/tool.tar.gz
echo "${p%/*}" "${p%%/*}|"
echo "${p%.*}" "${p%%.*}"
echo "${p%gz}" "${p%nomatch}"
#### pattern removal with classes
x=abc123def
echo "${x#[a-z]*[0-9]}" "${x##[a-z]*[0-9]}" "${x%%[0-9]*}" "${x%[!0-9]*}"
#### replace
x="hello world hello"
echo "${x/hello/bye}" "${x//hello/bye}"
echo "${x/#hello/START}" "${x/%hello/END}"
echo "${x/o/}" "${x//o/}"
echo "${x// /_}"
echo "${x//[aeiou]/*}"
#### replace with slash and vars
p=a/b/c; from=/; to=-
echo "${p//\//:}" "${p//$from/$to}"
#### substring
x=0123456789
echo "${x:2}" "${x:2:3}" "${x: -3}" "${x: -3:2}" "${x:0:1}" "${x:8:10}"
echo "${x:2:-2}"
n=4; echo "${x:n}" "${x:n+1:2}"
#### case modification
x="hello World"
echo "${x^}" "${x^^}" "${x,}" "${x,,}"
#### indirect expansion
name=target; target=value
echo "${!name}"
set -- a b c; i=2
echo "${!i}"
#### nested expansion
unset a; b=inner
echo "${a:-${b}}" "${a:-$b-x}" "${a:-"quoted $b"}"
#### expansion in default is lazy
unset a
x=${a:-$(echo computed)}
echo $x
#### quoted vs unquoted default
unset u
set -- ${u:-a b c}; echo $#
set -- "${u:-a b c}"; echo $#
#### arithmetic expansion
echo $((1+2)) $(( 3 * 4 )) $((10/3)) $((10%3)) $((2**8))
x=5; echo $((x+1)) $(($x+1)) $((x++)) $x $((++x)) $x
echo $(( (1+2)*3 )) $((1<2)) $((1>2)) $((5&3)) $((5|3)) $((5^3)) $((~5)) $((1<<4))
echo $((x>3 ? 10 : 20)) $((0x10)) $((010)) $((2#101))
#### arithmetic negative and precedence
echo $((-7/2)) $((-7%2)) $((7/-2)) $((2+3*4)) $((2*3+4)) $(( -2 ** 2 ))
echo $(( 1 || 0 )) $(( 1 && 0 )) $(( !5 )) $(( !0 ))
#### arithmetic assignment ops
x=10
echo $((x+=5)) $((x-=3)) $((x*=2)) $((x/=4)) $((x%=4)) $x
y=1; echo $((y<<=3)) $((y|=1)) $((y&=5))
#### arithmetic with unset and strings
unset z
echo $((z)) $((z+1))
v=w; w=7
echo $((v))
#### arithmetic comma
echo $((a=1, b=2, a+b))
#### glob basics
touch a.txt b.txt c.log .hidden
echo *.txt
echo *
echo .h*
echo ?.txt
echo [ab].txt [!a].txt
echo *.nomatch
echo "*.txt" '*.txt' \*.txt
#### glob in subdirs
mkdir -p d1/sub d2
touch d1/x.c d1/sub/y.c d2/z.c
echo */*.c
echo d1/*/
echo d?/*.c
echo */
#### glob from variable
touch f1 f2
p='f*'
echo $p
echo "$p"
#### glob sorted [posix]
touch b a C B 1 _x
echo *
#### no glob after set -f
touch g1 g2
set -f
echo g*
set +f
echo g*
#### nullglob
shopt -s nullglob
for f in *.zzz; do echo never; done
echo "done"
shopt -u nullglob
echo *.zzz
#### quote removal in patterns
x='a*b'
case 'a*b' in "$x") echo quoted-match;; esac
case 'aXXb' in "$x") echo wrong;; *) echo no-match;; esac
case 'aXXb' in $x) echo unquoted-match;; esac
#### param in double quotes preserves spaces
x='a   b'
y="$x"
echo "$y" | tr ' ' '_'
#### dollar edge cases
echo $ "$" a$ '$x' "\$x"
echo "$(echo '$literal')"
#### at-ops
x="a b"
echo "${x@Q}" "${x@U}"
#### prefix names
abc1=1; abc2=2
echo "${!abc@}"
#### empty default inside double quotes is one empty field
unset u
set -- "${u:-}"; echo $#
set -- "${u-}"; echo $#
set -- ${u:-}; echo $#
s=v
set -- "${s:+}"; echo $#
[ -n "${u:-}" ] && echo wrong || echo empty-ok
declare -A m
[ -n "${m[k]:-}" ] && echo wrong || echo empty-ok2
