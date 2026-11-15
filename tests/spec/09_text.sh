#### cat
printf 'a\nb\n' > f1; printf 'c\n' > f2
cat f1 f2
cat -n f1
cat < f1
cat f1 - f2 < f2
cat nonexistent 2>/dev/null; echo "st=$?"
#### head and tail
seq 1 20 > n.txt
head -3 n.txt
head -n 2 n.txt
tail -2 n.txt
tail -n +19 n.txt
head -n -18 n.txt
head -c 5 n.txt; echo
seq 1 5 | tail -n 1
seq 1 5 | head -1
#### wc
printf 'one two\nthree\n' > w.txt
wc -l w.txt
wc -w < w.txt
wc -c < w.txt
wc w.txt
wc -l w.txt w.txt
printf 'no newline' | wc -l
echo "a b c" | wc -w
#### sort basic
printf 'banana\napple\ncherry\napple\n' > s.txt
sort s.txt
sort -r s.txt
sort -u s.txt
printf '10\n9\n100\n1\n' | sort
printf '10\n9\n100\n1\n' | sort -n
printf '10\n9\n100\n1\n' | sort -rn
#### sort keys
printf 'b 2 x\na 10 y\nc 1 z\na 3 w\n' > k.txt
sort -k2 k.txt
sort -k2n k.txt
sort -k1,1 -k2,2n k.txt
sort -k1,1r -k2n k.txt
sort -t: -k2 <<< $'x:b\ny:a'
printf 'a,3\nb,1\nc,2\n' | sort -t, -k2,2n
#### sort case and stability
printf 'b\nA\na\nB\n' | sort
printf 'b\nA\na\nB\n' | sort -f
printf '1 b\n1 a\n0 c\n' | sort -s -k1,1n
#### uniq
printf 'a\na\nb\na\nc\nc\n' > u.txt
uniq u.txt
uniq -c u.txt
uniq -d u.txt
uniq -u u.txt
sort u.txt | uniq -c | sort -rn | head -1
#### cut
printf 'a:b:c\nd:e:f\nnodelim\n' > c.txt
cut -d: -f2 c.txt
cut -d: -f1,3 c.txt
cut -d: -f2- c.txt
cut -d: -s -f1 c.txt
echo "hello world" | cut -c1-5
echo "hello world" | cut -c7-
printf 'a\tb\tc\n' | cut -f2
#### tr
echo hello | tr a-z A-Z
echo hello | tr -d l
echo "a  b   c" | tr -s ' '
echo "hello123" | tr -d '[:digit:]'
echo "hello" | tr '[:lower:]' '[:upper:]'
echo "a-b_c" | tr '_-' '  '
echo "abc" | tr -c 'a\n' 'x'
printf 'a\r\nb\r\n' | tr -d '\r'
echo "path/to/file" | tr '/' '\n'
#### grep basic
printf 'apple\nbanana\ncherry\nApple pie\n' > g.txt
grep apple g.txt
grep -i apple g.txt
grep -v an g.txt
grep -c a g.txt
grep -n rr g.txt
grep '^b' g.txt
grep 'y$' g.txt
grep -q cherry g.txt && echo found
grep -q missing g.txt || echo "not found"
grep missing g.txt; echo "st=$?"
#### grep regex flavors
printf 'ab\naab\nabb\nabc123\na+b\n' > r.txt
grep 'a*b' r.txt | wc -l
grep -E 'a+b' r.txt
grep 'a\+b' r.txt
grep -E '^(ab|abc)[0-9]*$' r.txt
grep -F 'a+b' r.txt
grep -E '[0-9]{3}' r.txt
grep '[[:digit:]]' r.txt
grep -w ab r.txt
grep -x ab r.txt
grep -o '[0-9]\+' r.txt
#### grep multiple files and options
printf 'x\ny\n' > a.txt; printf 'y\nz\n' > b.txt
grep y a.txt b.txt
grep -l y a.txt b.txt
grep -L x a.txt b.txt
grep -h y a.txt b.txt
grep -c y a.txt b.txt
grep -e x -e z a.txt b.txt
grep -H x a.txt
#### grep context
seq 1 10 > c.txt
grep -A1 5 c.txt
grep -B1 5 c.txt
grep -C1 -n 5 c.txt
grep -m2 1 c.txt
#### grep recursive
mkdir -p d/e; echo needle > d/e/f.txt; echo hay > d/g.txt
grep -r needle d
grep -rl needle d
grep -rc needle d | sort
#### grep in pipeline and stdin
echo "one two" | grep -o two
printf 'a\nb\n' | grep -n b
grep -c '' /dev/null
#### sed substitute
echo "hello world" | sed 's/world/there/'
echo "aaa" | sed 's/a/b/'
echo "aaa" | sed 's/a/b/g'
echo "aaa" | sed 's/a/b/2'
echo "path/to" | sed 's/\//-/g'
echo "path/to" | sed 's|/|-|g'
echo "Hello" | sed 's/hello/x/i'
echo "abc" | sed 's/b/[&]/'
echo "john smith" | sed 's/\(.*\) \(.*\)/\2, \1/'
echo "john smith" | sed -E 's/(.*) (.*)/\2, \1/'
#### sed addresses
seq 1 6 > n.txt
sed -n '2p' n.txt
sed -n '2,4p' n.txt
sed -n '$p' n.txt
sed '2d' n.txt | tr '\n' ' '; echo
sed '2,$d' n.txt
sed -n '/3/,/5/p' n.txt | tr '\n' ' '; echo
sed -n '/2/!p' n.txt | tr '\n' ' '; echo
sed -n '1~2p' n.txt | tr '\n' ' '; echo
sed '3q' n.txt | tr '\n' ' '; echo
sed -n '2,+1p' n.txt | tr '\n' ' '; echo
#### sed commands
printf 'a\nb\nc\n' > t.txt
sed 'a\after' t.txt | tr '\n' ' '; echo
sed '2i\before' t.txt | tr '\n' ' '; echo
sed '2c\changed' t.txt | tr '\n' ' '; echo
sed 'y/abc/xyz/' t.txt | tr '\n' ' '; echo
sed -n '$=' t.txt
sed -e 's/a/1/' -e 's/b/2/' t.txt | tr '\n' ' '; echo
sed 's/a/1/;s/c/3/' t.txt | tr '\n' ' '; echo
sed '/b/{s/b/B/;p}' t.txt | tr '\n' ' '; echo
sed 'N;s/\n/+/' t.txt
sed '$!N;s/\n/ /' t.txt
#### sed hold space and reverse
printf '1\n2\n3\n' | sed -n '1!G;h;$p'
printf 'a\nb\n' | sed 'G'
printf 'k1\nv1\nk2\nv2\n' | sed 'N;s/\n/=/'
#### sed in place
printf 'foo\nbar\n' > ip.txt
sed -i 's/foo/baz/' ip.txt; cat ip.txt
sed -i.bak 's/bar/qux/' ip.txt; cat ip.txt ip.txt.bak
#### sed special chars
echo 'a.b*c' | sed 's/\./X/'
echo 'a.b*c' | sed 's/\*/Y/'
echo 'a b' | sed 's/ /\n/'
echo 'tab	here' | sed 's/\t/ /'
echo 'x' | sed 's/x/a\/b/'
echo 'end' | sed 's/$/!/'
echo 'start' | sed 's/^/> /'
echo 'abc' | sed 's/[ac]//g'
echo "UPPER lower" | sed 's/[A-Z]*/(&)/'
#### sed delete patterns
printf 'keep\n# comment\n\nkeep2\n' | sed '/^#/d;/^$/d'
printf '  trim  \n' | sed 's/^[ \t]*//;s/[ \t]*$//' | sed 's/$/|/'
#### rev tac nl paste
echo abc | rev
printf '1\n2\n3\n' | tac
printf 'a\nb\n' | nl
printf 'a\nb\nc\n' | paste -sd,
printf '1\n2\n' > p1; printf 'x\ny\n' > p2; paste p1 p2
paste -d: p1 p2
#### seq
seq 3
seq 2 4
seq 1 2 7
seq 5 -2 1
seq -s, 1 4
seq -w 8 10
seq 0.5 0.5 2
#### tee and pipes combined
printf 'b\na\n' | tee raw.txt | sort > sorted.txt
cat raw.txt sorted.txt
#### text pipeline word frequency
printf 'the quick brown fox\nthe lazy dog\nthe end\n' | tr ' ' '\n' | sort | uniq -c | sort -k1,1nr -k2 | head -3
#### csv processing
cat > data.csv <<EOF
id,name,amount
1,alice,100
2,bob,250
3,carol,75
EOF
tail -n +2 data.csv | cut -d, -f3 | paste -sd+ 
total=0; while IFS=, read -r id name amt; do [ "$id" = id ] && continue; total=$((total+amt)); done < data.csv; echo $total
tail -n +2 data.csv | sort -t, -k3,3nr | head -1 | cut -d, -f2
grep -c , data.csv
sed -n '2,$p' data.csv | while IFS=, read -r _ n a; do printf '%-6s %5d\n' "$n" "$a"; done
#### multibyte text
echo "日本語テキスト" | wc -m
echo "日本語" | rev
printf 'いろは\nあいう\n' | sort
echo "東京都" | sed 's/都/府/'
echo "カタカナ" | grep -c カ
echo "日本語abc" | tr a-c A-C
x="こんにちは"; echo ${#x} ${x:1:2}
#### base64 and checksums
printf 'hello' | base64
printf 'aGVsbG8=' | base64 -d; echo
printf 'hello' | md5sum
printf 'hello' | sha256sum
printf 'hello\n' > h.txt; md5sum h.txt; sha1sum h.txt
md5sum h.txt > sums; md5sum -c sums
#### diff and cmp
printf 'a\nb\nc\n' > d1; printf 'a\nx\nc\n' > d2
diff d1 d2; echo "st=$?"
diff d1 d1; echo "st=$?"
diff -q d1 d2; echo "st=$?"
cmp -s d1 d2; echo "st=$?"
cmp -s d1 d1; echo "st=$?"
printf 'a\nb\n' > d3; printf 'a\nb\nc\nd\n' > d4
diff d3 d4
diff d4 d3
#### expr
expr 1 + 2
expr 10 / 3
expr 5 \* 4
expr 7 % 3
expr length hello
expr substr hello 2 3
expr index hello l
expr hello : 'hel'
expr hello : 'h\(.*\)o'
expr 3 \> 2
expr 0; echo "st=$?"
expr a = b; echo "st=$?"
#### crlf handling with tr and sed
printf 'a\r\nb\r\n' > crlf.txt
tr -d '\r' < crlf.txt | od -c | head -1 | tr -s ' '
sed 's/\r$//' crlf.txt | od -An -tx1 | tr -d ' \n'; echo
od -c crlf.txt | tr -s ' '
#### iconv
printf 'テスト' | iconv -f UTF-8 -t SJIS | od -An -tx1 | tr -d ' \n'; echo
printf '\x83\x65\x83\x58\x83\x67' | iconv -f SJIS -t UTF-8; echo
