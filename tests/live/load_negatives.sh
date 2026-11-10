#!/usr/bin/env bash
# tests/live/load_negatives.sh -- rag-p01 live negatives on Linux (Load SPEC §9). Windows twin: load_negatives.ps1
# SHARED cases (same names in both twins): exit2-missing-source exit4-empty-dir exit0-ok exit3-partial
#   exit1-total-cap unreadable-file unreadable-last-dir link-loop long-path-488 dot-file-hidden
#   stdout-closed-early interrupt
# LINUX-ONLY: fifo undecodable-name interrupt-sigterm
# On adagio run it under WSL from the PowerShell tool, with a Linux venv:
#   wsl -d Ubuntu-24.04 --exec bash -lc "cd /mnt/c/.../phase-rag-cli-wt-feat && UV_PROJECT_ENVIRONMENT=~/.venvs/prc ./tests/live/load_negatives.sh"
set -uo pipefail

Usage() {
    echo "Usage: ./tests/live/load_negatives.sh [-w | --work-dir PATH] [-k | --keep] [-h | --help]"
    echo "Runs rag-p01 (venv python p01_load.py) live negatives: the shared cases above (chmod 000 file and last"
    echo "directory, symlink loop, 'p01 | head -c 10' with a payload > 64 KiB, SIGINT) plus FIFO, undecodable name, SIGTERM."
    echo "  -w, --work-dir PATH  scratch root (default: \${TMPDIR:-/tmp}/rag-load-neg-<utc>)"
    echo "  -k, --keep           keep the scratch root"
    echo "  -h, --help           show this help"
    echo "One PASS/FAIL line per case, then one JSON summary line. Exit 0 only when every case passes."
}
work=""; keep=0
while (($#)); do
    case "$1" in
        -h|--help) Usage; exit 0 ;;
        -k|--keep) keep=1 ;;
        -w|--work-dir) shift; (($#)) || { Usage; exit 2; }; work="$1" ;;
        *) Usage; exit 2 ;;
    esac
    shift
done
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$repo" == /mnt/* && -z "${UV_PROJECT_ENVIRONMENT:-}" ]]; then  # WSL on a Windows checkout
    echo "error: set UV_PROJECT_ENVIRONMENT to a Linux venv path; $repo/.venv belongs to Windows" >&2
    exit 2
fi
work="${work:-${TMPDIR:-/tmp}/rag-load-neg-$(date -u +%Y%m%dT%H%M%S)}"
mkdir -p "$work"
py="$(uv run --project "$repo" python -c 'import sys; print(sys.executable)' | tail -n 1)"
cases=0; failed=0

p01() { "$py" "$repo/p01_load.py" "$@"; }
field() { "$py" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print(eval(sys.argv[2]))' "$1" "$2"; }
corpus() { local d="$work/$1"; mkdir -p "$d"; printf '# good\n' > "$d/good.md"; echo "$d"; }
check() {  # check CASE EXIT WALL_MS OK NOTE
    cases=$((cases + 1))
    if [[ "$4" == 1 ]]; then echo "PASS $1 exit=$2 wall_ms=$3 $5"
    else failed=$((failed + 1)); echo "FAIL $1 exit=$2 wall_ms=$3 $5"; tail -n 8 "$work/err.txt" 2>/dev/null | sed 's/^/  stderr: /'; fi
}
run() {  # run OUT ARGS... -> sets code, ms; stdout -> $work/out.bin, stderr -> $work/err.txt
    local t0; t0=$(date +%s%3N)
    p01 "$@" > "$work/out.bin" 2> "$work/err.txt"; code=$?
    ms=$(( $(date +%s%3N) - t0 ))
}
ok() { "$@" && echo 1 || echo 0; }

# 1. standalone exit codes (pipes hide them)
o="$work/x2/01.json"; run -s "$work/no_such_dir" -o "$o"
check exit2-missing-source "$code" "$ms" "$(ok test "$code" = 2 -a ! -s "$work/out.bin" -a ! -e "$o")" "usage error, nothing written"
mkdir -p "$work/empty"; o="$work/x4/01.json"; run -s "$work/empty" -o "$o"
check exit4-empty-dir "$code" "$ms" "$(ok test "$code" = 4 -a ! -e "$o" -a "$(field "$work/x4/01.report.json" 'd["status"]')" = empty)" "report status empty"
d="$(corpus ok)"; o="$work/x0/01.json"; run -s "$d" -o "$o"
check exit0-ok "$code" "$ms" "$(ok cmp -s "$work/out.bin" "$o")" "stdout == artifact"
d="$(corpus partial)"; printf 'a\xff' > "$d/bad.txt"; o="$work/x3/01.json"; run -s "$d" -o "$o"
check exit3-partial "$code" "$ms" "$(ok test "$code" = 3 -a "$(field "$o" 'd["errors"][0]["stage"]')" = decode)" "errors[0].stage decode"
o="$work/x1/01.json"; run -s "$d" -o "$o" -M 3
check exit1-total-cap "$code" "$ms" "$(ok test "$code" = 1 -a ! -e "$o")" "nothing loaded"

# 2. unreadable file (chmod 000; root bypasses it) -> errors[] stage open
d="$(corpus perm)"; printf 'x' > "$d/secret.md"; chmod 000 "$d/secret.md"; o="$work/perm_out/01.json"; run -s "$d" -o "$o"
check unreadable-file "$code" "$ms" "$(ok test "$code" = 3 -a "$(field "$o" 'd["errors"][0]["path"]+"|"+d["errors"][0]["stage"]')" = 'secret.md|open')" "uid=$(id -u)"
chmod 644 "$d/secret.md"

# 2b. unreadable directory that sorts LAST (chmod 000) -> errors[] stage discover, never silence
d="$(corpus lastdir)"; mkdir "$d/zz_locked"; printf 'b' > "$d/zz_locked/b.md"; chmod 000 "$d/zz_locked"; o="$work/lastdir_out/01.json"; run -s "$d" -o "$o"
check unreadable-last-dir "$code" "$ms" "$(ok test "$code" = 3 -a "$(field "$o" 'd["errors"][0]["path"]+"|"+d["errors"][0]["stage"]')" = 'zz_locked|discover')" "uid=$(id -u)"
chmod 755 "$d/zz_locked"

# 3. FIFO is skipped without being opened (an open would block forever)
d="$(corpus fifo)"; mkfifo "$d/pipe.md"; o="$work/fifo_out/01.json"; run -s "$d" -o "$o"
check fifo "$code" "$ms" "$(ok test "$code" = 0 -a "$(field "$o" 'd["skipped"][0]["reason"]')" = not_regular_file)" "skipped not_regular_file"

# 4. symlink loop is skipped as a link, never followed
d="$(corpus symloop)"; ln -s "$d" "$d/loop"; o="$work/symloop_out/01.json"; run -s "$d" -o "$o"
check link-loop "$code" "$ms" "$(ok test "$code" = 0 -a "$(field "$o" 'd["skipped"][0]["reason"]')" = link)" "skipped link"

# 5. 488-character path loads
d="$work/longpath"; deep="$d"; while ((${#deep} < 430)); do deep="$deep/$(printf 'd%.0s' {1..50})"; done
mkdir -p "$deep"; leaf="$deep/$(printf 'f%.0s' $(seq 1 $((484 - ${#deep}))))"".md"; printf '# deep\n' > "$leaf"
o="$work/longpath_out/01.json"; run -s "$d" -o "$o"
check long-path-488 "$code" "$ms" "$(ok test "$code" = 0 -a "${#leaf}" -ge 488 -a "$(field "$o" 'len(d["documents"])')" = 1)" "path chars=${#leaf}"

# 6. dot-file is hidden; 7. undecodable (non-UTF-8) name loads with an escaped doc_id
d="$(corpus hidden)"; printf 'h' > "$d/.h.md"; printf 'n' > "$d/bad_$(printf '\x80').md"; o="$work/hidden_out/01.json"; run -s "$d" -o "$o"
check dot-file-hidden "$code" "$ms" "$(ok test "$code" = 0 -a "$(field "$o" 'd["skipped"][0]["reason"]')" = hidden)" "skipped hidden"
check undecodable-name "$code" "$ms" "$(ok test "$(field "$o" 'd["documents"][0]["doc_id"]')" = 'bad_\udc80.md')" "doc_id escaped"

# 8. p01 | head -c 10 with a payload > 64 KiB: p01 keeps its computed exit code, no traceback
d="$work/pipe"; mkdir -p "$d"; head -c 200000 /dev/zero | tr '\0' 'x' > "$d/big.txt"; o="$work/pipe_out/01.json"
t0=$(date +%s%3N); p01 -s "$d" -o "$o" 2> "$work/err.txt" | head -c 10 > /dev/null; code=${PIPESTATUS[0]}; ms=$(( $(date +%s%3N) - t0 ))
check stdout-closed-early "$code" "$ms" "$(ok test "$code" = 0 -a "$(stat -c %s "$o")" -gt 65536 -a -z "$(grep -l Traceback "$work/err.txt")")" "exit 0, no traceback"

# 9. SIGINT and SIGTERM during the load of a 200 MB file: exit 130, no tmp left
d="$work/sig"; mkdir -p "$d"; head -c 209715200 /dev/zero | tr '\0' 'y' > "$d/huge.txt"
set -m  # job control: background jobs keep SIGINT (non-interactive shells otherwise ignore it)
for sig in INT TERM; do
    o="$work/sig_$sig/01.json"; : > "$work/err.txt"; t0=$(date +%s%3N)
    p01 -s "$d" -o "$o" > /dev/null 2> "$work/err.txt" & pid=$!
    for _ in $(seq 1 300); do grep -q 'load start' "$work/err.txt" && break; sleep 0.05; done
    sleep 0.3; kill -s "$sig" "$pid"; wait "$pid"; code=$?; ms=$(( $(date +%s%3N) - t0 ))
    check "$([[ $sig == INT ]] && echo interrupt || echo interrupt-sigterm)" "$code" "$ms" "$(ok test "$code" = 130 -a -z "$(find "$work/sig_$sig" -name '.*.tmp' 2>/dev/null)")" "interrupted, no tmp"
done
set +m

echo "{\"suite\": \"load_negatives.sh\", \"host\": \"$(hostname)\", \"cases\": $cases, \"failed\": $failed, \"work\": \"$work\"}"
((keep)) || rm -rf "$work"
((failed == 0))
