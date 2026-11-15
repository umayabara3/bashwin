#### indexed array basics
a=(one two three)
echo ${a[0]} ${a[1]} ${a[2]} "[${a[3]}]"
echo ${a[@]} ${#a[@]} ${#a[1]}
echo $a
#### array with spaces
a=("x y" z)
for e in "${a[@]}"; do echo "<$e>"; done
for e in ${a[@]}; do echo "<$e>"; done
for e in "${a[*]}"; do echo "<$e>"; done
#### array assignment and append
a=()
a+=(1)
a+=(2 3)
a[5]=six
echo "${a[@]}" ${#a[@]} "${!a[@]}"
a[1]=TWO
a[0]+=x
echo "${a[@]}"
#### array slice
a=(a b c d e)
echo "${a[@]:1}" "|" "${a[@]:1:2}" "|" "${a[@]: -2}"
#### array negative index
a=(a b c)
echo ${a[-1]} ${a[-2]}
#### array unset element
a=(a b c d)
unset 'a[1]'
echo "${a[@]}" ${#a[@]} "${!a[@]}"
unset a
echo "[${a[@]}]" ${#a[@]}
#### array in arithmetic
a=(10 20 30)
i=1
echo $(( a[i] + a[2] )) $(( a[0]++ )) ${a[0]}
(( a[1] = 99 )); echo ${a[1]}
#### array transformations
a=(apple.txt banana.txt cherry.md)
echo "${a[@]%.txt}"
echo "${a[@]/a/A}"
echo "${a[@]^}"
echo "${a[@]#*.}"
#### array from command substitution
a=($(echo x y z))
echo ${#a[@]} ${a[2]}
#### array from glob
touch f1.dat f2.dat
a=(*.dat)
echo ${#a[@]} "${a[@]}"
#### array copy and join
a=("a b" c)
b=("${a[@]}")
echo ${#b[@]}
IFS=,; echo "${a[*]}"; unset IFS
#### loop over indices
a=(x y z)
for i in "${!a[@]}"; do echo "$i=${a[$i]}"; done
#### associative array
declare -A m
m[apple]=red
m[banana]=yellow
m["key with space"]=v
echo ${m[apple]} ${m[banana]} "${m[key with space]}" ${#m[@]}
k=apple; echo ${m[$k]}
#### associative array literal and keys
declare -A m=([a]=1 [b]=2 [c]=3)
for k in "${!m[@]}"; do echo "$k=${m[$k]}"; done | sort
echo "${m[@]}" | tr ' ' '\n' | sort | tr '\n' ' '; echo
#### associative unset and test
declare -A m=([x]=1 [y]=2)
unset 'm[x]'
echo ${#m[@]}
[[ -v m[y] ]] && echo has-y
[[ -v m[x] ]] || echo no-x
[ -n "${m[y]+set}" ] && echo y-set
#### associative increment
declare -A cnt
for w in a b a c a b; do (( cnt[$w]++ )); done
for k in a b c; do echo "$k ${cnt[$k]}"; done
#### array length of empty and unset
unset nope
echo ${#nope[@]}
e=()
echo ${#e[@]}
for x in "${e[@]}"; do echo never; done; echo ok
#### array element with default
a=(x)
echo "${a[5]:-default}" "${a[0]:-default}"
#### scalar as array
s=scalar
echo ${s[0]} ${#s[@]} "${s[@]}"
#### read into array
read -ra parts <<< "a b c"
echo ${#parts[@]} ${parts[1]}
IFS=: read -ra parts <<< "x:y:z"
echo ${#parts[@]} ${parts[2]}
#### mapfile
printf 'l1\nl2\nl3\n' > f.txt
mapfile -t lines < f.txt
echo ${#lines[@]} "${lines[1]}"
#### declare -a and local arrays
f() { local -a arr=(1 2 3); local x=("$@"); echo ${#arr[@]} ${#x[@]}; }
f a b
declare -a g
g[2]=z
echo ${#g[@]}
#### array of arrays simulation
declare -A grid
for r in 0 1; do for c in 0 1; do grid[$r,$c]=$((r*2+c)); done; done
echo ${grid[0,0]} ${grid[0,1]} ${grid[1,0]} ${grid[1,1]}
#### BASH_REMATCH array
if [[ "2026-11-15" =~ ^([0-9]+)-([0-9]+)-([0-9]+)$ ]]; then
  echo "${BASH_REMATCH[0]}" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" ${#BASH_REMATCH[@]}
fi
#### PIPESTATUS
true | false | true
echo "${PIPESTATUS[@]}"
false | true
echo "${PIPESTATUS[0]} ${PIPESTATUS[1]}"
