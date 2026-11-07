# tests/conftest.py -- hermetic plain-text CLI output for help/error assertions.
# typer.rich_utils forces a colour terminal when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS
# is set, which splits asserted text with ANSI codes. Drop them before any test module
# imports typer; subprocess-based tests inherit the cleaned environment.
import os

for _var in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(_var, None)
