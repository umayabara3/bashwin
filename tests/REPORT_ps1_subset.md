# PowerShell 変換可能サブセットの実測

対象: tests/spec のテストケース 475 件(bashwin 固有・設計差異の検証用を除く)

- 変換可能サブセットに収まる: **50 件 (10.5%)**
- サブセット外(変換不可): 425 件 (89.5%)

## ファイル別

| ファイル | ケース数 | 変換可能 |
|---|---:|---:|
| 01_basic.sh | 27 | 5 |
| 02_expansion.sh | 33 | 5 |
| 03_arrays.sh | 25 | 0 |
| 04_control.sh | 29 | 9 |
| 05_functions.sh | 25 | 7 |
| 06_redir_pipe.sh | 30 | 0 |
| 07_builtins.sh | 43 | 3 |
| 08_errexit.sh | 30 | 15 |
| 09_text.sh | 33 | 0 |
| 10_files.sh | 26 | 0 |
| 11_misc.sh | 30 | 1 |
| 12_scenarios.sh | 22 | 0 |
| 13_edge.sh | 68 | 5 |
| 14_awk.sh | 17 | 0 |
| 15_scripts.sh | 7 | 0 |
| 16_scripts2.sh | 8 | 0 |
| 17_options.sh | 22 | 0 |

## 変換を妨げている要因(該当ケース数、重複あり)

| 要因 | ケース数 |
|---|---:|
| unix-tool | 223 |
| builtin | 190 |
| pipeline | 143 |
| unquoted | 102 |
| array | 59 |
| param-op | 45 |
| glob | 42 |
| heredoc | 42 |
| set-opt | 39 |
| cmdsub | 32 |
| subshell | 31 |
| stdin-redirect | 28 |
| arith | 24 |
| compound-redirect | 24 |
| special-param | 21 |
| tmpenv | 21 |
| dynamic-command | 15 |
| fd-dup | 12 |
| background | 8 |
| regex | 6 |
| test-op | 6 |
| append | 6 |
| brace | 5 |
| echo-opt | 3 |
| tilde | 1 |
| case-fallthrough | 1 |
| procsub | 1 |

## 変換可能と判定されたケース

- 01_basic.sh :: ansi-c quoting
- 01_basic.sh :: comments and line continuation
- 01_basic.sh :: echo plain
- 01_basic.sh :: semicolons and newlines
- 01_basic.sh :: single and double quotes
- 02_expansion.sh :: arithmetic with unset and strings
- 02_expansion.sh :: default values
- 02_expansion.sh :: dollar edge cases
- 02_expansion.sh :: nested expansion
- 02_expansion.sh :: quote removal in patterns
- 04_control.sh :: and-or lists
- 04_control.sh :: case basics
- 04_control.sh :: case character classes
- 04_control.sh :: case with quotes and vars
- 04_control.sh :: double bracket grouping
- 04_control.sh :: double bracket pattern quoting
- 04_control.sh :: double bracket tests
- 04_control.sh :: select-like menu with case in function
- 04_control.sh :: test builtin forms
- 05_functions.sh :: default args pattern
- 05_functions.sh :: define and call
- 05_functions.sh :: function output capture
- 05_functions.sh :: functions and exit status chains
- 05_functions.sh :: large recursion depth
- 05_functions.sh :: local shadows and dynamic scope
- 05_functions.sh :: local with command substitution status
- 07_builtins.sh :: exec replaces shell
- 07_builtins.sh :: test numeric errors
- 07_builtins.sh :: test string operators
- 08_errexit.sh :: errexit and arithmetic
- 08_errexit.sh :: errexit and-or last element
- 08_errexit.sh :: errexit function in condition is ignored
- 08_errexit.sh :: errexit in function
- 08_errexit.sh :: errexit local masks failure
- 08_errexit.sh :: errexit middle of and-or
- 08_errexit.sh :: errexit negation and compound
- 08_errexit.sh :: errexit not triggered in conditions
- 08_errexit.sh :: errexit off again
- 08_errexit.sh :: errexit stops script
- 08_errexit.sh :: errexit with command substitution assignment
- 08_errexit.sh :: error message then continue without errexit
- 08_errexit.sh :: exit in function exits script
- 08_errexit.sh :: nounset stops script
- 08_errexit.sh :: return outside function
- 11_misc.sh :: random and seconds
- 13_edge.sh :: if with complex conditions
- 13_edge.sh :: nested functions and variable scope
- 13_edge.sh :: pattern matching variety
- 13_edge.sh :: string comparison operators
- 13_edge.sh :: test with tricky strings
