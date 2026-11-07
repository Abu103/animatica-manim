# HyperFrames experiment pilots

This directory holds two independent, hand-authored HyperFrames explainer
pilots used to evaluate the HyperFrames toolchain:

| Pilot | Path | What it explains |
| --- | --- | --- |
| 3-SAT | `hyperframes-3sat-pilot/` | Boolean formula truth evaluation |
| Binary search | `hyperframes-binary-search-pilot/` | Binary search over a sorted array |

Each pilot is self-contained: its own `package.json`, pinned `package-lock.json`,
HTML template, Python renderer, fixtures and focused test suite.

---

## Clean-checkout setup

Both pilots follow the same four-step process. Run the commands **from inside
the pilot directory**.

### 1. Prerequisites

| Requirement | Version used | Notes |
| --- | --- | --- |
| Node.js | `>=22` (declared in `engines`) | The npm `node` package is *not* used; it is a runtime installer, not a library, and the project gets Node from the host. |
| npm | 11.x | Uses the project-local `allowScripts` field in `package.json`. |
| Python | `>=3.10` | Standard library only for asset setup and the pilot renderers. |
| Chrome/Chromium | any recent build | HyperFrames manages its own browser download in a user-level cache. Not installed into the repo. |
| FFmpeg | provided by `ffmpeg-static` | Installed project-locally into `node_modules/`; HyperFrames also accepts a system FFmpeg via `PATH` or `FFMPEG_PATH`. |

Nothing is installed system-wide. All npm packages land in the pilot's own
`node_modules/`.

### 2. Install pinned dependencies

```bash
cd experiments/hyperframes-3sat-pilot     # or .../hyperframes-binary-search-pilot
npm ci
```

`npm ci` installs exactly what `package-lock.json` pins. The two npm packages
that need an install script (`ffmpeg-static`, which downloads the FFmpeg
binary, and `esbuild`, which downloads its platform binary) are explicitly
approved in `package.json`:

```json
"allowScripts": {
  "esbuild": true,
  "ffmpeg-static": true
}
```

This field is project-local: it takes precedence over any user or global
`.npmrc` `allow-scripts` setting, so a clean checkout behaves the same for
every contributor without touching global npm configuration.

### 3. Prepare the local asset tree

```bash
npm run setup          # equivalent to: python3 scripts/setup_assets.py
```

This copies, from the pilot's own `node_modules/`:

* `vendor/gsap.min.js` from the pinned `gsap` package
* `assets/*.woff2` from `@fontsource/manrope` and `@fontsource/space-grotesk`
* `assets/LICENSE-manrope.txt`, `assets/LICENSE-space-grotesk.txt`

and regenerates `assets/logic-chimes.wav` by running `scripts/generate_audio.py`.
The audio is original deterministic synthesis (seeded PRNG, no samples, no
service, no API) and reproduces byte-for-byte on every run.

The script prints a SHA-256 for each file it writes, so a clean checkout can be
verified against a known-good tree.

### 4. Build the composition and render

```bash
# 3-SAT pilot
python3 src/pilot.py fixtures/fixture_a_all_true.json renders/pilot_a.html
cp renders/pilot_a.html index.html
npx hyperframes check
npx hyperframes render --output renders/3sat-explained.mp4 --no-browser-gpu

# binary-search pilot
python3 src/binary_search_pilot.py fixtures/fixture_find_13.json renders/binary_search_find_13.html
cp renders/binary_search_find_13.html index.html
npx hyperframes check
npx hyperframes render --output renders/binary-search-explained.mp4 --no-browser-gpu
```

`index.html` is the composition entry point HyperFrames looks for. It is a
generated artifact and is not tracked in Git.

---

## Licensing and attribution

Third-party material is **not** fetched from a CDN at render time. Using a CDN
would not remove any of the obligations below, so everything is served from the
pilot's local `vendor/` and `assets/` directories.

### GSAP 3.15.1

Licensed under Webflow's **Standard "No Charge" GSAP License**
(<https://gsap.com/standard-license/>) — *not* an OSS license and *not* MIT.

* Upstream banner in `vendor/gsap.min.js` is preserved verbatim; proprietary
  notices and branding must not be removed or altered.
* Free for commercial and non-commercial use provided end users are not
  charged a usage/access/license fee. A one-time client fee for building a
  product is explicitly allowed. If end users are charged a fee, a Business
  Club GSAP membership with a commercial license is required.
* "Prohibited Uses" are tools that let users build visual animations without
  code in a way that competes with Webflow's animation-building capabilities.
  Upstream's FAQ states AI-generated GSAP code is not a Prohibited Use.
* No warranties are offered.

Full text, the compliance notes for this repo, and the attribution notice are
in `vendor/GSAP-LICENSE.txt` (tracked in Git).

### Manrope and Space Grotesk

Both are licensed under the **SIL Open Font License 1.1** (`OFL-1.1`). The OFL
permits bundling and redistribution provided the license travels with the
fonts and the fonts are not sold on their own. The license files are copied
next to the font binaries by `setup_assets.py` as
`assets/LICENSE-manrope.txt` and `assets/LICENSE-space-grotesk.txt`.

### FFmpeg (`ffmpeg-static`)

`ffmpeg-static` is a build of FFmpeg distributed under **GPL-3.0-or-later**.
It is installed into `node_modules/` by `npm ci` and is not committed to this
repository. The FFmpeg binary is used only as a local encoder for rendering.

### ffprobe (`ffprobe-static`)

Distributed under the **MIT** license. Installed locally, not committed.

### Original audio

`scripts/generate_audio.py` is original work in this repository: deterministic
synthesis from a seeded PRNG using only the Python standard library. It
contains no third-party samples and calls no network service.

---

## What is and is not tracked

Tracked: `package.json`, `package-lock.json`, `src/`, `tests/`, `fixtures/`,
`scripts/`, `vendor/GSAP-LICENSE.txt`.

Not tracked (regenerated or downloaded at setup time): `node_modules/`,
`vendor/gsap.min.js`, `assets/*.woff2`, `assets/*.wav`, `index.html`,
`renders/`, `frames/`, `snapshots/`, `.hyperframes/`, browser binaries and
caches.

---

## Running the focused tests

The pilot test suites use `pytest` and only need the standard library plus
`pytest`:

```bash
cd experiments/hyperframes-3sat-pilot
python3 -m pytest tests/ -q

cd ../hyperframes-binary-search-pilot
python3 -m pytest tests/ -q
```

No system-wide install is required if the repository's own `.venv/` is
available; `../..//.venv/bin/python -m pytest tests/ -q` also works.

---

## Platform notes

The setup above was verified on **WSL / Linux**. The Windows path
(`run-windows.ps1` in the 3-SAT pilot) exists but has **not** been executed on
Windows in this repository's CI for these experiments; treat Windows support
as unverified.
