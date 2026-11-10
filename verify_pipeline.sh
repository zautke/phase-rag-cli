#!/usr/bin/env bash
# Thin wrapper: all logic lives in verify_pipeline.py. Flags: -q/--quiet  -s/--skip-sync  -h/--help
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

Usage() {
    echo "Usage: ./verify_pipeline.sh [-q | --quiet] [-s | --skip-sync] [-h | --help]"
    echo "Runs the 4-stage battery via verify_pipeline.py (full help: uv run python verify_pipeline.py -h)."
}

for arg in "$@"; do [[ "$arg" == -h || "$arg" == --help ]] && { Usage; exit 0; }; done
exec uv run --project "$here" python "$here/verify_pipeline.py" "$@"