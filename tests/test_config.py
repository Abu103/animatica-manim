import os
import stat
import sys

import pytest

from animatica.config import Config, load_config, load_key, save_config, save_key


@pytest.fixture(autouse=True)
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_config_roundtrip():
    save_config(Config(provider="groq"))
    assert load_config().provider == "groq"


def test_config_defaults_when_missing():
    c = load_config()
    assert c.provider == "auto" and c.cloud_allowed is False and c.max_runtime_secs == 300


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_key_file_mode(cfg_dir):
    save_key("groq", "secret-key-123")
    key_files = [p for p in cfg_dir.rglob("*") if p.is_file() and "secret-key-123" in p.read_text()]
    assert len(key_files) == 1
    assert stat.S_IMODE(key_files[0].stat().st_mode) == 0o600
    assert load_key("groq") == "secret-key-123"


def test_key_not_in_config_toml(cfg_dir):
    save_config(Config(provider="groq"))
    save_key("groq", "secret-key-123")
    assert "secret-key-123" not in (cfg_dir / "config.toml").read_text()


def test_missing_key_is_none():
    assert load_key("nim") is None

