# 互換性（bashwin v0.1）

基準は GNU bash 5.2 と GNU coreutils / grep / sed / gawk。
ここに挙げたのは実装済みの範囲で、主な使い方は `tests/spec/` で本物と突き合わせてある。
ただしオプションの全組み合わせを網羅してはいない。出力書式の一致を保証しないものは注記する。

## 1. 対応する構文

| 分類 | 内容 |
|---|---|
| クォート | `'...'` `"..."` `\x` `$'...'`（ANSI-C） `$"..."` |
| 変数 | スカラー、添字配列、連想配列（`declare -A`）、`local`、`export`、`readonly`、`declare -i/-l/-u/-r/-x/-a/-A/-g/-p` |
| 特殊変数 | `$?` `$#` `$@` `$*` `$0` `$1`… `$$` `$!` `$-` `RANDOM` `SECONDS` `LINENO` `FUNCNAME` `BASH_SOURCE` `PIPESTATUS` `BASH_REMATCH` `OPTIND` `OPTARG` `REPLY` `PWD` `OLDPWD` `IFS` |
| パラメータ展開 | `${x:-d}` `${x-d}` `${x:=d}` `${x:?m}` `${x:+a}` `${#x}` `${x#p}` `${x##p}` `${x%p}` `${x%%p}` `${x/p/r}` `${x//p/r}` `${x/#p/r}` `${x/%p/r}` `${x:o:l}` `${x^}` `${x^^}` `${x,}` `${x,,}` `${!x}` `${!p@}` `${!a[@]}` `${x@Q}` `${x@U}` `${x@L}` `${a[@]:o:l}` |
| その他の展開 | `$(...)` `` `...` `` `$((...))` `$(<file)` ブレース `{a,b}` `{1..9}` `{01..10..2}`、チルダ、パス名（`*` `?` `[...]`）、`<(...)` |
| 算術 | `+ - * / % **` 比較、論理、ビット演算、三項、代入演算、`++` `--`、8 進・16 進・`base#n`、64bit で折り返し |
| 制御 | `if/elif/else` `case`（`;;` `;&` `;;&`） `for in` `for ((;;))` `while` `until` `break N` `continue N` |
| 複合 | `{ ...; }` `( ... )` `[[ ... ]]`（`== != < > =~ -eq … && \|\| ! ( )`） `(( ... ))` 関数（`f() {}` / `function f {}`） |
| リスト | `;` `&&` `\|\|` `!` `&`（バックグラウンド） |
| パイプ | `\|` `\|&`、`set -o pipefail` |
| リダイレクト | `<` `>` `>>` `>\|` `<>` `2>&1` `&>` `&>>` `N>&M` `N>&-` `<<EOF` `<<-EOF` `<<'EOF'` `<<<` |
| オプション | `set -e -u -x -f -a -C`、`set -o errexit/nounset/xtrace/pipefail/noglob/noclobber/igncr`、`shopt -s nullglob/nocasematch/nocaseglob/dotglob/inherit_errexit` |

## 2. シェル組み込み（53 個）

`.` `:` `[` `alias`※ `break` `builtin` `cd` `command` `continue` `declare` `dirs` `echo` `eval` `exit`
`export` `false` `getopts` `jobs` `kill` `let` `local` `mapfile` `popd` `printf` `pushd` `pwd` `read`
`readarray` `readonly` `return` `set` `shift` `shopt` `source` `test` `trap` `true` `type` `typeset`
`unalias` `unset` `wait`（`-n` 対応）。

何もしないで成功を返すもの：`bind` `compgen` `complete` `disown` `enable` `fc` `hash` `history` `times` `ulimit` `umask`。
※ `alias` は定義しようとするとエラー（関数を使う）。

## 3. 内蔵コマンド（74 個）と主なオプション

