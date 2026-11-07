# tests/conftest.py -- hermetic plain-text CLI output for help/error assertions.
# typer.rich_utils (FORCE_TERMINAL, MAX_WIDTH) forces a colour terminal when GITHUB_ACTIONS,
# FORCE_COLOR or PY_COLORS is set, and ANSI codes split asserted text (e.g. "--dense-backend").
# Pin a plain, wide terminal before any test module imports typer; CliRunner and subprocess
# tests both inherit it, so the same assertions hold on a laptop, in a tty and on a CI runner.
import os

for _var in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(_var, None)
os.environ.update(
    NO_COLOR="1",  # rich.console no_color
    TERM="dumb",  # rich.console is_dumb_terminal -> no colour system, no style codes
    COLUMNS="200",  # rich.console width
    TERMINAL_WIDTH="200",  # typer.rich_utils MAX_WIDTH
    _TYPER_FORCE_DISABLE_TERMINAL="1",  # typer.rich_utils FORCE_TERMINAL=False
)
