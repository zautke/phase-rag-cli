#!/usr/bin/env pwsh
# Thin wrapper: all logic lives in verify_pipeline.py. Flags: -q/--quiet  -s/--skip-sync  -h/--help
param([Parameter(ValueFromRemainingArguments)][string[]]$Rest)

function Usage {
    "Usage: ./verify_pipeline.ps1 [-q | --quiet] [-s | --skip-sync] [-h | --help]"
    "Runs the 4-stage battery via verify_pipeline.py (full help: uv run python verify_pipeline.py -h)."
}

if ($Rest -match '^(-h|--help)$') { Usage; exit 0 }
uv run --project $PSScriptRoot python "$PSScriptRoot/verify_pipeline.py" @Rest
exit $LASTEXITCODE