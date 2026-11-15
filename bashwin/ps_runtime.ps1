# ==== bashwin PowerShell runtime (embedded by `bashwin --ps1`) =================================
# Keeps the bash semantics that PowerShell lacks: case-sensitive variables, byte-exact stdout,
# exit status 0-255, dynamic scoping of `local`, errexit / nounset, glob patterns.
# Written for Windows PowerShell 5.1 (.NET Framework 4.5+); also runs on PowerShell 7.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$__win = ([System.Environment]::GetEnvironmentVariable('OS') -ceq 'Windows_NT')
$__pathmap = ([System.Environment]::GetEnvironmentVariable('BASHWIN_PATHMAP') -cne '0')
$__V = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
$__X = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
$__F = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
$__B = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
$__gcache = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
[string[]]$__P = @($args)
$__0 = [string]$PSCommandPath
$__st = 0
$__e = $false
$__u = $false
$__cd = 0
$__opened = $false
$__EX = New-Object System.Exception 'bashwin-exit'
$__frames = New-Object System.Collections.Stack
$__redirs = New-Object System.Collections.Stack
$__enc = New-Object System.Text.UTF8Encoding $false
$__encname = [string][System.Environment]::GetEnvironmentVariable('BASHWIN_ENCODING')
if ($__encname.Length -gt 0 -and $__encname -notmatch '\Autf-?8\z') {
    if ($__encname -match '\Acp([0-9]+)\z') { $__enc = [System.Text.Encoding]::GetEncoding([int]$Matches[1]) }
    else { $__enc = [System.Text.Encoding]::GetEncoding($__encname) }
}
$__stdout = [System.Console]::OpenStandardOutput()
$__stderr = [System.Console]::OpenStandardError()
$__conout = -not [System.Console]::IsOutputRedirected
$__conerr = -not [System.Console]::IsErrorRedirected
$__out = $__stdout
$__err = $__stderr

