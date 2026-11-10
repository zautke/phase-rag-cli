#!/usr/bin/env pwsh
# tests/live/load_negatives.ps1 -- rag-p01 live negatives on Windows (Load SPEC §9). Linux twin: load_negatives.sh
param([Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$ErrorActionPreference = 'Stop'

function Usage {
    "Usage: ./tests/live/load_negatives.ps1 [-w | --work-dir PATH] [-k | --keep] [-h | --help]"
    "Runs rag-p01 (venv python p01_load.py) live negatives: exit codes, exclusive source lock, locked destination,"
    "Ctrl-Break, junction loop, 488-char path, HIDDEN attribute, stdout closed after 10 bytes (payload > 64 KiB)."
    "  -w, --work-dir PATH  scratch root (default: TEMP\rag-load-neg-<utc>)"
    "  -k, --keep           keep the scratch root"
    "  -h, --help           show this help"
    "One PASS/FAIL line per case, then one JSON summary line. Exit 0 only when every case passes."
}
$work = $null; $keep = $false
for ($i = 0; $i -lt $Rest.Count; $i++) {
    switch -Regex ($Rest[$i]) {
        '^(-h|--help)$' { Usage; exit 0 }
        '^(-k|--keep)$' { $keep = $true }
        '^(-w|--work-dir)$' { $i++; $work = $Rest[$i] }
        default { Usage; exit 2 }
    }
}
$repo = (Resolve-Path "$PSScriptRoot/../..").Path
if (-not $work) { $work = Join-Path $env:TEMP ("rag-load-neg-" + (Get-Date -AsUTC -Format yyyyMMddTHHmmss)) }
New-Item -ItemType Directory -Force $work | Out-Null
$py = (& uv run --project $repo python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
$results = [Collections.Generic.List[object]]::new()

function B([string]$s) { [Text.Encoding]::UTF8.GetBytes($s) }
function New-Corpus([string]$name, [hashtable]$files) {
    $d = Join-Path $work $name; New-Item -ItemType Directory -Force $d | Out-Null
    foreach ($k in $files.Keys) { [IO.File]::WriteAllBytes((Join-Path $d $k), [byte[]]$files[$k]) }
    $d
}
function Start-P01([string[]]$argv) {
    $psi = [Diagnostics.ProcessStartInfo]::new($py)
    foreach ($a in @("$repo\p01_load.py") + $argv) { $psi.ArgumentList.Add($a) }
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.UseShellExecute = $false
    $psi.WorkingDirectory = $repo
    [Diagnostics.Process]::Start($psi)
}
function Invoke-P01([string[]]$argv, [int]$stopAfter = -1) {
    $sw = [Diagnostics.Stopwatch]::StartNew(); $p = Start-P01 $argv; $err = $p.StandardError.ReadToEndAsync()
    $ms = [IO.MemoryStream]::new(); $s = $p.StandardOutput.BaseStream
    if ($stopAfter -ge 0) { $buf = [byte[]]::new($stopAfter); [void]$s.Read($buf, 0, $stopAfter); $s.Close() }
    else { $s.CopyTo($ms) }
    $p.WaitForExit()
    [pscustomobject]@{ Code = $p.ExitCode; Out = $ms.ToArray(); Err = $err.Result; Ms = $sw.ElapsedMilliseconds }
}
function Check([string]$case, $r, [bool]$ok, [string]$note) {
    $results.Add([pscustomobject]@{ case = $case; pass = $ok; exit = $r.Code; wall_ms = $r.Ms; note = $note })
    "{0} {1} exit={2} wall_ms={3} {4}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $case, $r.Code, $r.Ms, $note
    if (-not $ok) { "  stderr tail: " + (($r.Err -split "`n" | Select-Object -Last 8) -join ' | ') }
}
function Art([string]$path) { [IO.File]::ReadAllText($path) | ConvertFrom-Json }
function NoTmp([string]$dir) { -not (Get-ChildItem -Force $dir -Filter '.*.tmp' -ErrorAction SilentlyContinue) }
$good = @{ 'good.md' = (B "# good`n") }

# 1. standalone exit codes (pipes hide them)
$o = "$work\x2\01.json"; $r = Invoke-P01 @('-s', "$work\no_such_dir", '-o', $o)
Check 'exit2-missing-source' $r ($r.Code -eq 2 -and $r.Out.Length -eq 0 -and -not (Test-Path $o)) 'usage error, nothing written'
$d = New-Corpus 'empty' @{}; $o = "$work\x4\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
Check 'exit4-empty-dir' $r ($r.Code -eq 4 -and -not (Test-Path $o) -and (Art "$work\x4\01.report.json").status -eq 'empty') 'report status empty'
$d = New-Corpus 'ok' $good; $o = "$work\x0\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
Check 'exit0-ok' $r ($r.Code -eq 0 -and [Linq.Enumerable]::SequenceEqual($r.Out, [IO.File]::ReadAllBytes($o))) 'stdout == artifact'
$d = New-Corpus 'partial' (@{ 'bad.txt' = [byte[]](0x61, 0xff) } + $good); $o = "$work\x3\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
Check 'exit3-partial' $r ($r.Code -eq 3 -and (Art $o).errors[0].stage -eq 'decode') 'errors[0].stage decode'
$o = "$work\x1\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o, '-M', '3')
Check 'exit1-total-cap' $r ($r.Code -eq 1 -and -not (Test-Path $o)) 'nothing loaded'

# 2. exclusive lock on a source file (FileShare.None): retried ~1.5 s, then errors[] stage open
$d = New-Corpus 'lock' (@{ 'locked.md' = (B "x") } + $good); $o = "$work\lock_out\01.json"
$fs = [IO.File]::Open("$d\locked.md", 'Open', 'Read', 'None')
try { $r = Invoke-P01 @('-s', $d, '-o', $o) } finally { $fs.Dispose() }
Check 'source-exclusive-lock' $r ($r.Code -eq 3 -and (Art $o).errors[0].stage -eq 'open' -and $r.Ms -ge 1500) 'stage open after lock retries'

# 3. destination held open without FILE_SHARE_DELETE: replace retried 2 s, exit 1, previous bytes kept, no tmp
$o = "$work\dest\01.json"; New-Item -ItemType Directory -Force "$work\dest" | Out-Null; [IO.File]::WriteAllBytes($o, (B 'previous'))
$fs = [IO.File]::Open($o, 'Open', 'Read', 'ReadWrite')
try { $r = Invoke-P01 @('-s', (New-Corpus 'dest_src' $good), '-o', $o) } finally { $fs.Dispose() }
Check 'locked-destination' $r ($r.Code -eq 1 -and [IO.File]::ReadAllText($o) -eq 'previous' -and (NoTmp "$work\dest")) 'previous artifact intact'

# 4. junction loop is skipped as a link, never followed
$d = New-Corpus 'junction' $good; New-Item -ItemType Junction -Path "$d\loop" -Target $d | Out-Null
$o = "$work\junction_out\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
$sk = (Art $o).skipped; Check 'junction-loop' $r ($r.Code -eq 0 -and $sk[0].path -eq 'loop' -and $sk[0].reason -eq 'link') 'skipped link'
[IO.Directory]::Delete("$d\loop")  # remove the link itself before any recursive cleanup

# 5. 488-character path loads (\\?\ walk root)
$d = New-Corpus 'longpath' @{}; $deep = $d; while ($deep.Length -lt 430) { $deep = Join-Path $deep ('d' * 50) }
[IO.Directory]::CreateDirectory($deep) | Out-Null; $leaf = Join-Path $deep (('f' * (487 - $deep.Length)) + '.md')
[IO.File]::WriteAllText($leaf, "# deep`n"); $o = "$work\longpath_out\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
Check 'long-path-488' $r ($r.Code -eq 0 -and $leaf.Length -ge 488 -and (Art $o).documents.Count -eq 1) "path chars=$($leaf.Length)"

# 6. HIDDEN attribute file is skipped
$d = New-Corpus 'hidden' (@{ 'h.md' = (B "h") } + $good); (Get-Item "$d\h.md").Attributes += 'Hidden'
$o = "$work\hidden_out\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o)
Check 'hidden-attribute' $r ($r.Code -eq 0 -and (Art $o).skipped[0].reason -eq 'hidden') 'skipped hidden'

# 7. reader closes stdout after 10 bytes (payload > 64 KiB): computed exit kept, artifact committed
$d = New-Corpus 'pipe' @{ 'big.txt' = (B ('x' * 200000)) }; $o = "$work\pipe_out\01.json"; $r = Invoke-P01 @('-s', $d, '-o', $o) 10
Check 'stdout-closed-early' $r ($r.Code -eq 0 -and (Test-Path $o) -and (Get-Item $o).Length -gt 65536 -and $r.Err -notmatch 'Traceback') 'exit 0, no traceback'

# 8. real Ctrl-Break during the load of a 200 MB file: exit 130, no tmp left
$d = New-Corpus 'break' @{}; $f = [IO.File]::Create("$d\huge.txt"); $chunk = B ('y' * 1MB)
for ($k = 0; $k -lt 200; $k++) { $f.Write($chunk, 0, $chunk.Length) }; $f.Dispose()
$o = "$work\break_out\01.json"; $hp = "$work\break_helper.py"
Set-Content -LiteralPath $hp -Encoding utf8 -Value @'
import os, signal, subprocess, sys, time
p = subprocess.Popen([sys.executable, *sys.argv[1:]], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)  # CTRL_BREAK targets this group only
for line in p.stderr:
    if b'load start' in line:
        break
time.sleep(0.3)
os.kill(p.pid, signal.CTRL_BREAK_EVENT)
p.stderr.read()
sys.exit(p.wait())
'@
$sw = [Diagnostics.Stopwatch]::StartNew(); & $py $hp "$repo\p01_load.py" -s $d -o $o 2>&1 | Out-Null
$r = [pscustomobject]@{ Code = $LASTEXITCODE; Err = ''; Ms = $sw.ElapsedMilliseconds }
Check 'ctrl-break' $r ($r.Code -eq 130 -and (NoTmp "$work\break_out")) 'interrupted, no tmp'

$fail = @($results | Where-Object { -not $_.pass }).Count
[ordered]@{ suite = 'load_negatives.ps1'; host = $env:COMPUTERNAME; cases = $results.Count; failed = $fail; work = $work } | ConvertTo-Json -Compress
if (-not $keep) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
exit $(if ($fail) { 1 } else { 0 })
