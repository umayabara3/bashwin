#### echo plain
echo hello world
echo   spaced    out
echo
#### echo options
echo -n no-newline; echo
echo -e 'a\tb\nc'
echo -E 'a\tb'
echo -ne 'x\ny\n'
echo -e 'stop\chere'; echo
echo -- -n
#### single and double quotes
x=world
echo 'single $x'
echo "double $x"
echo "nested 'single' in double"
echo 'nested "double" in single'
echo "escaped \"quote\" and \$dollar and \\ backslash"
echo a\ b\ \ c
#### ansi-c quoting
echo $'tab\there'
echo $'line1\nline2'
echo $'quote\'s'
echo $'\x41\x42\101'
#### adjacent quoting
a=1
echo "$a"'$a'"${a}"x$a
echo ""
echo "" "" | wc -c
#### variables basic
x=1; y=two
echo $x $y "$x$y" ${x}${y}
z=
echo "[$z]" "[${z}]"
unset x
echo "[$x]"
#### assignment forms
a=b=c
echo $a
p=/usr; q=$p/bin
echo $q
s="a  b   c"
echo $s
echo "$s"
t=$s
echo "$t"
#### command substitution
echo "$(echo inner)"
echo `echo backtick`
x=$(echo a; echo b)
echo "$x"
echo "nested: $(echo "$(echo deep)")"
echo "trailing newlines stripped: [$(printf 'x\n\n\n')]"
#### word splitting
x="a b  c"
for w in $x; do echo "<$w>"; done
for w in "$x"; do echo "<$w>"; done
set -- $x; echo $#
set -- "$x"; echo $#
#### IFS splitting
IFS=:
x="a:b::c"
for w in $x; do echo "<$w>"; done
IFS=,
set -- "a,b" c
echo "$*"
echo "$@"
unset IFS
y=" lead  trail "
set -- $y; echo $#
#### IFS mixed whitespace
IFS=' ,'
x='a, b ,c,,d'
for w in $x; do echo "<$w>"; done
#### empty expansion removal
e=
set -- $e; echo $#
set -- "$e"; echo $#
set -- $e x $e; echo $#
set -- ""$e; echo $#
#### positional params
set -- a b c d e f g h i j k
echo $1 $2 ${10} ${11} $#
echo "$*"
shift 2; echo $1 $#
shift; echo "$@"
#### special params
set -- x y
echo $# "$0" | sed 's/[^ ]*$/SCRIPT/'
true; echo $?
false; echo $?
echo ${#}
#### dollar-at vs dollar-star
set -- "a b" c
for x in "$@"; do echo "[$x]"; done
for x in "$*"; do echo "[$x]"; done
for x in $@; do echo "[$x]"; done
for x in $*; do echo "[$x]"; done
set --
for x in "$@"; do echo never; done
echo "count=$#"
#### dollar-at with prefix suffix
set -- 1 2 3
for x in "pre$@post"; do echo "[$x]"; done
#### brace expansion
echo {a,b,c}
echo x{1,2}y
echo {1..5} {5..1} {a..e}
echo {01..03} {1..10..3}
echo {a,b}{1,2}
echo pre{,mid}post
echo {a,b{c,d}}
echo {single} {} a{b
#### tilde expansion
HOME=/home/test
echo ~ ~/x "~" '~'
x=~/y; echo $x
echo a~b
#### comments and line continuation
echo one # comment
echo two \
  three
echo "four
five"
echo a#b
#### printf basics
printf '%s\n' hello
printf '%s %s\n' a b c d
printf '%d %i\n' 42 -7
printf '%5d|%-5d|%05d\n' 1 2 3
printf '%.2f %e\n' 3.14159 1000
printf '%x %X %o\n' 255 255 8
printf '%c%c\n' abc def
printf '%%\n'
printf 'no newline'; echo
#### printf strings
printf '[%10s][%-10s]\n' right left
printf '[%.3s]\n' truncated
printf '%s\n'
printf '%b\n' 'a\tb'
printf '%q\n' 'a b' "it's" plain
printf '\x41\101\n'
printf '%s\n' "a\nb"
#### printf -v
printf -v out '%03d-%s' 7 x
echo "$out"
#### printf reuse format
printf '%s=%s\n' a 1 b 2 c
printf '%d\n' 1 2 3
#### printf star width
printf '[%*d]\n' 5 42
printf '[%-*s]\n' 6 ab
#### exit status of last command
(exit 3); echo $?
( exit 258 ); echo $?
bash_missing_cmd_xyz 2>/dev/null; echo $?
#### semicolons and newlines
echo a; echo b
echo c;
{ echo d; echo e; }
#### long string
x=$(printf 'ab%.0s' 1 2 3 4 5 6 7 8 9 10)
echo ${#x} $x
