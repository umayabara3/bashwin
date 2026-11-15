#### syntax error is detected before anything runs [differs]
# bash は 1 コマンドずつ読んで実行するため "run" を出力してから構文エラーになる。
# bashwin は全体を先に解析するので、何も実行せずに終了コード 2 で止まる(安全側)。
echo "run"
if true; then
echo unterminated
#### type -t reports applets as builtin [differs]
# cat / grep / sed などは bashwin では内蔵コマンド。bash では外部ファイル。
type -t cat
type -t grep
