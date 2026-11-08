"""The version must be true and in one place.

GitHub shows a published v0.1.1 release, but the source tree claimed 0.1.0
in both pyproject.toml and animatica.__version__. A user who ran
`animatica --version` got a number that did not match any release. These
tests keep the two strings in sync and keep the value a valid PEP 440
version, so the release process cannot cut a tag whose version lies.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from animatica import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent

#: PEP 440, public version only (no local segment): N(.N)* with an optional
#: pre/post/dev suffix, e.g. 1.2, 1.2.3rc1, 0.2.0.dev0.
PEP440 = re.compile(
    r"^\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?$",
)


def _pyproject_version() -> str:
    """Read [project].version straight from pyproject.toml."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_package_version_matches_pyproject():
    """animatica.__version__ and pyproject.toml must be the same string."""
    assert __version__ == _pyproject_version()


def test_version_is_a_valid_pep440_version():
    """A malformed version breaks setuptools, twine and pip installs."""
    assert PEP440.match(__version__), f"not a PEP 440 version: {__version__!r}"


def test_version_is_not_the_already_published_release():
    """0.1.1 is published on GitHub; the tree must be past it, not on it.

    Cutting a v0.2.0 tag from a tree that still says 0.1.1 would ship the
    same version twice under two tags.
    """
    assert __version__ != "0.1.1", "0.1.1 is already published on GitHub"


def test_version_is_past_the_published_release():
    """The tree must be a version *newer* than the published v0.1.1.

    GitHub already carries v0.1.1 (published 2026-11-04). The source tree
    still said 0.1.0, so `animatica --version` reported a version that was
    neither the latest release nor the version under development. The
    working version must be strictly greater than the newest published one.
    """
    published = (0, 1, 1)
    current = tuple(int(part) for part in __version__.split(".")[:3])
    assert current > published, (
        f"{__version__} is not newer than the published v0.1.1"
    )