# ---- environment -> shell variables (all exported) ----
$__envd = [System.Environment]::GetEnvironmentVariables()
foreach ($__envk in @($__envd.Keys)) {
    $__envn = [string]$__envk
    if ($__win) { $__envn = $__envn.ToUpperInvariant() }
    $__V[$__envn] = [string]$__envd[$__envk]
    $__X[$__envn] = $true
}
if ($__win -and -not $__V.ContainsKey('HOME')) {
    $__envn = [string]$__V['USERPROFILE']
    if ($__envn.Length -gt 0) {
        $__V['HOME'] = $__envn.Replace('\', '/')
        $__X['HOME'] = $true
        [System.Environment]::SetEnvironmentVariable('HOME', [string]$__V['HOME'])
    }
}

# ---- working directory (.NET and PowerShell are kept in step) ----
$__origcwd = [System.Environment]::CurrentDirectory
$__startdir = (Get-Location -PSProvider FileSystem).ProviderPath
Push-Location -LiteralPath $__startdir
[System.Environment]::CurrentDirectory = $__startdir
if ($__win) { $__V['PWD'] = $__startdir.Replace('\', '/') } else { $__V['PWD'] = $__startdir }

function __cleanup {
    $script:__stdout.Flush()
    $script:__stderr.Flush()
    Pop-Location
    [System.Environment]::CurrentDirectory = $script:__origcwd
}

# ---- output ----
function __toend($stream) {
    # the same file may be open more than once (a function that logs while its caller is
    # redirected to the same log): always write at the current end of the file
    if ($stream -is [System.IO.FileStream]) { [void]$stream.Seek(0, [System.IO.SeekOrigin]::End) }
}

function __w($stream, [string]$text) {
    if ($script:__conout -and [object]::ReferenceEquals($stream, $script:__stdout)) {
        [System.Console]::Out.Write($text)
        return
    }
    if ($script:__conerr -and [object]::ReferenceEquals($stream, $script:__stderr)) {
        [System.Console]::Error.Write($text)
        return
    }
    $bytes = $script:__enc.GetBytes($text)
    __toend $stream
    $stream.Write($bytes, 0, $bytes.Length)
    if ($stream -is [System.IO.FileStream]) { $stream.Flush() }
}

function __errmsg([string]$text) {
    __w $script:__err ([System.IO.Path]::GetFileName($script:__0) + ': ' + $text + "`n")
}

function __isx($er) {
    $ex = $er.Exception
    while ($null -ne $ex) {
        if ([object]::ReferenceEquals($ex, $script:__EX)) { return $true }
        $ex = $ex.InnerException
    }
    return $false
}

function __crash($er) {
    $where = ''
    if ($null -ne $er.InvocationInfo) { $where = ' (generated line ' + $er.InvocationInfo.ScriptLineNumber + ')' }
    __w $script:__stderr ('bashwin-ps1: stopped: ' + $er.Exception.Message + $where + "`n")
    $script:__st = 70
}

function __ioerr($er) {
    $ex = $er.Exception
    while ($null -ne $ex.InnerException) { $ex = $ex.InnerException }
    if ($ex -is [System.IO.DirectoryNotFoundException] -or $ex -is [System.IO.FileNotFoundException]) {
        return 'No such file or directory'
    }
    if ($ex -is [System.UnauthorizedAccessException]) { return 'Permission denied' }
    return $ex.Message
}

# ---- paths ----
function __path([string]$text) {
    if (-not $script:__win -or -not $script:__pathmap -or $text -cnotlike '/*') { return $text }
    if ($text -ceq '/tmp' -or $text -clike '/tmp/*') {
        $tmp = [System.IO.Path]::GetTempPath().Replace('\', '/')
        if ($tmp.Length -gt 1 -and $tmp -clike '*/') { $tmp = $tmp.Substring(0, $tmp.Length - 1) }
        return ($tmp + $text.Substring(4))
    }
    if ($text -cmatch '\A/[A-Za-z](/|\z)') {
        $rest = $text.Substring(2)
        if ($rest.Length -eq 0) { $rest = '/' }
        return ($text.Substring(1, 1).ToUpperInvariant() + ':' + $rest)
    }
    return $text
}

# ---- variables ----
function __set([string]$name, [string]$val) {
    $script:__V[$name] = $val
    if ($script:__X.ContainsKey($name)) { [System.Environment]::SetEnvironmentVariable($name, $val) }
}

function __unset([string]$name) {
    $script:__V.Remove($name)
    if ($script:__X.ContainsKey($name)) {
        $script:__X.Remove($name)
        [System.Environment]::SetEnvironmentVariable($name, $null)
    }
}

function __export([string]$name) {
    $script:__X[$name] = $true
    if ($script:__V.ContainsKey($name)) {
        [System.Environment]::SetEnvironmentVariable($name, [string]$script:__V[$name])
    }
}

function __unbound([string]$name) {
    __errmsg ($name + ': unbound variable')
    $script:__st = 1
    throw $script:__EX
}

function __get([string]$name) {
    if ($name -cmatch '\A[0-9]+\z') {
        $idx = [int]$name
        if ($idx -eq 0) { return $script:__0 }
        if ($idx -le $script:__P.Length) { return $script:__P[$idx - 1] }
        if ($script:__u) { __unbound $name }
        return ''
    }
    if ($name -ceq '#') { return [string]$script:__P.Length }
    if ($name -ceq '?') { return [string]$script:__st }
    if ($script:__V.ContainsKey($name)) { return [string]$script:__V[$name] }
    if ($script:__u) { __unbound $name }
    return ''
}

function __isset([string]$name) {
    if ($name -cmatch '\A[0-9]+\z') {
        $idx = [int]$name
        return ($idx -eq 0 -or $idx -le $script:__P.Length)
    }
    if ($name -ceq '#' -or $name -ceq '?') { return $true }
    return $script:__V.ContainsKey($name)
}

function __nn([string]$name) {
    if (-not (__isset $name)) { return $false }
    $text = __get $name
    return ($text.Length -gt 0)
}

function __perr([string]$name, [string]$text) {
    if ($text.Length -eq 0) { $text = 'parameter null or not set' }
    __errmsg ($name + ': ' + $text)
    $script:__st = 1
    throw $script:__EX
}

# ---- functions: positional parameters and `local` ----
function __enter([string[]]$argv) {
    if ($null -eq $argv) { $argv = @() }
    $fr = @{}
    $fr['P'] = $script:__P
    $fr['L'] = New-Object System.Collections.ArrayList
    $fr['CD'] = $script:__cd
    $script:__frames.Push($fr)
    $script:__P = $argv
}

function __leave {
    $fr = $script:__frames.Pop()
    $saved = $fr['L']
    for ($k = $saved.Count - 1; $k -ge 0; $k--) {
        $ent = $saved[$k]
        $name = [string]$ent[0]
        if ($ent[1]) { $script:__V[$name] = [string]$ent[2] } else { $script:__V.Remove($name) }
        if ($ent[3]) {
            $script:__X[$name] = $true
            [System.Environment]::SetEnvironmentVariable($name, [string]$ent[2])
        } elseif ($script:__X.ContainsKey($name)) {
            $script:__X.Remove($name)
            [System.Environment]::SetEnvironmentVariable($name, $null)
        }
    }
    $script:__P = $fr['P']
    $script:__cd = $fr['CD']
}

function __mklocal([string]$name) {
    $fr = $script:__frames.Peek()
    foreach ($ent in $fr['L']) {
        if ([string]::Equals([string]$ent[0], $name)) { return $false }
    }
    $old = ''
    $had = $script:__V.ContainsKey($name)
    if ($had) { $old = [string]$script:__V[$name] }
    [void]$fr['L'].Add(@($name, $had, $old, $script:__X.ContainsKey($name)))
    return $true
}

function __local([string]$name) {
    if (__mklocal $name) { __unset $name }
}

function __localv([string]$name, [string]$val) {
    if (__mklocal $name) { __unset $name }
    __set $name $val
}

# ---- glob patterns (case / [[ == ]]) ----
$__cls = @{}
$__cls['alpha'] = '\p{L}'
$__cls['digit'] = '0-9'
$__cls['alnum'] = '\p{L}0-9'
$__cls['upper'] = '\p{Lu}'
$__cls['lower'] = '\p{Ll}'
$__cls['space'] = '\s'
$__cls['blank'] = ' \t'
$__cls['xdigit'] = '0-9A-Fa-f'
$__cls['punct'] = '!-/:-@\[-`{-~'

function __gq([string]$text) {
    return [regex]::Replace($text, '[\\*?\[\]]', '\$0')
}

function __gclass([string]$body) {
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('[')
    $k = 0
    $n = $body.Length
    if ($n -gt 0 -and ($body.Substring(0, 1) -ceq '!' -or $body.Substring(0, 1) -ceq '^')) {
        [void]$sb.Append('^')
        $k = 1
    }
    while ($k -lt $n) {
        $c = $body.Substring($k, 1)
        if ($c -ceq '[' -and ($k + 1) -lt $n -and $body.Substring($k + 1, 1) -ceq ':') {
            $q = $body.IndexOf(':]', $k + 2, [System.StringComparison]::Ordinal)
            if ($q -ge 0) {
                $cname = $body.Substring($k + 2, $q - $k - 2)
                if (-not $script:__cls.ContainsKey($cname)) {
                    throw ('unsupported character class [:' + $cname + ':] in a pattern')
                }
                [void]$sb.Append([string]$script:__cls[$cname])
                $k = $q + 2
                continue
            }
        }
        $escaped = $false
        if ($c -ceq '\' -and ($k + 1) -lt $n) {
            $k++
            $c = $body.Substring($k, 1)
            $escaped = $true
        }
        if ($c -cmatch '[\\\]\[\^]' -or ($escaped -and $c -ceq '-')) { [void]$sb.Append('\') }
        [void]$sb.Append($c)
        $k++
    }
    [void]$sb.Append(']')
    return $sb.ToString()
}

function __g2r([string]$pat) {
    if ($script:__gcache.ContainsKey($pat)) { return [string]$script:__gcache[$pat] }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('\A(?s:')
    $n = $pat.Length
    $k = 0
    while ($k -lt $n) {
        $c = $pat.Substring($k, 1)
        $k++
        if ($c -ceq '*') { [void]$sb.Append('.*') }
        elseif ($c -ceq '?') { [void]$sb.Append('.') }
        elseif ($c -ceq '\') {
            if ($k -lt $n) {
                [void]$sb.Append([regex]::Escape($pat.Substring($k, 1)))
                $k++
            } else {
                [void]$sb.Append('\\')
            }
        }
        elseif ($c -ceq '[') {
            $j = $k
            if ($j -lt $n -and ($pat.Substring($j, 1) -ceq '!' -or $pat.Substring($j, 1) -ceq '^')) { $j++ }
            if ($j -lt $n -and $pat.Substring($j, 1) -ceq ']') { $j++ }
            while ($j -lt $n -and $pat.Substring($j, 1) -cne ']') {
                $d = $pat.Substring($j, 1)
                if ($d -ceq '[' -and ($j + 1) -lt $n -and $pat.Substring($j + 1, 1) -ceq ':') {
                    $q = $pat.IndexOf(':]', $j + 2, [System.StringComparison]::Ordinal)
                    if ($q -ge 0) { $j = $q + 1 }
                } elseif ($d -ceq '\' -and ($j + 1) -lt $n) {
                    $j++
                }
                $j++
            }
            if ($j -ge $n) {
                [void]$sb.Append('\[')
            } else {
                $body = $pat.Substring($k, $j - $k)
                [void]$sb.Append((__gclass $body))
                $k = $j + 1
            }
        }
        else { [void]$sb.Append([regex]::Escape($c)) }
    }
    [void]$sb.Append(')\z')
    $re = $sb.ToString()
    $script:__gcache[$pat] = $re
    return $re
}

function __m([string]$text, [string]$pat) {
    return [regex]::IsMatch($text, (__g2r $pat))
}

# ---- arithmetic (64-bit integers) ----
function __aerr([string]$text) {
    __errmsg $text
    $script:__st = 1
    throw $script:__EX
}

function __intlit([string]$text) {
    # decimal / octal (leading 0) / hex (0x) integer literal -> Int64; $null when it is not one
    $t = $text.Trim()
    $neg = $false
    if ($t -cmatch '\A[+-]') {
        $neg = ($t.Substring(0, 1) -ceq '-')
        $t = $t.Substring(1)
    }
    $r = $null
    if ($t -cmatch '\A0[xX][0-9a-fA-F]+\z') { $r = [System.Convert]::ToInt64($t.Substring(2), 16) }
    elseif ($t -cmatch '\A0[0-9]+\z') {
        if ($t -cnotmatch '\A[0-7]+\z') { __aerr ($text + ': value too great for base') }
        $r = [System.Convert]::ToInt64($t, 8)
    }
    elseif ($t -cmatch '\A[0-9]+\z') { $r = [long]::Parse($t, [System.Globalization.CultureInfo]::InvariantCulture) }
    else { return $null }
    if ($neg) { return (-$r) }
    return $r
}

function __num([string]$text, [int]$depth) {
    # the value of a variable used inside (( )) or [[ -eq ]]
    $t = $text.Trim()
    if ($t.Length -eq 0) { return 0L }
    $r = __intlit $t
    if ($null -ne $r) { return $r }
    if ($t -cmatch '\A[A-Za-z_][A-Za-z0-9_]*\z') {
        if ($depth -gt 100) { __aerr ($text + ': expression recursion level exceeded') }
        if (-not $script:__V.ContainsKey($t)) {
            if ($script:__u) { __unbound $t }
            return 0L
        }
        return (__num ([string]$script:__V[$t]) ($depth + 1))
    }
    throw ('arithmetic on a value that is not a plain integer is not supported: "' + $text + '"')
}

function __vn([string]$name) {
    if (-not $script:__V.ContainsKey($name)) {
        if ($script:__u) { __unbound $name }
        return 0L
    }
    return (__num ([string]$script:__V[$name]) 0)
}

function __si([string]$text) {
    # `$x` written inside $(( )): bash substitutes the text; only a plain integer is accepted here
    $r = __intlit $text
    if ($null -eq $r) {
        throw ('`$var` inside $(( )) must hold a plain integer here (got "' + $text + '"); write the variable without `$`')
    }
    return $r
}

function __div([long]$x, [long]$y) {
    if ($y -eq 0) { __aerr 'division by 0' }
    return [long][System.Math]::Truncate([decimal]$x / [decimal]$y)
}

function __mod([long]$x, [long]$y) {
    if ($y -eq 0) { __aerr 'division by 0' }
    return ($x % $y)
}

function __aset([string]$name, [long]$val) {
    __set $name ([string]$val)
    return $val
}

function __ainc([string]$name, [long]$delta, [bool]$post) {
    $old = __vn $name
    $new = $old + $delta
    __set $name ([string]$new)
    if ($post) { return $old }
    return $new
}

# ---- test / [ ] ----
$__tbin = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
foreach ($__envn in @('=', '==', '!=', '<', '>', '-eq', '-ne', '-lt', '-le', '-gt', '-ge', '-nt', '-ot', '-ef')) {
    $__tbin[$__envn] = $true
}
[string[]]$__ta = @()
$__ti = 0

function __tint([string]$text) {
    $r = 0L
    $ok = [long]::TryParse($text.Trim(), [System.Globalization.NumberStyles]::AllowLeadingSign,
        [System.Globalization.CultureInfo]::InvariantCulture, [ref]$r)
    if (-not $ok) { throw ('bw-test:' + $text + ': integer expression expected') }
    return $r
}

function __tunary([string]$op, [string]$text) {
    if ($op -ceq '-z') { return ($text.Length -eq 0) }
    if ($op -ceq '-n') { return ($text.Length -gt 0) }
    if ($op -cnotmatch '\A-[aedfsrw]\z') { throw ('test ' + $op + ' is not supported by the PowerShell runtime') }
    if ($text.Length -eq 0) { return $false }
    $full = __path $text
    $isfile = [System.IO.File]::Exists($full)
    $isdir = [System.IO.Directory]::Exists($full)
    if ($op -ceq '-f') { return $isfile }
    if ($op -ceq '-d') { return $isdir }
    if ($op -ceq '-s') {
        if ($isdir) { return $true }
        if (-not $isfile) { return $false }
        return ((New-Object System.IO.FileInfo $full).Length -gt 0)
    }
    if ($op -ceq '-w') {
        if ($isdir) { return $true }
        if (-not $isfile) { return $false }
        return (-not (New-Object System.IO.FileInfo $full).IsReadOnly)
    }
    return ($isfile -or $isdir)
}

function __tbinary([string]$op, [string]$x, [string]$y) {
    if ($op -ceq '=' -or $op -ceq '==') { return [string]::Equals($x, $y) }
    if ($op -ceq '!=') { return (-not [string]::Equals($x, $y)) }
    if ($op -ceq '<') { return ([string]::CompareOrdinal($x, $y) -lt 0) }
    if ($op -ceq '>') { return ([string]::CompareOrdinal($x, $y) -gt 0) }
    if ($op -cnotmatch '\A-(eq|ne|lt|le|gt|ge)\z') { throw ('test ' + $op + ' is not supported by the PowerShell runtime') }
    $p = __tint $x
    $q = __tint $y
    if ($op -ceq '-eq') { return ($p -eq $q) }
    if ($op -ceq '-ne') { return ($p -ne $q) }
    if ($op -ceq '-lt') { return ($p -lt $q) }
    if ($op -ceq '-le') { return ($p -le $q) }
    if ($op -ceq '-gt') { return ($p -gt $q) }
    return ($p -ge $q)
}

function __tpeek([int]$ahead) {
    $k = $script:__ti + $ahead
    if ($k -lt $script:__ta.Length) { return $script:__ta[$k] }
    return $null
}

function __tor {
    $r = __tand
    while ((__tpeek 0) -ceq '-o') {
        $script:__ti++
        $r2 = __tand
        $r = ($r -or $r2)
    }
    return $r
}

function __tand {
    $r = __tnot
    while ((__tpeek 0) -ceq '-a') {
        $script:__ti++
        $r2 = __tnot
        $r = ($r -and $r2)
    }
    return $r
}

function __tnot {
    if ((__tpeek 0) -ceq '!' -and $null -ne (__tpeek 1)) {
        $script:__ti++
        $r = __tnot
        return (-not $r)
    }
    $r = __tprim
    return $r
}

function __tprim {
    $t = __tpeek 0
    if ($null -eq $t) { throw 'bw-test:argument expected' }
    $script:__ti++
    if ($t -ceq '(' -and $null -ne (__tpeek 0)) {
        $r = __tor
        if ((__tpeek 0) -cne ')') { throw "bw-test:``)' expected" }
        $script:__ti++
        return $r
    }
    $n1 = __tpeek 0
    $n2 = __tpeek 1
    if ($null -ne $n1 -and $null -ne $n2 -and $script:__tbin.ContainsKey($n1)) {
        $script:__ti += 2
        return (__tbinary $n1 $t $n2)
    }
    if ($null -ne $n1 -and $t -cmatch '\A-[abcdefghknoprstuvwxzGLNOS]\z') {
        $script:__ti++
        return (__tunary $t $n1)
    }
    return ($t.Length -gt 0)
}

function __test([string[]]$a) {
    if ($null -eq $a) { return $false }
    $n = $a.Length
    if ($n -eq 0) { return $false }
    if ($n -eq 1) { return ($a[0].Length -gt 0) }
    if ($n -eq 2) {
        if ($a[0] -ceq '!') { return ($a[1].Length -eq 0) }
        if ($a[0] -cmatch '\A-[abcdefghknoprstuvwxzGLNOS]\z') {
            $r = __tunary $a[0] $a[1]
            return $r
        }
        throw ('bw-test:' + $a[0] + ': unary operator expected')
    }
    if ($n -eq 3) {
        if ($script:__tbin.ContainsKey($a[1])) {
            $r = __tbinary $a[1] $a[0] $a[2]
            return $r
        }
        if ($a[1] -ceq '-a') { return ($a[0].Length -gt 0 -and $a[2].Length -gt 0) }
        if ($a[1] -ceq '-o') { return ($a[0].Length -gt 0 -or $a[2].Length -gt 0) }
        if ($a[0] -ceq '!') {
            $r = __test @($a[1], $a[2])
            return (-not $r)
        }
        if ($a[0] -ceq '(' -and $a[2] -ceq ')') { return ($a[1].Length -gt 0) }
        throw ('bw-test:' + $a[1] + ': binary operator expected')
    }
    if ($n -eq 4 -and $a[0] -ceq '!') {
        $r = __test @($a[1], $a[2], $a[3])
        return (-not $r)
    }
    $script:__ta = $a
    $script:__ti = 0
    $r = __tor
    if ($script:__ti -ne $n) { throw 'bw-test:too many arguments' }
    return $r
}

function __b_test([string[]]$a, [bool]$bracket) {
    if ($null -eq $a) { $a = @() }
    if ($bracket) {
        if ($a.Length -eq 0 -or $a[$a.Length - 1] -cne ']') {
            __errmsg "[: missing ``]'"
            $script:__st = 2
            return
        }
        if ($a.Length -eq 1) { $a = @() } else { $a = $a[0..($a.Length - 2)] }
    }
    try {
        $r = __test $a
        if ($r) { $script:__st = 0 } else { $script:__st = 1 }
    } catch {
        $text = [string]$_.Exception.Message
        if ($text -clike 'bw-test:*') {
            __errmsg ('test: ' + $text.Substring(8))
            $script:__st = 2
        } else {
            throw
        }
    }
}

# ---- builtins ----
function __b_echo([string[]]$a) {
    if ($null -eq $a) { $a = @() }
    $nl = $true
    $esc = $false
    $k = 0
    while ($k -lt $a.Length -and $a[$k] -cmatch '\A-[neE]+\z') {
        foreach ($ch in $a[$k].Substring(1).ToCharArray()) {
            $c = [string]$ch
            if ($c -ceq 'n') { $nl = $false } elseif ($c -ceq 'e') { $esc = $true } else { $esc = $false }
        }
        $k++
    }
    if ($esc) { throw 'echo -e (escape processing) is not supported by the PowerShell runtime' }
    $text = ''
    if ($k -lt $a.Length) { $text = ($a[$k..($a.Length - 1)] -join ' ') }
    if ($nl) { $text = $text + "`n" }
    __w $script:__out $text
    $script:__st = 0
}

function __statusarg([string[]]$a, [string]$who) {
    if ($null -eq $a -or $a.Length -eq 0) { return $script:__st }
    $r = 0L
    $ok = [long]::TryParse($a[0].Trim(), [System.Globalization.NumberStyles]::AllowLeadingSign,
        [System.Globalization.CultureInfo]::InvariantCulture, [ref]$r)
    if (-not $ok) {
        __errmsg ($who + ': ' + $a[0] + ': numeric argument required')
        return 2
    }
    return [int]($r -band 255)
}

function __b_exit([string[]]$a) {
    $script:__st = __statusarg $a 'exit'
    throw $script:__EX
}

function __b_shift([string[]]$a) {
    $cnt = 1
    if ($null -ne $a -and $a.Length -gt 0) {
        $r = 0L
        $ok = [long]::TryParse($a[0].Trim(), [System.Globalization.NumberStyles]::AllowLeadingSign,
            [System.Globalization.CultureInfo]::InvariantCulture, [ref]$r)
        if (-not $ok) {
            __errmsg ('shift: ' + $a[0] + ': numeric argument required')
            $script:__st = 1
            return
        }
        if ($r -lt 0 -or $r -gt $script:__P.Length) { $script:__st = 1; return }
        $cnt = [int]$r
    }
    $len = $script:__P.Length
    if ($cnt -gt $len) { $script:__st = 1; return }
    if ($cnt -eq $len) { $script:__P = @() }
    elseif ($cnt -gt 0) { $script:__P = $script:__P[$cnt..($len - 1)] }
    $script:__st = 0
}

function __b_unset([string[]]$a) {
    if ($null -eq $a) { $a = @() }
    foreach ($name in $a) {
        if ($name -ceq '-v') { continue }
        if ($name -clike '-*') { throw ('unset ' + $name + ' is not supported by the PowerShell runtime') }
        __unset $name
    }
    $script:__st = 0
}

function __setcwd([string]$full) {
    Set-Location -LiteralPath $full
    $now = (Get-Location -PSProvider FileSystem).ProviderPath
    [System.Environment]::CurrentDirectory = $now
    $old = [string]$script:__V['PWD']
    if ($script:__win) { $now = $now.Replace('\', '/') }
    __set 'OLDPWD' $old
    __set 'PWD' $now
}

function __b_cd([string[]]$a) {
    if ($null -eq $a) { $a = @() }
    $print = $false
    if ($a.Length -gt 1) {
        __errmsg 'cd: too many arguments'
        $script:__st = 1
        return
    }
    if ($a.Length -eq 0) {
        $target = [string]$script:__V['HOME']
        if ($target.Length -eq 0) { __errmsg 'cd: HOME not set'; $script:__st = 1; return }
    } elseif ($a[0] -ceq '-') {
        $target = [string]$script:__V['OLDPWD']
        if ($target.Length -eq 0) { __errmsg 'cd: OLDPWD not set'; $script:__st = 1; return }
        $print = $true
    } else {
        $target = $a[0]
    }
    $full = __path $target
    if ($full.Length -eq 0 -or -not [System.IO.Directory]::Exists($full)) {
        __errmsg ('cd: ' + $target + ': No such file or directory')
        $script:__st = 1
        return
    }
    try {
        __setcwd ([System.IO.Path]::GetFullPath($full))
    } catch {
        if (__isx $_) { throw }
        __errmsg ('cd: ' + $target + ': ' + (__ioerr $_))
        $script:__st = 1
        return
    }
    if ($print) { __w $script:__out ([string]$script:__V['PWD'] + "`n") }
    $script:__st = 0
}

function __b_pwd {
    __w $script:__out ([string]$script:__V['PWD'] + "`n")
    $script:__st = 0
}

function __ck {
    if ($script:__st -ne 0 -and $script:__e -and $script:__cd -eq 0) { throw $script:__EX }
}

# ---- redirections (stdout / stderr only) ----
function __open([string]$target, [bool]$append) {
    $script:__opened = $false
    if ($target -ceq '/dev/null') { return [System.IO.Stream]::Null }
    if ($script:__win -and $target -ieq 'NUL') { return [System.IO.Stream]::Null }
    if ($target -ceq '/dev/stdout') { return $script:__out }
    if ($target -ceq '/dev/stderr') { return $script:__err }
    $full = __path $target
    if ($append) { $mode = [System.IO.FileMode]::Append } else { $mode = [System.IO.FileMode]::Create }
    try {
        $fs = New-Object System.IO.FileStream($full, $mode, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
    } catch {
        __errmsg ($target + ': ' + (__ioerr $_))
        return $null
    }
    $script:__opened = $true
    return $fs
}

function __rpush([string[]]$spec) {
    $fr = @{}
    $fr['O'] = $script:__out
    $fr['E'] = $script:__err
    $fr['S'] = New-Object System.Collections.ArrayList
    $script:__redirs.Push($fr)
    for ($k = 0; $k -lt $spec.Length; $k += 3) {
        $fd = $spec[$k]
        $op = $spec[$k + 1]
        $target = $spec[$k + 2]
        if ($op -ceq 'd') {
            if ($fd -ceq '2') { $script:__err = $script:__out } else { $script:__out = $script:__err }
            continue
        }
        $s = __open $target ($op -ceq 'a' -or $op -ceq 'ba')
        if ($null -eq $s) {
            __rpop
            $script:__st = 1
            return $false
        }
        if ($script:__opened) { [void]$fr['S'].Add($s) }
        if ($op -ceq 'b' -or $op -ceq 'ba') {
            $script:__out = $s
            $script:__err = $s
        } elseif ($fd -ceq '2') {
            $script:__err = $s
        } else {
            $script:__out = $s
        }
    }
    return $true
}

function __rpop {
    $fr = $script:__redirs.Pop()
    $script:__out = $fr['O']
    $script:__err = $fr['E']
    foreach ($s in $fr['S']) { $s.Dispose() }
}

# ---- command substitution: runs in a copy of the shell state ----
function __copytable($table) {
    $copy = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
    foreach ($key in @($table.Keys)) { $copy[$key] = $table[$key] }
    return ,$copy
}

function __cs([scriptblock]$body) {
    $snapV = __copytable $script:__V
    $snapX = __copytable $script:__X
    $snapF = __copytable $script:__F
    $snapP = $script:__P
    $snapE = $script:__e
    $snapU = $script:__u
    $snapCD = $script:__cd
    $snapDir = [System.Environment]::CurrentDirectory
    $oldOut = $script:__out
    $ms = New-Object System.IO.MemoryStream
    $script:__out = $ms
    $script:__e = $false
    try {
        $null = & $body
    } catch {
        if (-not (__isx $_)) { throw }
    } finally {
        $script:__out = $oldOut
        foreach ($key in @($script:__X.Keys)) {
            if (-not $snapX.ContainsKey($key)) { [System.Environment]::SetEnvironmentVariable([string]$key, $null) }
        }
        foreach ($key in @($snapX.Keys)) {
            if ($snapV.ContainsKey($key)) {
                [System.Environment]::SetEnvironmentVariable([string]$key, [string]$snapV[$key])
            } else {
                [System.Environment]::SetEnvironmentVariable([string]$key, $null)
            }
        }
        $script:__V = $snapV
        $script:__X = $snapX
        $script:__F = $snapF
        $script:__P = $snapP
        $script:__e = $snapE
        $script:__u = $snapU
        $script:__cd = $snapCD
        if (-not [string]::Equals($snapDir, [System.Environment]::CurrentDirectory)) {
            Set-Location -LiteralPath $snapDir
            [System.Environment]::CurrentDirectory = $snapDir
        }
    }
    $text = $script:__enc.GetString($ms.ToArray())
    if ($text.IndexOf([char]0) -ge 0) { $text = $text.Replace([string][char]0, '') }
    if ($script:__win) { $text = $text.Replace("`r`n", "`n") }
    return $text.TrimEnd([char]10)
}

# ---- external commands ----
function __qa([string]$text) {
    if ($text.Length -gt 0 -and $text -notmatch '[\s"]') { return $text }
    $q = [regex]::Replace($text, '(\\*)"', '$1$1\"')
    $q = [regex]::Replace($q, '(\\+)\z', '$1$1')
    return ('"' + $q + '"')
}

function __norm([int]$rc) {
    if ($rc -ge 0 -and $rc -le 255) { return $rc }
    if ($rc -lt 0 -and -not $script:__win) { return (128 - $rc) }
    $low = $rc -band 255
    if ($low -eq 0) { return 255 }
    return $low
}

function __find([string]$name) {
    if ($name.Length -eq 0) { return $null }
    if ($name.Contains('/') -or ($script:__win -and $name.Contains('\'))) {
        $base = __path $name
        $cands = @($base)
        if ($script:__win) {
            $exts = @('.com', '.exe', '.bat', '.cmd')
            if ([System.IO.Path]::GetExtension($base).Length -gt 0) {
                foreach ($x in $exts) { $cands += ($base + $x) }
            } else {
                $cands = @()
                foreach ($x in $exts) { $cands += ($base + $x) }
                $cands += $base
            }
        }
        foreach ($cand in $cands) {
            if ([System.IO.File]::Exists($cand)) { return [System.IO.Path]::GetFullPath($cand) }
        }
        return $null
    }
    $pat = [System.Management.Automation.WildcardPattern]::Escape($name)
    $found = @(Get-Command -CommandType Application -Name $pat -ErrorAction SilentlyContinue)
    if ($found.Length -eq 0) { return $null }
    return [string]$found[0].Path
}

function __ext([string[]]$argv) {
    $exe = __find $argv[0]
    if ($null -eq $exe) {
        __errmsg ($argv[0] + ': command not found')
        $script:__st = 127
        return
    }
    $rest = @()
    for ($k = 1; $k -lt $argv.Length; $k++) { $rest += (__qa $argv[$k]) }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = [System.Environment]::CurrentDirectory
    $suffix = [System.IO.Path]::GetExtension($exe).ToLowerInvariant()
    if ($script:__win -and ($suffix -ceq '.cmd' -or $suffix -ceq '.bat')) {
        $comspec = [string]$script:__V['COMSPEC']
        if ($comspec.Length -eq 0) { $comspec = 'cmd.exe' }
        $psi.FileName = $comspec
        $psi.Arguments = '/d /s /c "' + ((@(__qa $exe) + $rest) -join ' ') + '"'
    } elseif ($script:__win -and $suffix -ceq '.ps1') {
        $psi.FileName = 'powershell.exe'
        $psi.Arguments = ((@('-NoProfile', '-NonInteractive', '-File', (__qa $exe)) + $rest) -join ' ')
    } else {
        $psi.FileName = $exe
        $psi.Arguments = ($rest -join ' ')
    }
    $capOut = -not [object]::ReferenceEquals($script:__out, $script:__stdout)
    $capErr = -not [object]::ReferenceEquals($script:__err, $script:__stderr)
    $psi.RedirectStandardOutput = $capOut
    $psi.RedirectStandardError = $capErr
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        [void]$proc.Start()
    } catch {
        __errmsg ($argv[0] + ': cannot execute: ' + (__ioerr $_))
        $script:__st = 126
        return
    }
    if ($capOut) { __toend $script:__out }
    if ($capErr) { __toend $script:__err }
    if ($capOut -and $capErr) {
        # two pipes: stderr is drained in the background so neither side can block
        if ([object]::ReferenceEquals($script:__out, $script:__err)) {
            $buf = New-Object System.IO.MemoryStream
            $task = $proc.StandardError.BaseStream.CopyToAsync($buf)
            $proc.StandardOutput.BaseStream.CopyTo($script:__out)
            $task.Wait()
            $buf.WriteTo($script:__out)
        } else {
            $task = $proc.StandardError.BaseStream.CopyToAsync($script:__err)
            $proc.StandardOutput.BaseStream.CopyTo($script:__out)
            $task.Wait()
        }
    } elseif ($capOut) {
        $proc.StandardOutput.BaseStream.CopyTo($script:__out)
    } elseif ($capErr) {
        $proc.StandardError.BaseStream.CopyTo($script:__err)
    }
    $proc.WaitForExit()
    if ($capOut) { $script:__out.Flush() }
    if ($capErr) { $script:__err.Flush() }
    $rc = $proc.ExitCode
    $proc.Dispose()
    $script:__st = __norm $rc
}

# ---- dispatch for names decided at run time: function -> builtin -> external command ----
$__B['echo'] = { param([string[]]$a) __b_echo $a }
$__B[':'] = { param([string[]]$a) $script:__st = 0 }
$__B['true'] = { param([string[]]$a) $script:__st = 0 }
$__B['false'] = { param([string[]]$a) $script:__st = 1 }
$__B['cd'] = { param([string[]]$a) __b_cd $a }
$__B['pwd'] = { param([string[]]$a) __b_pwd }
$__B['test'] = { param([string[]]$a) __b_test $a $false }
$__B['['] = { param([string[]]$a) __b_test $a $true }
$__B['exit'] = { param([string[]]$a) __b_exit $a }
$__B['shift'] = { param([string[]]$a) __b_shift $a }
$__B['unset'] = { param([string[]]$a) __b_unset $a }
$__nodyn = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
foreach ($__envn in @('alias', 'bg', 'bind', 'break', 'builtin', 'caller', 'command', 'compgen', 'complete',
        'continue', 'declare', 'dirs', 'disown', 'enable', 'eval', 'exec', 'export', 'fc', 'fg', 'getopts',
        'hash', 'help', 'history', 'jobs', 'kill', 'let', 'local', 'logout', 'mapfile', 'popd', 'printf',
        'pushd', 'read', 'readarray', 'readonly', 'return', 'set', 'shopt', 'source', '.', 'suspend',
        'times', 'trap', 'type', 'typeset', 'ulimit', 'umask', 'unalias', 'wait')) {
    $__nodyn[$__envn] = $true
}

function __run([string[]]$argv) {
    $name = $argv[0]
    [string[]]$rest = @()
    if ($argv.Length -gt 1) { $rest = $argv[1..($argv.Length - 1)] }
    if ($script:__F.ContainsKey($name)) {
        $fn = $script:__F[$name]
        & $fn $rest
        return
    }
    if ($script:__B.ContainsKey($name)) {
        $fn = $script:__B[$name]
        & $fn $rest
        return
    }
    if ($script:__nodyn.ContainsKey($name)) {
        throw ('the builtin `' + $name + '` cannot be called through a variable in the PowerShell runtime')
    }
    __ext $argv
}
# ==== end of runtime ==========================================================================
