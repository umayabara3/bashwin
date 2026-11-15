#### mkdir and rmdir
mkdir d1
mkdir -p a/b/c
[ -d a/b/c ] && echo nested
mkdir d1 2>/dev/null; echo "st=$?"
mkdir -p d1; echo "st=$?"
rmdir d1; [ -d d1 ] || echo removed
rmdir a 2>/dev/null; echo "st=$?"
#### touch and test
touch new.txt
[ -f new.txt ] && [ ! -s new.txt ] && echo "empty file"
touch new.txt; echo "st=$?"
touch -c nocreate.txt; [ -e nocreate.txt ] || echo "not created"
#### cp files
echo data > src.txt
cp src.txt dst.txt; cat dst.txt
mkdir dir; cp src.txt dir/; ls dir
cp src.txt dst.txt dir/; ls dir
cp nonexistent x 2>/dev/null; echo "st=$?"
cp src.txt 2>/dev/null; echo "st=$?"
#### cp recursive
mkdir -p t/sub; echo 1 > t/a; echo 2 > t/sub/b
cp -r t t2; find t2 | sort
mkdir existing; cp -r t existing/; find existing | sort
cp t t3 2>/dev/null; echo "st=$?"
#### mv
echo x > m1; mv m1 m2; ls m*; cat m2
mkdir md; mv m2 md/; ls md
echo y > m3; echo z > m4; mv m3 m4; cat m4
mkdir mdir1; mv mdir1 mdir2; [ -d mdir2 ] && echo dir-renamed
mv nonexistent x 2>/dev/null; echo "st=$?"
#### rm
touch r1 r2 r3
rm r1; ls r*
rm r2 r3; ls r* 2>/dev/null; echo "st=$?"
rm nonexistent 2>/dev/null; echo "st=$?"
rm -f nonexistent; echo "st=$?"
mkdir -p rd/sub; touch rd/sub/f
rm rd 2>/dev/null; echo "st=$?"
rm -r rd; [ -e rd ] || echo gone
rm -rf nothing1 nothing2; echo "st=$?"
#### ls
mkdir l; touch l/b l/a l/.hidden; mkdir l/sub
ls l
ls -a l
ls -A l
ls -1 l
ls l/a l/b
ls -d l
ls -p l
ls -r l
ls nonexistent 2>/dev/null; echo "st=$?"
#### ls multiple dirs
mkdir x y; touch x/1 y/2
ls x y
#### find by name and type
mkdir -p f/a/b f/c; touch f/a/one.txt f/a/b/two.txt f/c/three.log f/top.txt
find f -name '*.txt' | sort
find f -type d | sort
find f -type f -name 't*' | sort
find f -maxdepth 1 | sort
find f -mindepth 2 -type f | sort
find f -name '*.log' -o -name 'top*' | sort
find f ! -name '*.txt' -type f
find f -iname 'ONE*'
find f -path '*/b/*'
#### find with exec and delete
mkdir -p g; touch g/1.tmp g/2.tmp g/keep.txt
find g -name '*.tmp' -exec echo found {} \; | sort
find g -name '*.tmp' -exec echo batch {} + | tr ' ' '\n' | sort | tr '\n' ' '; echo
find g -name '*.tmp' -delete
ls g
find g -type f -exec cat {} \; | wc -c
#### find empty and size
mkdir -p h/emptydir; touch h/empty; echo data > h/full
find h -empty | sort
find h -type f -size +0 
find h -type f ! -empty
#### find newer
touch -d '2020-01-01' old.txt
touch -d '2024-06-01' mid.txt
touch new.txt
find . -maxdepth 1 -name '*.txt' -newer mid.txt
find . -maxdepth 1 -name '*.txt' ! -newer mid.txt | sort
#### find prune
mkdir -p p/skip p/keep; touch p/skip/a p/keep/b
find p -name skip -prune -o -type f -print
#### basename dirname
basename /usr/local/bin/tool
basename /usr/local/bin/tool.sh .sh
basename tool
basename /trailing/
dirname /usr/local/bin/tool
dirname tool
dirname /
dirname a/b/
basename -a /x/one /y/two
basename -s .txt /a/b.txt
#### path manipulation with expansion
p=/var/log/app/server.2026.log
echo "${p##*/}" "${p%/*}" "${p##*.}"
f=${p##*/}; echo "${f%%.*}" "${f%.*}" "${f#*.}"
#### realpath and readlink
mkdir -p rp/a; touch rp/a/f
cd rp; realpath a/../a/f | sed "s|^$HOME||"
realpath -m a/b/../c | sed "s|^$HOME||"
#### symlinks [posix]
echo target > st.txt
ln -s st.txt link
[ -L link ] && echo is-link
cat link
readlink link
ln -sf st.txt link; echo "st=$?"
rm link; [ -e st.txt ] && echo target-kept
#### chmod and permissions [posix]
touch perm; chmod 600 perm
[ -r perm ] && [ -w perm ] && echo rw
stat -c %a perm
chmod u+x perm; stat -c %a perm
chmod go+r perm; stat -c %a perm
chmod a-w perm; stat -c %a perm
[ -x perm ] && echo executable
#### stat size
printf '12345' > sz
stat -c %s sz
stat -c '%n %s' sz
wc -c < sz
#### mktemp
t=$(mktemp); [ -f "$t" ] && echo file-created; rm "$t"
d=$(mktemp -d); [ -d "$d" ] && echo dir-created; rmdir "$d"
t2=$(mktemp ./tmp.XXXXXX); case $t2 in ./tmp.??????) echo pattern-ok;; esac; rm "$t2"
t3=$(mktemp); t4=$(mktemp); [ "$t3" != "$t4" ] && echo unique; rm "$t3" "$t4"
#### file loops and globs
mkdir w; for i in 1 2 3; do echo "c$i" > w/f$i.txt; done
for f in w/*.txt; do echo "$(basename "$f"): $(cat "$f")"; done
n=0; for f in w/*; do n=$((n+1)); done; echo $n
cat w/*.txt | wc -l
#### spaces in filenames
mkdir "sp dir"; echo hi > "sp dir/a file.txt"
cat "sp dir/a file.txt"
for f in "sp dir"/*; do echo "[$f]"; done
ls "sp dir"
find "sp dir" -type f | while IFS= read -r f; do wc -c < "$f"; done
cp "sp dir/a file.txt" "sp dir/b file.txt"; ls "sp dir" | wc -l
rm -r "sp dir"; ls | wc -l
#### file tests with globs and counts
mkdir c; touch c/a.log c/b.log c/c.txt
set -- c/*.log; echo $#
ls c | wc -l
ls c/*.log | wc -l
[ -e c/a.log ] && echo exists
files=(c/*); echo ${#files[@]}
#### du and disk helpers
mkdir du; printf '%1000s' x > du/f
du -sb du/f | cut -f1
#### gzip tar roundtrip
mkdir -p ar/sub; echo one > ar/1.txt; echo two > ar/sub/2.txt
tar -czf ar.tar.gz ar
rm -r ar
tar -tzf ar.tar.gz | sort
tar -xzf ar.tar.gz
cat ar/1.txt ar/sub/2.txt
echo compress-me > z.txt; gzip z.txt; [ -f z.txt.gz ] && [ ! -f z.txt ] && echo gzipped
gunzip z.txt.gz; cat z.txt
gzip -c z.txt | gunzip -c
gzip -c z.txt | zcat
#### write then read many files
mkdir many
for i in $(seq 1 50); do echo $i > many/$i; done
ls many | wc -l
cat many/* | sort -n | tail -1
find many -type f | wc -l
rm many/1*; ls many | wc -l
