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


def test_key_file_is_private(cfg_dir):
    """The key lives in its own file, and on POSIX nothing else can read it.

    Windows has no POSIX mode bits, so there the invariant checked is that the key
    is not in config.toml and still round-trips; skipping the test there would leave
    the Windows job with an unexplained gap.
    """
    save_key("groq", "secret-key-123")
    key_files = [p for p in cfg_dir.rglob("*") if p.is_file() and "secret-key-123" in p.read_text(encoding="utf-8")]
    assert len(key_files) == 1
    if os.name == "posix":
        assert stat.S_IMODE(key_files[0].stat().st_mode) == 0o600
    else:
        assert key_files[0].name != "config.toml"
    assert load_key("groq") == "secret-key-123"


def test_key_not_in_config_toml(cfg_dir):
    save_config(Config(provider="groq"))
    save_key("groq", "secret-key-123")
    assert "secret-key-123" not in (cfg_dir / "config.toml").read_text(encoding="utf-8")


def test_missing_key_is_none():
    assert load_key("nim") is None

