#### output redirect and append
echo one > f.txt
echo two >> f.txt
cat f.txt
> empty.txt
wc -c < empty.txt
#### input redirect
echo content > in.txt
cat < in.txt
read -r line < in.txt; echo "[$line]"
#### stderr redirect
{ echo out; echo err >&2; } 2>/dev/null
{ echo out; echo err >&2; } 2>&1 | sort
{ echo out; echo err >&2; } > both.txt 2>&1; sort both.txt
{ echo out2; echo err2 >&2; } &> amp.txt; sort amp.txt
#### redirect order matters
{ echo out; echo err >&2; } 2>&1 >/dev/null | sed 's/^/captured:/'
#### fd duplication
exec 3>&1
echo "via fd3" >&3
exec 3>&-
{ echo "to stdout"; } 3>/dev/null
#### custom fds
exec 4> fd4.txt
echo "line a" >&4
echo "line b" >&4
exec 4>&-
cat fd4.txt
exec 5< fd4.txt
read -r first <&5
read -r second <&5
exec 5<&-
echo "$first|$second"
#### heredoc basic
cat <<EOF
line 1
line 2
EOF
#### heredoc with expansion
name=world
cat <<EOF
hello $name
sum: $((1+2))
cmd: $(echo sub)
literal: \$name
EOF
#### heredoc quoted delimiter
name=world
cat <<'EOF'
hello $name $(echo no) `no`
EOF
cat <<"EOF"
also $name
EOF
#### heredoc tab stripping
cat <<-EOF
	indented with tab
		two tabs
	EOF
#### heredoc in pipeline and multiple
cat <<EOF | tr a-z A-Z
piped
EOF
cat <<A; cat <<B
first
A
second
B
#### heredoc to variable and function
v=$(cat <<EOF
captured
text
EOF
)
echo "$v"
f() { cat; }
f <<EOF
to function
EOF
#### herestring
cat <<< "here string"
x="a b"
read -r p q <<< "$x"; echo "$q $p"
wc -w <<< "one two three"
#### pipelines
echo hello | cat | cat
printf '3\n1\n2\n' | sort | head -1
echo "a b c" | tr ' ' '\n' | wc -l
seq 1 100 | grep 5 | wc -l
#### pipeline exit status
true | false; echo $?
false | true; echo $?
set -o pipefail
false | true; echo $?
true | false | true; echo $?
set +o pipefail
#### pipe stderr too
{ echo out; echo err >&2; } |& sort
#### pipeline with compound commands
for i in 3 1 2; do echo $i; done | sort
{ echo b; echo a; } | sort
if true; then echo x; fi | cat
while read -r l; do echo "got $l"; done < <(printf 'p\nq\n')
#### pipeline producer stops early
seq 1 100000 | head -3
yes | head -2
#### process substitution input
diff <(echo a) <(echo a) && echo same
cat <(echo from-procsub)
#### command substitution with pipes
n=$(printf 'a\nb\nc\n' | wc -l)
echo "$n lines"
first=$(printf 'z\ny\n' | sort | head -1)
echo $first
#### redirect to and from same loop
printf '1\n2\n3\n' > nums.txt
while read -r n; do echo $((n*2)); done < nums.txt > doubled.txt
cat doubled.txt
#### noclobber and force
echo a > nc.txt
set -o noclobber
echo b > nc.txt 2>/dev/null; echo "st=$?"
echo c >| nc.txt; cat nc.txt
set +o noclobber
#### redirect errors
cat < /nonexistent/file 2>/dev/null; echo "st=$?"
echo x > /nonexistent/dir/file 2>/dev/null; echo "st=$?"
echo still running
#### dev null
echo discard > /dev/null
cat /dev/null | wc -c
#### tee
echo data | tee t1.txt t2.txt | tr a-z A-Z
cat t1.txt t2.txt
echo more | tee -a t1.txt > /dev/null; cat t1.txt
#### read from stdin in subshell pipeline keeps position
printf 'a\nb\nc\n' | { read -r x; read -r y; echo "$x-$y"; cat; }
#### nested command substitution and quotes
echo "$(echo "a $(echo "b $(echo c)")")"
x="$(printf '%s' "quo\"te")"; echo "$x"
#### stdout stderr swap
{ echo o; echo e >&2; } 3>&1 1>&2 2>&3 | sed 's/^/E:/' 2>/dev/null
#### close stdin
echo hi | cat <&-  2>/dev/null; echo "ran"
#### background and wait
( echo bg ) &
wait
echo fg
sleep 0.1 & wait $!; echo "waited $?"
( exit 3 ) & wait $!; echo "status $?"
