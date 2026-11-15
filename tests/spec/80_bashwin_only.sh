#### dos2unix and unix2dos applets [own]
printf 'a\r\nb\r\n' > crlf.txt
dos2unix crlf.txt
od -An -tx1 crlf.txt | tr -d ' \n'; echo
printf 'x\ny\n' | unix2dos | od -An -tx1 | tr -d ' \n'; echo
#= 610a620a
#= 780d0a790d0a
#### script with CRLF line endings runs [own]
printf 'echo one\r\nx=two\r\necho "$x"\r\nif true; then\r\n  echo three\r\nfi\r\n' > crlf.sh
"$PY" -m bashwin crlf.sh
#= one
#= two
#= three
#### igncr strips CR from command substitution [own]
set -o igncr
v=$(printf 'value\r\n')
echo "[$v] ${#v}"
printf 'k1 v1\r\nk2 v2\r\n' > f.txt
while read -r k v; do echo "<$v>"; done < f.txt
set +o igncr
v=$(printf 'value\r\n'); echo "${#v}"
#= [value] 5
#= <v1>
#= <v2>
#= 6
#### winpath conversions [own]
winpath -w a/b/c.txt
winpath -m 'C:\Users\x'
winpath -u 'C:/Users/x'
#= a\b\c.txt
#= C:/Users/x
#= /c/Users/x
#### raw exit status is kept [own]
"$PY" -c 'import sys; sys.exit(3)'
echo "$? $BASHWIN_RAWSTATUS"
#= 3 3
#### syntax check mode does not execute [own]
echo 'echo should-not-run; if true; then echo x; fi' > ok.sh
"$PY" -m bashwin -n ok.sh; echo "rc=$?"
printf 'if true; then\necho x\n' > bad.sh
"$PY" -m bashwin -n bad.sh 2>/dev/null; echo "rc=$?"
#= rc=0
#= rc=2
#### version variable and applet list [own]
[ -n "$BASHWIN_VERSION" ] && echo has-version
"$PY" -m bashwin --applets | grep -c applets
#= has-version
#= 1
#### unsupported features fail loudly [own]
"$PY" -m bashwin -c 'select x in a b; do echo $x; done' 2>/dev/null; echo "rc=$?"
"$PY" -m bashwin -c 'shopt -s extglob' 2>&1 | grep -c 'not supported'
"$PY" -m bashwin -c 'tail -f /dev/null' 2>/dev/null; echo "rc=$?"
#= rc=2
#= 1
#= rc=1
#### rm refuses filesystem root [own]
rm -rf / 2>/dev/null; echo "rc=$?"
#= rc=1
#### iconv sjis roundtrip file [own]
printf '漢字テスト\n' > u8.txt
iconv -f UTF-8 -t CP932 u8.txt > sj.txt
wc -c < sj.txt
iconv -f CP932 -t UTF-8 sj.txt
#= 11
#= 漢字テスト
#### inventory lists external commands without running [own]
cat > job.sh <<'EOF'
log() { echo "$*"; }
log start
sqlplus -s user/pass @run.sql | grep -v '^$' > out.txt
"$JAVA_HOME/bin/java" -jar app.jar
command robocopy src dst /E
rm -f out.txt
EOF
"$PY" -m bashwin --inventory job.sh | sed 's/  */ /g'
#= script: job.sh
#= functions (defined in script): log
#= shell builtins: command echo
#= bashwin applets: grep rm
#= external commands (must exist on the host):
#=  robocopy line 5
#=  sqlplus line 3
#= dynamic command names (decided at run time): line 4
#### ps1-check classifies scripts [own]
printf 'set -e\nif [ -f "$1" ]; then\n  "$APP" --in "$1"\nelse\n  echo "missing: $1"; exit 2\nfi\n' > portable.sh
printf 'ls | grep x\n' > unix.sh
"$PY" -m bashwin --ps1-check portable.sh >/dev/null; echo "rc=$?"
"$PY" -m bashwin --ps1-check unix.sh | tail -1 | sed 's/(.*//'; echo "rc=${PIPESTATUS[0]}"
#= rc=0
#= unix.sh: NOT transpilable 
#= rc=1
