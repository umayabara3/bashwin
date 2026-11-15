# PowerShell 変換可能サブセットの実測

対象: tests/spec のテストケース 494 件(bashwin 固有・設計差異の検証用を除く)

- 変換可能サブセットに収まる: **72 件 (14.6%)**
- サブセット外(変換不可): 422 件 (85.4%)

## ファイル別

| ファイル | ケース数 | 変換可能 |
|---|---:|---:|
| 01_basic.sh | 27 | 5 |
| 02_expansion.sh | 33 | 7 |
| 03_arrays.sh | 25 | 0 |
| 04_control.sh | 29 | 9 |
| 05_functions.sh | 25 | 9 |
| 06_redir_pipe.sh | 30 | 0 |
| 07_builtins.sh | 43 | 2 |
| 08_errexit.sh | 33 | 16 |
| 09_text.sh | 33 | 0 |
| 10_files.sh | 26 | 0 |
| 11_misc.sh | 30 | 0 |
| 12_scenarios.sh | 22 | 0 |
| 13_edge.sh | 68 | 8 |
| 14_awk.sh | 17 | 0 |
| 15_scripts.sh | 7 | 0 |
| 16_scripts2.sh | 8 | 0 |
| 17_options.sh | 22 | 0 |
| 18_ps1_subset.sh | 16 | 16 |

## 変換を妨げている要因(該当ケース数、重複あり)

| 要因 | ケース数 |
|---|---:|
| unix-tool | 222 |
| builtin | 198 |
| pipeline | 143 |
| unquoted | 97 |
| array | 59 |
| stdin-redirect | 43 |
| heredoc | 42 |
| param-op | 36 |
| subshell | 32 |
| special-param | 21 |
| tmpenv | 21 |
| arith | 20 |
| glob | 13 |
| special-var | 9 |
| background | 8 |
| regex | 6 |
| append | 6 |
| set-opt | 5 |
| test-op | 5 |
| echo-opt | 3 |
| fd | 3 |
| brace | 2 |
| case-fallthrough | 1 |
| return | 1 |

## 変換可能と判定されたケース

- 01_basic.sh :: ansi-c quoting
- 01_basic.sh :: comments and line continuation
- 01_basic.sh :: echo plain
- 01_basic.sh :: semicolons and newlines
- 01_basic.sh :: single and double quotes
- 02_expansion.sh :: alternate value
- 02_expansion.sh :: arithmetic with unset and strings
- 02_expansion.sh :: assign default
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
- 05_functions.sh :: early return and cleanup pattern
- 05_functions.sh :: function output capture
- 05_functions.sh :: functions and exit status chains
- 05_functions.sh :: large recursion depth
- 05_functions.sh :: local shadows and dynamic scope
- 05_functions.sh :: local with command substitution status
- 05_functions.sh :: return values
- 07_builtins.sh :: test numeric errors
- 07_builtins.sh :: test string operators
- 08_errexit.sh :: command not found status
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
- 08_errexit.sh :: exit inside command substitution
- 08_errexit.sh :: nounset stops script
- 13_edge.sh :: arithmetic division by zero
- 13_edge.sh :: arithmetic with spaces and newlines
- 13_edge.sh :: if with complex conditions
- 13_edge.sh :: integer comparisons with leading zeros and negatives
- 13_edge.sh :: nested functions and variable scope
- 13_edge.sh :: pattern matching variety
- 13_edge.sh :: string comparison operators
- 13_edge.sh :: test with tricky strings
- 18_ps1_subset.sh :: ps1 case patterns classes and quoting
- 18_ps1_subset.sh :: ps1 cd changes the directory of child processes
- 18_ps1_subset.sh :: ps1 command substitution of an external command
- 18_ps1_subset.sh :: ps1 environment export and unset reach child processes
- 18_ps1_subset.sh :: ps1 errexit with external commands
- 18_ps1_subset.sh :: ps1 external command arguments are passed exactly
- 18_ps1_subset.sh :: ps1 external exit status and conditions
- 18_ps1_subset.sh :: ps1 functions return values recursion and dynamic dispatch
- 18_ps1_subset.sh :: ps1 loops break continue and c-style for
- 18_ps1_subset.sh :: ps1 nounset with positional parameters and defaults
- 18_ps1_subset.sh :: ps1 output bytes are exact
- 18_ps1_subset.sh :: ps1 parameter defaults and error exit
- 18_ps1_subset.sh :: ps1 positional parameters set shift and at
- 18_ps1_subset.sh :: ps1 redirect external and builtin output to files
- 18_ps1_subset.sh :: ps1 stderr redirections
- 18_ps1_subset.sh :: ps1 tilde home and string tests
