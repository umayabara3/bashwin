# 差分テスト結果(bash 実物との突き合わせ)

- 基準: `GNU bash, version 5.2.21(1)-release (x86_64-pc-linux-gnu)`
- 対象: bashwin on Python 3.13.18 (linux)
- 判定: stdout のバイト一致 + 終了コード一致
- 結果: **506 / 506 合格**

| ファイル | ケース数 | 合格 | 不一致 |
|---|---:|---:|---|
| 01_basic.sh | 27 | 27 | - |
| 02_expansion.sh | 33 | 33 | - |
| 03_arrays.sh | 25 | 25 | - |
| 04_control.sh | 29 | 29 | - |
| 05_functions.sh | 25 | 25 | - |
| 06_redir_pipe.sh | 30 | 30 | - |
| 07_builtins.sh | 43 | 43 | - |
| 08_errexit.sh | 33 | 33 | - |
| 09_text.sh | 33 | 33 | - |
| 10_files.sh | 26 | 26 | - |
| 11_misc.sh | 30 | 30 | - |
| 12_scenarios.sh | 22 | 22 | - |
| 13_edge.sh | 68 | 68 | - |
| 14_awk.sh | 17 | 17 | - |
| 15_scripts.sh | 7 | 7 | - |
| 16_scripts2.sh | 8 | 8 | - |
| 17_options.sh | 22 | 22 | - |
| 18_ps1_subset.sh | 16 | 16 | - |
| 80_bashwin_only.sh | 12 | 12 | - |

## 設計上の差異(合否に数えない)

### syntax error is detected before anything runs

```sh
# bash は 1 コマンドずつ読んで実行するため "run" を出力してから構文エラーになる。
# bashwin は全体を先に解析するので、何も実行せずに終了コード 2 で止まる(安全側)。
echo "run"
if true; then
echo unterminated
```

| | 終了コード | stdout |
|---|---:|---|
| bash | 2 | `run\n` |
| bashwin | 2 | `` |

### type -t reports applets as builtin

```sh
# cat / grep / sed などは bashwin では内蔵コマンド。bash では外部ファイル。
type -t cat
type -t grep
```

| | 終了コード | stdout |
|---|---:|---|
| bash | 0 | `file\nfile\n` |
| bashwin | 0 | `builtin\nbuiltin\n` |

