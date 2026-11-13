"""Every relative link in the README and the docs it points at must resolve (task card T20)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "docs" / "GALLERY.md", ROOT / "docs" / "VERIFIED_INSTALLS.md"]
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(doc):
    text = doc.read_text(encoding="utf-8")
    for target in _LINK.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        path = (doc.parent / target.split("#")[0]).resolve()
        assert path.exists(), f"{doc.name}: broken link {target}"


def test_readme_what_you_get_links_the_gallery_and_the_baseline():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## What you get", 1)[1].split("\n## ", 1)[0]
    assert "docs/GALLERY.md" in section and "docs/EVAL_BASELINE.md" in section


def test_verified_installs_table_has_no_rows_until_a_real_run_is_reported():
    lines = [l for l in (ROOT / "docs" / "VERIFIED_INSTALLS.md").read_text(encoding="utf-8").splitlines() if l.startswith("|")]
    assert len(lines) == 2, "only the header and separator; add a row only from a real clean-machine run"
