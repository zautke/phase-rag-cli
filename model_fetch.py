#!/usr/bin/env python3
# model_fetch.py
"""Fetch model files with aria2c into the Hugging Face cache layout, reporting progress on stderr.

Files land in <cache>/models--<org>--<name>/snapshots/<sha>/ with refs/main -> <sha>, so
huggingface_hub, transformers, sentence-transformers and fastembed find them locally and
download nothing themselves. stdout is never written (Tri-Plex I/O).
"""
from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi, constants
from huggingface_hub.file_download import repo_folder_name

INSTALL_HINT = "winget install aria2.aria2 | sudo apt-get install -y aria2 | brew install aria2"


def _log(msg: str) -> None:
    print(f"[model-fetch] {msg}", file=sys.stderr, flush=True)


def _cached_snapshot(root: Path) -> Path | None:
    ref = root / "refs" / "main"
    if ref.is_file():
        snap = root / "snapshots" / ref.read_text().strip()
        if snap.is_dir():
            return snap
    return None


def ensure_model(
    repo_id: str,
    cache_dir: str | os.PathLike[str] | None = None,
    include: tuple[str, ...] = ("*",),
    exclude: tuple[str, ...] = (),
) -> Path:
    """Make every repo file matching include/exclude present locally; return the snapshot dir."""
    root = Path(cache_dir or constants.HF_HUB_CACHE) / repo_folder_name(repo_id=repo_id, repo_type="model")
    if constants.HF_HUB_OFFLINE:
        snap = _cached_snapshot(root)
        if snap is None:
            raise RuntimeError(f"{repo_id} not cached under {root} and HF_HUB_OFFLINE is set")
        return snap
    try:
        info = HfApi().model_info(repo_id, files_metadata=True)
    except Exception as exc:  # network down: a complete earlier fetch is still usable
        snap = _cached_snapshot(root)
        if snap is None:
            raise
        _log(f"{repo_id}: hub unreachable ({type(exc).__name__}); using cached {snap.name[:7]}")
        return snap

    snap = root / "snapshots" / str(info.sha)
    files = [
        s for s in info.siblings or []
        if any(fnmatch.fnmatch(s.rfilename, p) for p in include)
        and not any(fnmatch.fnmatch(s.rfilename, p) for p in exclude)
    ]
    if any(s.rfilename.endswith(".safetensors") for s in files):  # loaders prefer safetensors
        files = [s for s in files if not s.rfilename.endswith(".bin")]
    missing = []
    for s in files:
        path = snap / s.rfilename
        size = path.stat().st_size if path.is_file() else -1
        if s.size is None or size != s.size:
            if s.size is not None and size > s.size:
                path.unlink()  # larger than remote: corrupt, cannot resume
            missing.append(s)
    (root / "refs").mkdir(parents=True, exist_ok=True)
    (root / "refs" / "main").write_text(str(info.sha))
    if not missing:
        return snap

    aria2 = shutil.which("aria2c")
    if not aria2:
        raise RuntimeError(f"aria2c not found on PATH; install it: {INSTALL_HINT}")
    total_mb = sum(s.size or 0 for s in missing) / 1e6
    _log(f"{repo_id}@{str(info.sha)[:7]}: downloading {len(missing)} file(s), {total_mb:.1f} MB -> {snap} (aria2c)")
    for s in missing:
        _log(f"  {s.rfilename} ({(s.size or 0) / 1e6:.1f} MB)")
    lines: list[str] = []
    token = os.environ.get("HF_TOKEN")
    for s in missing:
        lines += [f"{constants.ENDPOINT}/{repo_id}/resolve/{info.sha}/{s.rfilename}", f"  out={s.rfilename}"]
        if token:
            lines.append(f"  header=Authorization: Bearer {token}")
    with tempfile.NamedTemporaryFile("w", suffix=".aria2", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    started = time.monotonic()
    try:
        rc = subprocess.run(
            [
                aria2, f"--input-file={fh.name}", f"--dir={snap}", "--continue=true",
                "--max-connection-per-server=8", "--split=8", "--min-split-size=8M",
                "--max-concurrent-downloads=4", "--max-tries=10", "--retry-wait=3",
                "--auto-file-renaming=false", "--file-allocation=none",
                "--summary-interval=5", "--console-log-level=warn",
            ],
            stdout=2,  # aria2c progress readout -> our stderr; stdout stays payload-only
            check=False,
        ).returncode
    finally:
        os.unlink(fh.name)
    bad = [s.rfilename for s in missing if s.size is not None
           and (not (snap / s.rfilename).is_file() or (snap / s.rfilename).stat().st_size != s.size)]
    if rc != 0 or bad:
        raise RuntimeError(f"aria2c exit {rc} fetching {repo_id}; incomplete: {bad or 'see log above'}")
    _log(f"{repo_id}: done, {total_mb:.1f} MB in {time.monotonic() - started:.1f} s")
    return snap
