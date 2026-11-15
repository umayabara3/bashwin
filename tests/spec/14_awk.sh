#### awk print fields
printf 'a b c\nd e f\n' | awk '{print $1, $3}'
printf 'a b c\n' | awk '{print $NF, NF, $(NF-1)}'
printf 'x y\n' | awk '{print $2 $1}'
printf 'one\ntwo\n' | awk '{print NR": "$0}'
echo "a b c" | awk '{print}'
echo "a b c" | awk '{$2="X"; print}'
echo "a b c" | awk '{$5="E"; print; print NF}'
echo "  lead   trail  " | awk '{print $1 "|" $2 "|" NF}'
#### awk field separators
echo "a:b:c" | awk -F: '{print $2}'
echo "a,b,c" | awk -F, '{print $3, $1}'
echo "a,b,c" | awk 'BEGIN{FS=","} {print $2}'
printf 'a\tb c\td\n' | awk -F'\t' '{print $2}'
echo "a1b22c" | awk -F'[0-9]+' '{print $1 $2 $3}'
echo "a b c" | awk 'BEGIN{OFS="-"} {$1=$1; print}'
echo "a b c" | awk -v OFS=, '{print $1, $2}'
echo "a|b|c" | awk -F'|' '{print $2}'
echo "k=v" | awk -F= '{print $2 "=" $1}'
#### awk patterns
printf '1\n2\n3\n4\n5\n' > n.txt
awk '$1 > 3' n.txt
awk '$1 % 2 == 0 {print "even", $1}' n.txt
awk 'NR == 2' n.txt
awk 'NR >= 2 && NR <= 3' n.txt
awk '/3/' n.txt
awk '!/3/' n.txt | tr '\n' ' '; echo
awk '/2/,/4/' n.txt | tr '\n' ' '; echo
awk 'NR==1, NR==2 {print "r" $1}' n.txt
awk '$1 ~ /^[24]$/' n.txt
awk '$1 !~ /[135]/' n.txt
awk 'END {print NR}' n.txt
#### awk BEGIN END and aggregates
printf '10\n20\n30\n' | awk '{s += $1} END {print s, s/NR}'
printf '3\n1\n2\n' | awk 'NR==1 || $1 > max {max = $1} END {print max}'
printf 'a\nb\na\nc\na\n' | awk '{c[$1]++} END {for (k in c) print k, c[k]}' | sort
awk 'BEGIN {print "only begin"}'
printf 'x\n' | awk 'BEGIN {print "start"} {print "line", $0} END {print "end"}'
printf '5 apples\n3 pears\n' | awk '{total += $1; items = items $2 " "} END {print total, items}'
#### awk arithmetic and numbers
awk 'BEGIN {print 7/2, 7%3, 2^3, 2**4, -5+2, 1e3, 0.1+0.2}'
awk 'BEGIN {print int(7.9), int(-7.9), sqrt(16), 10 % 3}'
awk 'BEGIN {x = 5; x += 3; x *= 2; x -= 1; x /= 3; print x}'
awk 'BEGIN {i = 1; print i++, i, ++i, i--, i, --i}'
awk 'BEGIN {print 1 == 1.0, "a" < "b", 10 < 9, "10" < "9", 2 < 10}'
awk 'BEGIN {print 3 " " 4, 3 4, 1+2 "x"}'
awk 'BEGIN {print 100000 * 100000, 1/3, 123456789012}'
awk 'BEGIN {printf "%d %5.2f %e %s %c %x %o %%\n", 42.9, 3.14159, 1234.5, "str", 65, 255, 8}'
awk 'BEGIN {printf "%5d|%-5d|%05d|%+d\n", 42, 42, 42, 42}'
#### awk string functions
awk 'BEGIN {print length("hello"), substr("hello", 2, 3), substr("hello", 3), index("hello", "ll")}'
awk 'BEGIN {print toupper("abc"), tolower("XYZ"), length()}' < /dev/null
awk 'BEGIN {s = "a b c"; n = split(s, arr); print n, arr[1], arr[3]}'
awk 'BEGIN {n = split("a:b:c", arr, ":"); print n, arr[2]}'
awk 'BEGIN {s = "hello world"; sub(/o/, "0", s); print s; gsub(/o/, "0", s); print s}'
awk 'BEGIN {s = "aaa"; n = gsub(/a/, "b", s); print n, s}'
awk 'BEGIN {s = "abc"; gsub(/b/, "[&]", s); print s}'
awk 'BEGIN {if (match("foobar", /o+/)) print RSTART, RLENGTH}'
awk 'BEGIN {print sprintf("%03d-%s", 7, "x")}'
awk 'BEGIN {print substr("hello", 0, 2), substr("hello", -1, 3), substr("hello", 4, 100) "|"}'
echo "hello world" | awk '{gsub(/o/, "0"); print}'
echo "a.b.c" | awk '{gsub(/\./, "-"); print}'
echo "Hello" | awk '{print length($0), toupper(substr($0, 1, 1)) substr($0, 2)}'
#### awk control flow
awk 'BEGIN {for (i = 1; i <= 3; i++) printf "%d ", i; print ""}'
awk 'BEGIN {i = 0; while (i < 3) {i++; if (i == 2) continue; print i}}'
awk 'BEGIN {i = 0; do {i++} while (i < 5); print i}'
awk 'BEGIN {for (i = 1; i <= 10; i++) {if (i > 3) break; s += i}; print s}'
awk 'BEGIN {x = 5; if (x > 3) print "big"; else print "small"}'
awk 'BEGIN {x = 2; if (x == 1) print "one"; else if (x == 2) print "two"; else print "other"}'
awk 'BEGIN {print (1 > 2) ? "yes" : "no", 1 ? "t" : "f"}'
printf '1\n2\n3\n' | awk '$1 == 2 {next} {print}'
printf '1\n2\n3\n' | awk '{print} $1 == 2 {exit}'
printf '1\n2\n' | awk '{if ($1 == 1) {print "first"} else {print "other"}}'
awk 'BEGIN {exit 3}'; echo "st=$?"
printf 'x\n' | awk '{exit 4} END {print "end runs"}'; echo "st=$?"
#### awk arrays
awk 'BEGIN {a["x"] = 1; a["y"] = 2; print ("x" in a), ("z" in a), length(a)}'
awk 'BEGIN {a[1] = "one"; a[2] = "two"; delete a[1]; print (1 in a), a[2], length(a)}'
awk 'BEGIN {a[1,2] = "m"; print a[1,2]; for (k in a) {split(k, p, SUBSEP); print p[1], p[2]}}'
awk 'BEGIN {n = split("c a b", arr); for (i = n; i >= 1; i--) printf "%s ", arr[i]; print ""}'
printf 'k1 1\nk2 2\nk1 3\n' | awk '{sum[$1] += $2} END {for (k in sum) print k, sum[k]}' | sort
printf 'a\nb\na\n' | awk '!seen[$0]++'
printf 'x 1\ny 2\n' | awk '{v[NR] = $2} END {for (i = NR; i >= 1; i--) print v[i]}'
awk 'BEGIN {a["k"]; if ("k" in a) print "exists"; delete a; print length(a)}'
#### awk user functions
awk 'function add(a, b) {return a + b} BEGIN {print add(2, 3)}'
awk 'function fact(n) {return n <= 1 ? 1 : n * fact(n - 1)} BEGIN {print fact(10)}'
awk 'function fill(arr, n,   i) {for (i = 1; i <= n; i++) arr[i] = i * i} BEGIN {fill(sq, 3); print sq[1], sq[2], sq[3]}'
awk 'function max(a, b) {return a > b ? a : b} {m = max(m, $1)} END {print m}' <<< $'3\n9\n4'
awk 'function greet(name,    msg) {msg = "hi " name; return msg} BEGIN {print greet("x"); print msg "|"}'
#### awk variables from shell
awk -v n=5 'BEGIN {print n * 2}'
awk -v s="hello world" 'BEGIN {print length(s), s}'
x=42; awk -v v="$x" 'BEGIN {print v + 1}'
echo "data" | awk -v prefix=">> " '{print prefix $0}'
awk 'BEGIN {print ENVIRON["HOME"] != ""}'
th=2; printf '1\n2\n3\n' | awk -v t="$th" '$1 > t'
echo x | awk '{print v}' v=assigned -
#### awk output control
awk 'BEGIN {printf "no newline"; printf "\n"; print "a" > "/dev/stderr"}' 2>/dev/null
awk 'BEGIN {print "to file" > "out.txt"; print "more" > "out.txt"; close("out.txt")}'; cat out.txt
awk 'BEGIN {print "appended" >> "out.txt"}'; wc -l < out.txt
awk 'BEGIN {OFS = "\t"; print "a", "b"; ORS = "!\n"; print "c"}'
awk 'BEGIN {print "b\na" | "sort"; close("sort"); print "after"}'
awk 'BEGIN {"echo cmd-output" | getline x; print "got:", x}'
printf 'l1\nl2\nl3\n' | awk 'NR == 1 {getline; print "after getline:", $0}'
printf 'aa\nbb\n' > gl.txt; awk 'BEGIN {while ((getline line < "gl.txt") > 0) n++; print n, line}'
awk 'BEGIN {print 1, 2 > "/dev/stdout"}'
#### awk multiple files and FILENAME
printf 'a\nb\n' > f1.txt; printf 'c\n' > f2.txt
awk '{print FILENAME, FNR, NR, $0}' f1.txt f2.txt
awk 'FNR == 1 {print "start of " FILENAME}' f1.txt f2.txt
awk 'END {print NR}' f1.txt f2.txt
#### awk csv and report idioms
cat > emp.csv <<'EOF'
name,dept,salary
alice,eng,100
bob,ops,80
carol,eng,120
dave,ops,90
EOF
awk -F, 'NR > 1 {sum[$2] += $3; cnt[$2]++} END {for (d in sum) printf "%s %d %.1f\n", d, sum[d], sum[d]/cnt[d]}' emp.csv | sort
awk -F, 'NR > 1 && $3 >= 100 {print $1}' emp.csv
awk -F, 'NR == 1 {next} {printf "%-6s %5d\n", $1, $3}' emp.csv
awk -F, 'NR > 1 {if ($3 > max) {max = $3; who = $1}} END {print who, max}' emp.csv
awk -F, 'BEGIN {OFS = ","} NR > 1 {$3 = $3 * 1.1; print}' emp.csv
awk -F, 'NR > 1 {print toupper(substr($1, 1, 1)) substr($1, 2) " (" $2 ")"}' emp.csv
awk -F, '{print NF}' emp.csv | sort -u
awk -F, 'NR > 1 {total += $3} END {printf "total=%d avg=%.2f n=%d\n", total, total/(NR-1), NR-1}' emp.csv
#### awk text idioms
printf 'a\n\nb\n\n\nc\n' | awk 'NF'
printf 'x y z\n' | awk '{for (i = NF; i >= 1; i--) printf "%s%s", $i, (i > 1 ? " " : "\n")}'
printf 'line1\nline2\nline3\n' | awk 'END {print $0}'
printf 'a b\nc d\n' | awk '{print $2}' | paste -sd,
printf '  trim me  \n' | awk '{$1 = $1; print "[" $0 "]"}'
printf 'k: v\n' | awk -F': ' '{print $2}'
printf 'aXbXc\n' | awk '{n = split($0, p, "X"); print n, p[n]}'
printf '1 2 3\n4 5 6\n' | awk '{for (i = 1; i <= NF; i++) col[i] += $i} END {print col[1], col[2], col[3]}'
printf 'b 2\na 1\n' | awk '{print $2, $1}' | sort -n
printf 'long line here\nshort\n' | awk 'length($0) > 6'
printf 'A\nB\n' | awk '{printf "%s%s", sep, $0; sep = ","} END {print ""}'
seq 1 10 | awk 'NR % 3 == 0'
seq 1 5 | awk '{a[NR] = $0} END {print a[1] + a[5]}'
#### awk string vs number comparison
printf '10 9\nabc 5\n010 10\n' | awk '{print ($1 < $2), ($1 == $2)}'
echo "5" | awk '{if ($1 == 5.0) print "numeric eq"; if ($1 == "5") print "string eq"}'
awk 'BEGIN {if ("abc" < "abd") print "lt"; if (10 > 9) print "num"; if ("10" > "9") print "no"; else print "strcmp"}'
echo "0" | awk '{if ($1) print "true"; else print "false"}'
echo "0.0" | awk '{if ($1) print "true"; else print "false"}'
echo "a" | awk '{if ($1) print "true"; else print "false"}'
awk 'BEGIN {if (x == 0 && x == "") print "uninit is both"}'
awk 'BEGIN {x = "3x"; print x + 1, x * 2, +x}'
#### awk regex features
printf 'foo123\nbar\nfoo\n' | awk '/^foo[0-9]+$/'
printf 'a.b\naxb\n' | awk '/a\.b/'
printf 'ab\nabab\nb\n' | awk '/^(ab)+$/'
printf 'x1\nx22\n' | awk '{sub(/[0-9]+/, "<&>"); print}'
printf 'Hello\nhello\n' | awk 'tolower($0) ~ /^hello$/' | wc -l
printf 'a/b\n' | awk '{gsub("/", "-"); print}'
printf 'tab\there\n' | awk '/\t/ {print "has tab"}'
printf 'email@x.com\nbad\n' | awk '/^[a-z]+@[a-z]+\.[a-z]+$/ {print "ok:", $0}'
printf 'aaa\n' | awk '{print gsub(/a/, "b") ":" $0}'
re='^b'; printf 'abc\nbcd\n' | awk -v r="$re" '$0 ~ r'
#### awk in shell pipelines
total=$(printf '1 2\n3 4\n' | awk '{s += $1 * $2} END {print s}'); echo "total=$total"
ls_like=$(printf 'f1 10\nf2 20\n' | awk '$2 > 15 {print $1}'); echo "[$ls_like]"
printf 'a b\n' | awk '{print $2}' | tr a-z A-Z
for w in $(echo "x y z" | awk '{for (i = 1; i <= NF; i++) print $i}'); do printf '<%s>' "$w"; done; echo
printf '3\n1\n2\n' | sort -n | awk 'NR == 1 {min = $1} END {print min, $1}'
echo "2026-11-15 01:40:00 ERROR something bad" | awk '{print $3 ": " substr($0, index($0, $4))}'
