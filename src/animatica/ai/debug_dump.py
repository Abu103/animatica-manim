"""Debug-only raw provider dumps (O1).

A provider's malformed reply often cannot be understood from the parse
error alone. With ``--debug``, every parse failure writes the untouched
reply to ``<out_dir>/debug/<stage>_<scene>_<attempt>.txt`` and prints the
80 characters around the position the parser reported. Without
``--debug`` this module is inert.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

#: json.JSONDecodeError ends with "(char N)"; ValidationError has no position.
_CHAR_POS = re.compile(r"\(char\s+(\d+)\)")


def dump_parse_failure(
    raw: str,
    *,
    out_dir: str | Path | None,
    stage: str,
    scene: int = 0,
    attempt: int = 1,
    error: BaseException | str,
    debug: bool,
    echo: Callable[[str], None] = print,
) -> Path | None:
    """Write the raw reply and print the error context. No-op unless debug.

    Returns the dump path when written, None otherwise.
    """
    if not debug or out_dir is None:
        return None
    path = Path(out_dir) / "debug" / f"{stage}_{scene}_{attempt}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    message = str(error)
    match = _CHAR_POS.search(message)
    if match:
        pos = int(match.group(1))
        snippet = raw[max(0, pos - 40): pos + 40].replace("\n", "\\n")
        echo(f"debug {path.name}: around char {pos}: ...{snippet}...")
    else:
        echo(f"debug {path.name}: {message[:200]}")
    return path


__all__ = ["dump_parse_failure"]
