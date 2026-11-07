# Native dependencies that have no Linux wheels

`manim` needs two compiled extensions that PyPI does **not** ship for Linux:
`pycairo` (cairo bindings) and `manimpango` (pango bindings). On a normal Debian
box `apt install libcairo2-dev libpango1.0-dev` is enough. On a stripped
container — no apt, no `pkg-config`, no cairo/pango at all — neither the wheels
nor a source build are possible locally.

You normally never touch this: `scripts/bootstrap.sh` installs cairo/pango
from the system packages when it can, and otherwise fetches this bundle and
activates it automatically (`animatica/_nativelibs.py`). This document is for
maintaining that path.

`.github/workflows/native-deps.yml` solves that: a GitHub runner builds the
extensions inside a `python:3.11-slim-bookworm` container and ships the result
as a **bundle** (`wheels/` + `lib/`) that runs on any glibc ≥ 2.36 / x86_64 host.

## Getting the bundle

Two delivery modes, both controlled by the workflow:

| mode | how | when to use |
| --- | --- | --- |
| artifact (default, `COMMIT_BUNDLE: "0"`) | Actions → run → download `animatica-native` | normal use; needs `actions:read` |
| commit (`COMMIT_BUNDLE: "1"`) | job commits `native/animatica-native.tar.gz` to the branch | hosts that can only reach `codeload.github.com` (Actions artifact downloads redirect to `*.blob.core.windows.net`, which is often blocked) |

Trigger it by pushing a change to `.github/workflows/native-deps.yml` (or
`workflow_dispatch` once the file is on the default branch).

With the commit path the tarball is fetched without any API token:

```bash
curl -sL -o branch.tgz \
  https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>
tar xzf branch.tgz --strip-components=1 -C out "*/native/animatica-native.tar.gz"
tar xzf out/native/animatica-native.tar.gz -C native/
```

Delete the committed release artifact afterwards (it is ~2.6 MB and rewrites on
every run) so the branch history stays clean; squash-merging a PR drops it from
the target branch anyway.

## Using the bundle

```bash
export LD_LIBRARY_PATH=$PWD/native/lib:$LD_LIBRARY_PATH
pip install --no-deps --target ./vendor native/wheels/*.whl   # pycairo, manimpango
pip install --target ./vendor 'manim'                          # plain, no --only-binary
export PYTHONPATH=$PWD/vendor:$PYTHONPATH
python -m animatica doctor
```

`--no-deps` for the two wheels is deliberate: their runtime dependencies are the
shared libraries in `native/lib`, not other Python packages. `manim` itself is
pure Python and installs normally once cairo/pango resolve.

## What the bundle contains

- `wheels/`: `pycairo-*-cp311-*.whl`, `manimpango-*-cp311-*.whl`
- `lib/`: `libcairo`, `libpixman-1`, `libpng16`, `libXrender`, `libXext`,
  `libXau`, `libXdmcp`, `liblzo2`, `libpango-1.0`, `libpangoft2-1.0`,
  `libpangocairo-1.0`, `libharfbuzz`, `libfribidi`, `libthai`, `libdatrie`,
  `libgraphite2`, `libxcb-render`, `libxcb-shm` (plus their `-dev` symlinks)

The X11 libraries are needed only because cairo links against them; manim renders
to cairo image surfaces, so nothing actually opens a display.

## Windows

No bundle is needed: the Windows wheels of `pycairo` and `manimpango` ship the
cairo/pango DLLs, so `scripts/bootstrap.ps1` just installs them. The two installers
otherwise do the same job (source, environment, LaTeX, verify, then `animatica tui`).

## Known limits

- **LaTeX** is not in the bundle. `MathTex` and friends still fail; text built on
  pango (`Text`, `MarkupText`) renders fine. The doctor report and the CI
  workflow (`ci.yml`) cover the TeX path on a runner with `texlive`.
- **HyperFrames / headless Chrome** needs Chromium and ~12 GUI libraries — a
  separate, much larger bundle.
- The bundle is built for **cp311 / x86_64 / glibc ≥ 2.36**. Change the container
  image, the wheel tag, or the `find` list if the target host differs.
