# bashwin（仮称）

Windows で **bash スクリプトをそのまま実行する**ための、純 Python 製 Bash 互換インタープリター。

- 依存は **Python 標準ライブラリのみ**（3.8 以上を想定）。`pip install` 不要、単一ファイル `dist/bashwin.pyz`（約 120KB）で配れる
- `grep` `sed` `awk` `sort` `find` など **74 個のコマンドを内蔵**。Windows に Unix コマンドが無くても動く
- 外部コマンド（`java.exe` `sqlplus.exe` `robocopy.exe` …）は本物の子プロセスとして起動し、終了コードをそのまま返す
- 実行時に AI もネットワークも使わない
- **Bash → PowerShell トランスパイラー**（`--ps1`）も同梱。Python を置けない実行機向けに、単体で動く `.ps1` を生成する。
  対象は「EXE を順に呼び、終了コードで分岐する」範囲に限る。**PowerShell 上での実行検証は未実施**（[docs/TRANSPILER.md](docs/TRANSPILER.md)）

## 現在の状態（2026-11-15）：保留

Git for Windows に付属する bash（Git Bash）がバッチの実行機でも使えるなら、自作の大半は不要になる
（[docs/ALT_B_existing_binaries.md](docs/ALT_B_existing_binaries.md)）。それを先に確かめるため、開発を止めている。

| 再開前に決めること・測ること | 方法 |
|---|---|
| 実行機に Git for Windows があるか、バッチ実行に使ってよいか | 運用部門に確認 |
| Git Bash が Linux の bash と同じに動くか（引数の書き換え、改行、文字コードなど） | `python tests\run_golden.py --shell "C:\Program Files\Git\bin\bash.exe" --report gitbash.md` |

止めた時点で未了のもの：インタープリターの Windows 実機検証（`tests\run_golden.py`）、
トランスパイラーの PowerShell 実行検証（`tests\run_ps1.py`。生成物は 1 度も実行していない）、トランスパイラーの第 2 段。

名前は仮称。置き換える場合はパッケージ名 `bashwin` と環境変数接頭辞 `BASHWIN_` を一括置換する。

## 動かす

```bat
rem スクリプトを実行（終了コードはスクリプトの終了コード）
python dist\bashwin.pyz examples\nightly_job.sh C:\data\in C:\data\out 7

rem 1 行だけ実行
python dist\bashwin.pyz -c "ls *.csv | wc -l"

rem 実行せずに構文だけ検査（bash -n 相当）
python dist\bashwin.pyz -n job.sh

rem スクリプトが使うコマンドの棚卸し（外部コマンド＝実行機に必要なもの）
python dist\bashwin.pyz --inventory job.sh
```

ソースのまま使う場合は、このフォルダで `python -m bashwin job.sh`。

ジョブ管理ツール（JP1 など）からは、ランチャーを挟まず `python.exe` を直接呼ぶ形を推奨する。

```
実行ファイル: C:\tools\python\python.exe
パラメーター: C:\tools\bashwin\bashwin.pyz D:\jobs\nightly_job.sh D:\data\in D:\data\out 7
```

## 何が書けるか

変数・配列・連想配列、`if` `case` `for` `while` `until`、関数と `local`、`$(...)`、`$((...))`、
`[[ ]]` と正規表現、パイプライン、リダイレクトとヒアドキュメント、`set -euo pipefail`、`trap`、
`getopts`、`read`、`printf`、バックグラウンドジョブと `wait`。詳細は [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)。

対応しないものは黙って無視せず、エラーか警告にする（`select`、`extglob`、nameref、`export -f` など）。

## どこまで確かめてあるか

| 測ったもの | 結果 |
|---|---|
| 本物の bash 5.2 との突き合わせ（stdout のバイト一致＋終了コード） | 494 / 494 件一致 |
| bashwin 固有機能のテスト | 12 / 12 件 |
| Python 3.8 互換（構文検査＋最小バージョン解析） | 問題なし（静的検査） |
| Windows 固有ロジック（パス対応付け・起動判定・終了コード） | 机上シミュレーション 6 / 6 件 |
| トランスパイラーの静的検査（構文の対応、5.1 で使えない書き方の不使用、fail-closed） | 全項目通過 |
| **トランスパイラーの生成物を PowerShell で実行** | **未実施**（`python tests\run_ps1.py` で測る） |
| **Windows 実機での実行** | **未実施**（下の手順で測る） |

Windows 実機では、まずこれを実行する（bash は不要。約 30 秒）。

```bat
python tests\run_golden.py --report golden_windows.md
```

`tests/golden/` に入っている「本物の bash の出力」と突き合わせ、不一致を `golden_windows.md` に書き出す。
詳細は [docs/VERIFICATION.md](docs/VERIFICATION.md)。

## 文書

| 文書 | 内容 |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | 方式の選択肢と判定、構成、Windows を前提にした設計判断 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 立場ごとの使い方、役割×時間軸の運用確認表 |
| [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) | 対応構文・内蔵コマンド・未対応・bash との差異・Windows の注意 |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | 検証方法と結果、未検証事項、実機での再測定手順、性能 |
| [docs/TRANSPILER.md](docs/TRANSPILER.md) | Bash → PowerShell トランスパイラー：使い方、変換できる範囲、bash との差異、検証の状況 |
| [docs/ALT_A_powershell_transpiler.md](docs/ALT_A_powershell_transpiler.md) | 代替案 A：「実行機に Python を置けない」場合の比較と適用範囲の実測 |
| [docs/ALT_B_existing_binaries.md](docs/ALT_B_existing_binaries.md) | 代替案 B：「自作を保守したくない」場合 |

## フォルダ構成

```
bashwin/            本体（パーサ、展開、実行エンジン、組み込み、内蔵コマンド）
bashwin/ps_emit.py  トランスパイラーの生成器（判定器を兼ねる）
bashwin/ps_runtime.ps1  生成物に埋め込む PowerShell ランタイム
dist/bashwin.pyz    単一ファイル配布物（python bashwin.pyz ... で実行）
examples/           夜間バッチの見本
tests/spec/         テストケース（#### 区切り。bash と bashwin の両方で実行する）
tests/golden/       本物の bash の出力（bash の無い環境での再生用）
tests/run_diff.py   差分テスト（bash が必要。Linux で実行）
tests/run_golden.py ゴールデン再生テスト（bash 不要。Windows 実機用）
tests/run_ps1.py    トランスパイラーの実行検証（変換 → PowerShell で実行 → golden と比較）
tests/test_ps1_static.py  トランスパイラーの静的検査（PowerShell 不要）
docs/               設計・運用・互換性・検証・代替案
```

`dist/bashwin.pyz` の作り直し:

```
python -m zipapp <bashwin フォルダだけを入れた作業フォルダ> -m "bashwin.cli:entry" -c -o dist/bashwin.pyz
```
