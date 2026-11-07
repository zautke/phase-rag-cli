from types import SimpleNamespace

import pytest

import model_fetch

SHA = "abc1234def"


def _fake_api(monkeypatch, siblings, sha=SHA, seen=None):
    info = SimpleNamespace(sha=sha, siblings=[SimpleNamespace(rfilename=n, size=s) for n, s in siblings])

    def model_info(*a, **k):
        if seen is not None:
            seen.append(k)
        return info

    monkeypatch.setattr(model_fetch, "HfApi", lambda: SimpleNamespace(model_info=model_info))


def _fake_aria2(monkeypatch, sizes, rc=0, write=True):
    """Pretend aria2c is installed; its 'download' writes `sizes` files into --dir (or half of them on failure)."""
    monkeypatch.setattr(model_fetch.shutil, "which", lambda _: "aria2c")

    def run(cmd, **kw):
        out = next(a.split("=", 1)[1] for a in cmd if a.startswith("--dir="))
        for name, size in sizes.items():
            if write:
                (model_fetch.Path(out) / name).parent.mkdir(parents=True, exist_ok=True)
                (model_fetch.Path(out) / name).write_bytes(b"x" * (size if rc == 0 else size // 2))
        return SimpleNamespace(returncode=rc)

    monkeypatch.setattr(model_fetch.subprocess, "run", run)


def test_present_files_skip_download_and_filters_apply(tmp_path, monkeypatch):
    _fake_api(monkeypatch, [("config.json", 2), ("model.safetensors", 3), ("pytorch_model.bin", 9), ("onnx/model.onnx", 5)])
    snap = tmp_path / "models--org--m" / "snapshots" / SHA
    snap.mkdir(parents=True)
    (snap / "config.json").write_bytes(b"{}")
    (snap / "model.safetensors").write_bytes(b"abc")
    monkeypatch.setattr(model_fetch.shutil, "which", lambda _: pytest.fail("aria2c must not run"))
    # .bin dropped because safetensors exists; onnx excluded by pattern
    assert model_fetch.ensure_model("org/m", tmp_path, exclude=("onnx/*",)) == snap
    assert (tmp_path / "models--org--m" / "refs" / "main").read_text() == SHA
    assert (snap / ".complete").is_file()


def test_missing_file_without_aria2_exits_with_one_install_line(tmp_path, monkeypatch, capsys):
    _fake_api(monkeypatch, [("model.onnx", 10)])
    monkeypatch.setattr(model_fetch.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        model_fetch.ensure_model("org/m", tmp_path)
    assert exc.value.code not in (0, None)
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "winget install aria2.aria2" in err
    assert "sudo apt-get -o Acquire::ForceIPv4=true install aria2" in err
    assert not (tmp_path / "models--org--m" / "refs" / "main").exists()


def test_interrupted_fetch_leaves_no_ref_or_marker(tmp_path, monkeypatch):
    _fake_api(monkeypatch, [("model.onnx", 10)])
    _fake_aria2(monkeypatch, {"model.onnx": 10}, rc=7)  # killed mid-download: half the bytes on disk
    with pytest.raises(RuntimeError, match="incomplete"):
        model_fetch.ensure_model("org/m", tmp_path)
    root = tmp_path / "models--org--m"
    assert not (root / "refs" / "main").exists()
    assert not (root / "snapshots" / SHA / ".complete").exists()


def test_short_file_after_clean_exit_leaves_no_ref(tmp_path, monkeypatch):
    _fake_api(monkeypatch, [("model.onnx", 10)])
    _fake_aria2(monkeypatch, {"model.onnx": 4})  # rc 0 but wrong size
    with pytest.raises(RuntimeError, match="incomplete"):
        model_fetch.ensure_model("org/m", tmp_path)
    assert not (tmp_path / "models--org--m" / "refs" / "main").exists()


def test_verified_fetch_writes_ref_and_marker_then_skips_hub(tmp_path, monkeypatch):
    seen: list = []
    _fake_api(monkeypatch, [("model.onnx", 10)], seen=seen)
    _fake_aria2(monkeypatch, {"model.onnx": 10})
    snap = model_fetch.ensure_model("org/m", tmp_path)
    root = tmp_path / "models--org--m"
    assert (root / "refs" / "main").read_text() == SHA
    assert (snap / ".complete").is_file()
    assert len(seen) == 1
    # second call: marker present -> no hub call at all
    monkeypatch.setattr(model_fetch, "HfApi", lambda: pytest.fail("hub must not be called"))
    assert model_fetch.ensure_model("org/m", tmp_path) == snap
    # a different include filter was never verified -> hub is consulted again
    seen2: list = []
    _fake_api(monkeypatch, [("model.onnx", 10), ("tok.json", 2)], seen=seen2)
    _fake_aria2(monkeypatch, {"tok.json": 2})
    model_fetch.ensure_model("org/m", tmp_path, include=("tok.json",))
    assert len(seen2) == 1


def test_model_info_uses_hub_etag_timeout(tmp_path, monkeypatch):
    seen: list = []
    _fake_api(monkeypatch, [("a.json", 1)], seen=seen)
    snap = tmp_path / "models--org--m" / "snapshots" / SHA
    snap.mkdir(parents=True)
    (snap / "a.json").write_bytes(b"x")
    model_fetch.ensure_model("org/m", tmp_path)
    assert seen[0]["timeout"] == model_fetch.constants.HF_HUB_ETAG_TIMEOUT


def _cached(tmp_path, complete: bool):
    root = tmp_path / "models--org--m"
    snap = root / "snapshots" / "old"
    snap.mkdir(parents=True)
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("old")
    if complete:
        (snap / ".complete").write_text(model_fetch._signature(("*",), ()) + "\n")
    return snap


def _offline_hub(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(model_fetch, "HfApi", lambda: SimpleNamespace(model_info=boom))


def test_unreachable_hub_serves_verified_snapshot_without_calling_it(tmp_path, monkeypatch):
    _offline_hub(monkeypatch)
    snap = _cached(tmp_path, complete=True)
    monkeypatch.setattr(model_fetch.constants, "HF_HUB_OFFLINE", False)
    # marker present -> hub never consulted, snapshot served
    assert model_fetch.ensure_model("org/m", tmp_path) == snap


def test_unreachable_hub_refuses_unmarked_snapshot(tmp_path, monkeypatch):
    _offline_hub(monkeypatch)
    monkeypatch.setattr(model_fetch.constants, "HF_HUB_OFFLINE", False)
    _cached(tmp_path, complete=False)  # ref + dir but no proof of a verified fetch
    with pytest.raises(OSError):
        model_fetch.ensure_model("org/m", tmp_path)


def test_hf_offline_mode_requires_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(model_fetch.constants, "HF_HUB_OFFLINE", True)
    _cached(tmp_path, complete=False)
    with pytest.raises(RuntimeError, match="not cached"):
        model_fetch.ensure_model("org/m", tmp_path)
