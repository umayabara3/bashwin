#### shopt variants
touch Abc abd .dot
shopt -s nocaseglob; echo a*; shopt -u nocaseglob; echo a*
shopt -s dotglob; echo *; shopt -u dotglob; echo *
shopt -s nullglob; echo none*; shopt -u nullglob
shopt -q nullglob; echo "st=$?"
#### set -a allexport and set -C
set -a
AUTO=exported
set +a
NOTAUTO=x
$PY -c 'import os; print(os.environ.get("AUTO"), os.environ.get("NOTAUTO"))'
#### inherit_errexit
set -e
x=$(false; echo continued); echo "[$x]"
shopt -s inherit_errexit
y=$(false; echo continued) || echo "sub failed [$y]"
#### declare -g and -p inside function
f() { declare -g G=global; declare L=local; local -i n=3; n+=4; echo "$n"; }
f; echo "$G [${L:-unset}]"
declare -p G
#### case conversion operators
x="hello World"; echo "${x@U}" "${x@L}" "${x@u}"
#### diff options
printf 'a\nb\nc\nd\ne\nf\ng\nh\n' > d1; printf 'a\nb\nX\nd\ne\nf\ng\nh\n' > d2
diff -U1 d1 d2 | tail -n +3
diff -s d1 d1
printf 'Hello World\n' > c1; printf 'hello   world\n' > c2
diff -i -b c1 c2; echo "st=$?"
diff -w c1 c2 > /dev/null; echo "st=$?"
diff -u d1 d2 | grep -c '^[-+][^-+]'
#### cp and mv options
echo new > src; echo old > dst
cp -n src dst; cat dst
cp -u src dst 2>/dev/null; cat dst
mkdir td; cp -t td src dst; ls td
echo a > m1; echo b > m2; mv -n m1 m2; cat m2; ls m1
cp -T src plain_copy; cat plain_copy
cp -v src v_copy
mv -v v_copy v_moved
#### rm and mkdir verbose
mkdir -v vd
touch vf; rm -v vf
rmdir vd; mkdir -p a/b/c; rmdir -p a/b/c; ls -d a 2>/dev/null; echo "st=$?"
#### find more predicates
mkdir -p f/sub; touch f/a.txt f/b.TXT f/sub/c.txt; printf 'xx' > f/two
find f -regex '.*/[ab]\.txt' | sort
find f -iname '*.txt' | sort
find f -name '*.txt' -print0 | tr '\0' '\n' | sort
find f -depth -name sub
find f -type f -size -1c | sort
find f -type f -size +1c
find f -type f -readable | wc -l
find f -type f \( -name 'a*' -o -name 'two' \) | sort
find f -maxdepth 1 -type f ! -name '*.txt' ! -name '*.TXT'
find f -mmin -5 -type f | wc -l
find f -mtime +1 | wc -l
find f/sub f/two -type f | sort
#### xargs more options
printf 'a,b,c' | xargs -d, -n1 echo
printf 'l1 x\nl2 y\n' | xargs -L1 echo line:
printf 'p q\n' | xargs -t echo 2>&1
printf '1\n2\n3\n' | xargs -n2 sh -c 'echo "$#"' sh
#### nl seq paste od variants
printf 'a\n\nb\n' | nl -ba
printf 'a\nb\n' | nl -w2 -s': ' -v10
seq -f '%03g' 1 3
seq -s' ' 3 -1 1
printf '1\n2\n3\n4\n' | paste -d' ' - -
printf 'AB' | od -An -tx1
printf 'AB\n' | od -b
printf 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' | od -Ad -c -N 20
printf 'abcd' | od -x
#### date more options
date -u -d @1700000000 -R
date -u -d @1700000000 -I
date -u -d @1700000000 -Iseconds
touch -d '2026-03-04 05:06:07' stamp; date -u -r stamp '+%F %T'
touch -t 202601020304 stamp2; date -r stamp2 +%Y%m%d%H%M
touch -r stamp stamp3; [ ! stamp3 -nt stamp ] && [ ! stamp -nt stamp3 ] && echo same-mtime
date -u -d '2026-11-15 tomorrow' +%F
date -u -d 'yesterday' +%F | grep -c '^20'
date -u -d '15 Nov 2026' +%F
date -u -d '2026-11-15 10:00 UTC +90 minutes' '+%H:%M'
date -u -d '2026-11-15 next month' +%F
date -u -d '2026-11-15 last year' +%F
date -u -d @1700000000 '+%-d %-m %_H %e|%k|%l|%C|%g|%G|%V|%U|%W|%h|%n%t|%%'
#### timeout and env options
timeout -s KILL 0.3 sleep 5; echo "st=$?"
timeout 5 true; echo "st=$?"
timeout 5 false; echo "st=$?"
env -i A=1 $PY -c 'import os; print(sorted(k for k in os.environ if k in ("A","HOME","PATH")))'
env X=1 Y=2 | grep -c '^[XY]='
#### grep remaining options
printf 'alpha\nbeta\ngamma\n' > g.txt; printf 'al\nga\n' > pats
grep -f pats g.txt
grep -P 'a(?=l)' g.txt
grep -s x /nonexistent/file; echo "st=$?"
grep -L beta g.txt pats
grep -c -i ALPHA g.txt
grep -h -n a g.txt pats | head -2
grep -ow 'beta' g.txt
grep -E -o '[a-z]+a$' g.txt | wc -l
grep -A1 -B1 beta g.txt
grep -x -F beta g.txt
#### wc uniq sort remaining
printf 'short\na much longer line\n' | wc -L
printf 'A\na\nB\n' | uniq -i
printf 'b\na\n' > s.txt; sort -o s.txt s.txt; cat s.txt
printf ' b\na\n  c\n' | sort -b
printf 'x 10\nx 9\ny 1\n' | sort -k1,1 -k2,2nr
printf 'a\tb\n' | cut -f1
printf '3\n1\n2\n' | sort -r | head -1
printf 'a:1\nb:2\n' | sort -t: -k2,2rn
#### sed remaining commands
printf 'a\nb\nc\nd\n' > s.txt
sed -n '2{n;p}' s.txt
sed '2r pats' s.txt | tr '\n' ' '; echo
sed -n 'l' <<< $'a\tb'
sed -n '/b/{=;p}' s.txt
sed '1!G;h;$!d' s.txt | tr '\n' ' '; echo
sed -n '$!{N;P;D}' s.txt | tr '\n' ' '; echo
sed 's/a/x/w wout.txt' s.txt > /dev/null; cat wout.txt
sed -e ':a' -e '$!{N;ba}' -e 's/\n/,/g' s.txt
sed '/b/,/c/{s/^/> /}' s.txt | tr '\n' ' '; echo
sed -s -n '$p' s.txt pats
sed 's/[aeiou]/\U&/g;s/^./\l&/' <<< "Banana"
sed -E 's/(b)(c)?/[\1\2]/' <<< "abd"
sed '2,3!d' s.txt | tr '\n' ' '; echo
sed '0~2d' s.txt | tr '\n' ' '; echo
sed -n '2,${p}' s.txt | wc -l
sed 'c\replaced' <<< "x"
sed '$a\tail line' s.txt | tail -1
sed '1i\head line' s.txt | head -1
#### touch stat du tar remaining
printf '12345' > sz.txt
stat -c '%s %F' sz.txt
stat -c '%n|%s' sz.txt
mkdir dd; printf '%2000s' x > dd/big
du -sb dd | cut -f1 | awk '{print ($1 >= 2000)}'
du -ab dd | wc -l
mkdir -p tt/in; echo hi > tt/in/f.txt
tar -cf t.tar -C tt in; tar -tf t.tar | sort
mkdir out && tar -xf t.tar -C out && cat out/in/f.txt
tar -xOf t.tar in/f.txt
tar -czf t.tgz -C tt in && tar -tzf t.tgz | wc -l
#### readlink realpath basename remaining
mkdir -p rp/x; touch rp/x/f
realpath -e rp/x/f | sed "s|$HOME||"
realpath -e rp/missing 2>/dev/null; echo "st=$?"
realpath -s rp/./x/../x/f | sed "s|$HOME||"
readlink -f rp/x/../x/f | sed "s|$HOME||"
basename -a a/b c/d
dirname a/b/c d
#### printf and echo remaining
printf '%5.1f|%-8.3s|%+.2e\n' 3.14159 abcdef 12345.678
printf '%o %X %#X %c\n' 64 255 255 A
printf '%s\n' 'a' 'b' | cat -n
printf '%b\n' 'x\ty\0101'
printf '%d\n' "'A" 0x1F 010
printf '[%6.2f] [%-6d] [%06.1f]\n' 2.5 7 2.5
printf '%s %s %s\n' a b c d e
echo -e 'a\\nb' 'c\0101'
#### read remaining options
printf 'abc\ndef\n' | { read -r -N 5 v; printf '[%s]\n' "$v"; }
printf 'k=v;rest' | { IFS='=' read -r -d ';' k v; echo "$k -> $v"; }
printf 'one\ntwo\n' | { read -r a; read -r b; read -r c; echo "$a $b [$c] st=$?"; }
exec 7<<< "from fd 7"; read -r -u 7 line; echo "$line"; exec 7<&-
printf 'a b c d\n' | { read -ra arr; echo "${#arr[@]} ${arr[-1]}"; }
#### arithmetic remaining
echo $(( 5 > 3 ? 1 : 0 )) $(( 0x10 | 0x01 )) $(( 7 & ~2 )) $(( 1 << 3 >> 1 )) $(( 5 ^ 1 ))
x=10; (( x %= 3, x <<= 2 )); echo $x
declare -i n; n=5*4; echo $n; n+=2; echo $n
let "a = 3" "b = a ** 2" "c = b % 4"; echo "$a $b $c"
echo $(( 64#10 )) $(( 8#17 )) $(( -3 ** 2 )) $(( (-3) ** 2 ))
i=5; echo $(( i-- - --i )) $i
#### sh and bash invoked from a script
cat > child.sh <<'XX'
echo "child: $0 $# [$1] X=${X:-unset} E=${E:-unset}"
exit 4
XX
X=notexported; export E=exported
bash child.sh "a b"; echo "st=$?"
sh ./child.sh; echo "st=$?"
sh -c 'echo "inline: $0 $1 $#"' name arg1 arg2
bash -c 'exit 9'; echo "st=$?"
bash -c 'echo $((1+2)); false; echo after-false'
bash -ec 'echo before; false; echo not-reached'; echo "st=$?"
bash -eu -o pipefail -c 'echo strict; false | true; echo never'; echo "st=$?"
echo 'echo "from stdin $1"' | bash -s -- param
echo 'echo piped script' | sh
bash -n child.sh; echo "syntax st=$?"
echo 'if true; then' > bad.sh; bash -n bad.sh 2>/dev/null; echo "syntax st=$?"
v=$(bash -c 'echo captured'); echo "[$v]"
bash -c 'cd /; echo changed' > /dev/null; [ "$PWD" = "$HOME" ] && echo "parent cwd intact"
