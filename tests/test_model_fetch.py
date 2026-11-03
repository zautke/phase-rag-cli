from types import SimpleNamespace

import pytest

import model_fetch


def _fake_api(monkeypatch, siblings, sha="abc1234def"):
    info = SimpleNamespace(sha=sha, siblings=[SimpleNamespace(rfilename=n, size=s) for n, s in siblings])
    monkeypatch.setattr(model_fetch, "HfApi", lambda: SimpleNamespace(model_info=lambda *a, **k: info))


def test_present_files_skip_download_and_filters_apply(tmp_path, monkeypatch):
    _fake_api(monkeypatch, [("config.json", 2), ("model.safetensors", 3), ("pytorch_model.bin", 9), ("onnx/model.onnx", 5)])
    snap = tmp_path / "models--org--m" / "snapshots" / "abc1234def"
    snap.mkdir(parents=True)
    (snap / "config.json").write_bytes(b"{}")
    (snap / "model.safetensors").write_bytes(b"abc")
    monkeypatch.setattr(model_fetch.shutil, "which", lambda _: pytest.fail("aria2c must not run"))
    # .bin dropped because safetensors exists; onnx excluded by pattern
    assert model_fetch.ensure_model("org/m", tmp_path, exclude=("onnx/*",)) == snap
    assert (tmp_path / "models--org--m" / "refs" / "main").read_text() == "abc1234def"


def test_missing_file_without_aria2_fails_loudly(tmp_path, monkeypatch):
    _fake_api(monkeypatch, [("model.onnx", 10)])
    monkeypatch.setattr(model_fetch.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="aria2c not found"):
        model_fetch.ensure_model("org/m", tmp_path)


def test_offline_hub_falls_back_to_cached_snapshot(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(model_fetch, "HfApi", lambda: SimpleNamespace(model_info=boom))
    root = tmp_path / "models--org--m"
    (root / "snapshots" / "old").mkdir(parents=True)
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("old")
    assert model_fetch.ensure_model("org/m", tmp_path) == root / "snapshots" / "old"