| コマンド | 対応オプション・機能 |
|---|---|
| `cat` | `-n` `-b` |
| `head` / `tail` | `-n N` `-N` `-c N`、`head -n -N`、`tail -n +N`（`tail -f` は非対応） |
| `wc` | `-l -w -c -m -L` |
| `sort` | `-r -n -u -f -b -s -c -o FILE -t SEP -k F[.C][opts][,F[.C][opts]]` |
| `uniq` | `-c -d -u -i` |
| `cut` | `-d -f -c -b -s` |
| `tr` | `-d -s -c`、範囲、`[:class:]`、`\n` `\t` `\NNN` |
| `tee` | `-a` |
| `grep` `egrep` `fgrep` | `-E -F -P -i -v -n -c -q -s -l -L -h -H -o -w -x -r -e -f -m -A -B -C` |
| `sed` | `-n -e -f -E/-r -i[SUFFIX] -s`。アドレス `N` `$` `/re/` `first~step` `a,b` `a,+N` `!`。コマンド `s`（`g p i N w`） `y d D p P a i c n N g G h H x = q Q b t T : r w l { }` |
| `awk` | `-F -v -f`。BEGIN/END、パターン・範囲、連想配列、`if/while/do/for/for-in`、関数定義、`print/printf` と `> >> \|`、`getline`（単体・`< file`・`cmd \|`）、`length substr index split sub gsub match sprintf tolower toupper int sqrt exp log sin cos atan2 rand srand system close fflush systime strftime` |
| `rev` `tac` `nl` `paste` `seq` `yes` | `nl -b -w -s -v`、`paste -d -s`、`seq -s -w -f` |
| `base64` | `-d -w` |
| `md5sum` `sha1sum` `sha256sum` `sha512sum` | ファイル／標準入力、`-c` |
| `diff` / `cmp` | `diff -u -U N -q -s -i -b -w`（ファイル同士のみ）、`cmp -s` |
| `expr` | 算術、比較、`:`、`length substr index match` |
| `od` | `-c -b -x -t x1/o1/d1/u1 -A n/o/d/x -N -v` |
| `iconv` | `-f -t -c -o`（SJIS/CP932/EUC-JP/UTF-8/UTF-16 ほか Python が持つ全コーデック） |
| `dos2unix` `unix2dos` | ファイルを書き換え、または標準入力→標準出力 |
| `ls` | `-1 -a -A -d -l -r -t -S -R -p -F -h`（`-l` の書式は GNU に近い形。所有者欄は Windows では固定文字列） |
| `mkdir` `rmdir` `rm` | `mkdir -p -v`、`rmdir -p`、`rm -r -f -v -d` |
| `cp` / `mv` | `cp -r -a -p -f -n -u -v -t -T`、`mv -f -n -u -v -t -T` |
| `touch` | `-c -r FILE -d STR -t STAMP` |
| `ln` | `-s -f`（Windows のシンボリックリンクは権限が要る） |
| `chmod` `chown` `chgrp` | 8 進・記号指定、`-R`（Windows では書き込み可否のみ。`chown` は何もしない） |
| `mktemp` | `-d -u -p DIR -t`、テンプレート |
| `realpath` `readlink` `basename` `dirname` | `realpath -e -m -s`、`readlink -f`、`basename -a -s` |
| `find` | `-name -iname -path -regex -type -maxdepth -mindepth -depth -mtime -mmin -newer -size -empty -readable -writable -executable -print -print0 -delete -prune -quit -exec … ; / +`、`! -a -o ( )` |
| `stat` / `du` | `stat -c`（`%s %n %Y %y %a %A %U %G %F` ほか）`-L`、`du -s -h -k -b -a -c -d N` |
| `date` | `+FORMAT`（OS 非依存の自前実装） `-u -d STR -r FILE -R -I`。`-d` は `@秒`、`YYYY-MM-DD[ HH:MM[:SS]]`、`N day/week/month/year[s] [ago]`、`yesterday` `tomorrow` など |
| `sleep` `timeout` | 小数と `s m h d`、`timeout -s -k` |
| `env` `printenv` `which` | `env -i -u VAR=val cmd` |
| `xargs` | `-n -I -d -0 -r -t -L` |
| `hostname` `whoami` `uname` `id` `nproc` `tput` | 基本形 |
| `gzip` `gunzip` `zcat` `tar` `zip` `unzip` | `tar c/x/t z j J v f C O`、`zip -r -q -j`、`unzip -l -q -o -d -p` |
| `winpath`（別名 `cygpath`） | `-w`（`C:\a\b`） `-m`（`C:/a/b`） `-u`（`/c/a/b`） `-a`（絶対化） |
| `sh` `bash` | bashwin 自身を別シェルとして実行する。`bash script.sh 引数`、`sh -c '...'`、`-e -u -x -o NAME`、`-n`、`-s` |

内蔵コマンドより外部の同名コマンドを優先したいときは `BASHWIN_PREFER_EXTERNAL=1`。

## 4. 未対応（エラーまたは警告になる）

