"""User configuration and API key storage (keys live in a separate mode-600 file)."""
from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


@dataclass
class Config:
    provider: str = "auto"
    cloud_allowed: bool = False
    max_runtime_secs: int = 300


def config_dir() -> Path:
    override = os.environ.get("ANIMATICA_CONFIG_DIR")
    path = Path(override) if override else Path(platformdirs.user_config_dir("animatica"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_config(cfg: Config) -> None:
    lines = [f"{k} = {_toml_value(v)}" for k, v in asdict(cfg).items()]
    (config_dir() / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config() -> Config:
    path = config_dir() / "config.toml"
    if not path.exists():
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {k: v for k, v in data.items() if k in Config.__dataclass_fields__}
    return Config(**known)


def _keys_path() -> Path:
    return config_dir() / "keys.toml"


def _read_keys() -> dict[str, str]:
    path = _keys_path()
    if not path.exists():
        return {}
    return {k: str(v) for k, v in tomllib.loads(path.read_text(encoding="utf-8")).items()}


def save_key(provider: str, key: str) -> None:
    keys = _read_keys()
    keys[provider] = key
    body = "\n".join(f"{k} = {_toml_value(v)}" for k, v in keys.items()) + "\n"
    fd = os.open(_keys_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    if sys.platform != "win32":
        os.chmod(_keys_path(), 0o600)


def load_key(provider: str) -> str | None:
    return _read_keys().get(provider)

