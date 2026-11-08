#!/usr/bin/env python3
"""Prepare the local asset tree for a HyperFrames pilot.

The composition templates reference three kinds of third-party material:

* ``vendor/gsap.min.js``          -- GSAP 3.15.1 (Webflow Standard "no charge" license)
* ``assets/*.woff2``              -- Manrope + Space Grotesk (SIL Open Font License 1.1)
* ``assets/logic-chimes.wav``     -- original synthesis, regenerated locally

Everything here is copied from the *project-local* ``node_modules`` tree that
``npm ci`` installs, or regenerated from source. Nothing is downloaded at setup
time and no asset is fetched from a CDN at render time, so a clean checkout
reproduces the exact same bytes.

Run it from the pilot directory::

    npm ci
    python3 scripts/setup_assets.py

The script is idempotent and safe to re-run.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

PILOT_ROOT = Path(__file__).resolve().parent.parent
NODE_MODULES = PILOT_ROOT / "node_modules"
VENDOR_DIR = PILOT_ROOT / "vendor"
ASSETS_DIR = PILOT_ROOT / "assets"

# (source relative to node_modules, destination relative to the pilot root)
FONT_FILES = [
    ("@fontsource/manrope/files/manrope-latin-400-normal.woff2", "assets/manrope-regular.woff2"),
    ("@fontsource/manrope/files/manrope-latin-600-normal.woff2", "assets/manrope-semibold.woff2"),
    ("@fontsource/manrope/files/manrope-latin-700-normal.woff2", "assets/manrope-bold.woff2"),
    ("@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2",
     "assets/space-grotesk-medium.woff2"),
    ("@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2",
     "assets/space-grotesk-bold.woff2"),
]

LICENSE_FILES = [
    ("@fontsource/manrope/LICENSE", "assets/LICENSE-manrope.txt"),
    ("@fontsource/space-grotesk/LICENSE", "assets/LICENSE-space-grotesk.txt"),
]

GSAP_SOURCE = "gsap/dist/gsap.min.js"
GSAP_DEST = "vendor/gsap.min.js"


def fail(message: str) -> "None":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_asset(source_rel: str, dest_rel: str) -> None:
    source = NODE_MODULES / source_rel
    if not source.is_file():
        fail(f"missing {source_rel} in node_modules -- run 'npm ci' in {PILOT_ROOT.name} first")
    destination = PILOT_ROOT / dest_rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"  {dest_rel}  sha256={sha256(destination)}")


def copy_gsap() -> None:
    source = NODE_MODULES / GSAP_SOURCE
    if not source.is_file():
        fail("missing gsap/dist/gsap.min.js in node_modules -- run 'npm ci' first")
    destination = PILOT_ROOT / GSAP_DEST
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"  {GSAP_DEST}  sha256={sha256(destination)}")


def regenerate_audio() -> None:
    generator = PILOT_ROOT / "scripts" / "generate_audio.py"
    if not generator.is_file():
        fail("scripts/generate_audio.py is missing from this checkout")
    result = subprocess.run(
        [sys.executable, str(generator)],
        cwd=str(PILOT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"audio generation failed:\n{result.stdout}\n{result.stderr}")
    print(f"  {result.stdout.strip()}")
    wav = ASSETS_DIR / "logic-chimes.wav"
    print(f"  assets/logic-chimes.wav  sha256={sha256(wav)}")


def main() -> int:
    if not NODE_MODULES.is_dir():
        fail(f"node_modules not found at {NODE_MODULES} -- run 'npm ci' in {PILOT_ROOT.name} first")

    print("GSAP (Webflow Standard 'no charge' license -- see vendor/GSAP-LICENSE.txt):")
    copy_gsap()

    print("Fonts (SIL Open Font License 1.1 -- see assets/LICENSE-*.txt):")
    for source_rel, dest_rel in FONT_FILES:
        copy_asset(source_rel, dest_rel)

    print("Font licenses:")
    for source_rel, dest_rel in LICENSE_FILES:
        copy_asset(source_rel, dest_rel)

    print("Original synthesized audio (regenerated locally, no samples):")
    regenerate_audio()

    print("\nAssets ready. Next: python3 src/pilot.py <fixture.json> <output.html>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
