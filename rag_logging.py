#!/usr/bin/env python3
# rag_logging.py
"""Named `rag.<phase>` loggers on stderr (Rich, sharing err_console) + peak RSS for run reports."""
from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler

from rag_contracts import err_console

DEFAULT_LOG_LEVEL = "INFO"  # mirrored in .env.example (RAG_LOG_LEVEL)
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def get_logger(phase: str, level: str = DEFAULT_LOG_LEVEL) -> logging.Logger:
    """Idempotent: one handler on the `rag` logger, never on root (library INFO stays out).
    err_console resolves sys.stderr per write, so CliRunner's swapped stderr is honoured."""
    root = logging.getLogger("rag")
    if not root.handlers:
        root.addHandler(RichHandler(console=err_console, show_path=False, show_time=False))
        root.propagate = False
    root.setLevel(level.upper())
    return root.getChild(phase)


def peak_rss_bytes() -> int:
    """Peak resident set of this process in bytes (Windows: PeakWorkingSetSize); 0 if unavailable."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE  # untyped, a 64-bit handle is truncated -> 0
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        pmc = PMC(cb=ctypes.sizeof(PMC))
        ok = k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return int(pmc.PeakWorkingSetSize) if ok else 0
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # Linux reports KiB