| 機能 | 挙動 |
|---|---|
| `select`、`coproc` | 構文エラー（実行前に停止） |
| `shopt -s extglob / globstar / lastpipe` | 警告を出して無視 |
| nameref（`declare -n` `local -n`） | エラー（終了コード 2） |
| `export -f` | エラー（終了コード 2） |
| `>( ... )` | エラー |
| `trap ... DEBUG / RETURN` | 警告（受け付けるが発火しない） |
| `alias` の定義 | エラー |
| `tail -f` | エラー |
| ジョブ制御（`fg` `bg` `Ctrl+Z`）、対話機能、履歴、補完 | なし |
| `read -t`（タイムアウト） | 無視される（待ち続ける） |
| 内蔵コマンドの未実装オプション | 「invalid option」で失敗 |

## 5. bash との差異（仕様として選んだもの）

| 項目 | bash | bashwin | 理由 |
|---|---|---|---|
| 構文エラー | そこまで実行してから止まる | 1 行も実行せず終了コード 2 | 途中まで実行されるより安全 |
| `type -t grep` | `file` | `builtin` | grep 等は内蔵コマンド |
| `$!`（複合コマンドをバックグラウンド実行したとき） | 子プロセスの PID | 内部ジョブ番号（100001〜） | fork が無い。単純な外部コマンドなら本物の PID |
| サブシェルの `$$` `$BASHPID` | プロセスごと | 常に bashwin 本体の PID | 同上 |
| `sort` と グロブの並び順 | ロケール依存 | 常にコードポイント順（`LC_ALL=C` 相当） | 環境差を無くす |
| `diff` の出力 | Myers 法 | Python difflib | 差分の「有無」と終了コードは同じ。行の切り方が違うことがある |
| `awk` | gawk | gawk に合わせたサブセット | 未対応関数（`gensub` 等）はエラー |
| `find` `ls -R` の走査順 | ディレクトリ順 | OS の列挙順（`ls` は名前順） | 順序に依存する処理は `sort` を挟む |
| エラーメッセージの文言 | — | 形式は近いが一致しない | 標準エラーの文言に依存しないこと |

## 6. Windows での注意

| 項目 | 内容 |
|---|---|
| パス | `C:/dir/file` と書く。`\` はエスケープ文字なので `'C:\dir\file'` のように引用する |
| 仮想パス | bashwin が開くパスに限り `/dev/null`→`NUL`、`/tmp/...`→一時フォルダ、`/c/...`→`C:/...`。無効化は `BASHWIN_PATHMAP=0` |
| 外部コマンドへの引数 | **書き換えない**。`/c/...` はそのまま渡る。Windows 形式が要るなら `$(winpath -w "$p")` |
| `PATH` | Windows 形式（`;` 区切り）のまま。追加は `PATH="$PATH;C:/tools/bin"` |
| 環境変数名 | Windows 側の都合で大文字に正規化されて見える（`Path`→`PATH`） |
| 改行 | スクリプトは CRLF でも LF でも読める。出力は LF。CRLF が要る相手には `unix2dos` |
| `igncr` | 既定で有効。`$(...)` の結果と `read` で行末の CR を落とす。無効化は `set +o igncr` |
| 文字コード | 既定 UTF-8。`BASHWIN_ENCODING=cp932` で入出力とデータ解釈を cp932 にできる。ファイル単位の変換は `iconv` |
| `printf` の幅 | バイト数で数える（bash と同じ）。全角文字の桁揃えは `printf` では合わない |
| 終了コード | 0〜255 に正規化。元が非 0 で下位 8bit が 0 なら 255。生の値は `$BASHWIN_RAWSTATUS` |
| `.cmd` / `.bat` | `cmd.exe /d /s /c` 経由。引数中の `% ^ & < > \|` は cmd.exe が解釈する。UNC パスをカレントにして呼ぶと cmd.exe が拒否する |
| `.ps1` | `powershell.exe -NoProfile -NonInteractive -File`。実行ポリシーは環境の設定に従う（回避フラグは付けない） |
| `.sh` / shebang が sh・bash のファイル | bashwin がプロセス内で「別シェル」として実行（export 済みの変数だけ渡る） |
| シンボリックリンク | `ln -s` は開発者モードか管理者権限が要る |
| パーミッション | `chmod` は読み取り専用属性の切り替えだけ。`-x` 判定は拡張子（`PATHEXT`、`.sh` `.py` `.ps1`）と shebang |
| 大文字小文字 | ファイル名は区別されない（NTFS）。グロブの照合は区別する |
| `kill` | TerminateProcess による強制終了のみ。`kill -0`（生存確認）は対応 |
| コンソール | 標準入出力がコンソールのときは Unicode で入出力される |

上の表は設計と机上確認に基づく。**実機での確認は未実施**（[VERIFICATION.md](VERIFICATION.md)）。
