#!/usr/bin/env bash
# Animatica one-command setup.
#
#   curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
#
# Gets you from a bare machine to a working render: python + manim + the cairo/pango
# libraries manim needs (system packages when available, otherwise a prebuilt
# bundle — no manual downloads), ffmpeg, and optionally LaTeX. Afterwards it opens
# nothing and asks nothing: run `animatica tui` and set your defaults there.
#
# Environment (all optional):
#   ANIMATICA_HOME        where to put the checkout        (default ~/animatica-manim)
#   ANIMATICA_REF         git branch/tag to install        (default main)
#   ANIMATICA_NATIVE_URL  tar.gz with wheels/ + lib/       (default: repo release)
#   ANIMATICA_TEX=0       skip the LaTeX (TinyTeX) step
#   ANIMATICA_NATIVE=0    never touch cairo/pango
#
# Flags: --full (always try LaTeX), --native-only (stop after the native deps),
#        --help
set -euo pipefail

GH_REPO="${ANIMATICA_GH_REPO:-Abu103/animatica-manim}"
GH_REF="${ANIMATICA_REF:-main}"
ROOT="${ANIMATICA_HOME:-$HOME/animatica-manim}"
DO_TEX="${ANIMATICA_TEX:-1}"
DO_NATIVE="${ANIMATICA_NATIVE:-1}"
MODE="install"

for arg in "$@"; do
  case "$arg" in
    --full) DO_TEX=1 ;;
    --native-only) MODE="native" ;;
    --help|-h) sed -n '2,20p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "unknown flag: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n[%s] %s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

# --------------------------------------------------------------------------- #
# 0. get the source (works from a checkout, a git clone, or a plain tarball)
# --------------------------------------------------------------------------- #
self_dir=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "$self_dir" ] && [ -f "$self_dir/../src/animatica/__init__.py" ]; then
  ROOT="$(cd "$self_dir/.." && pwd)"
  say "Using the checkout at $ROOT"
elif [ -f "$ROOT/src/animatica/__init__.py" ]; then
  say "Using the existing checkout at $ROOT"
else
  step "0/4" "downloading Animatica ($GH_REF)"
  if have git; then
    git clone --depth 1 --branch "$GH_REF" "https://github.com/$GH_REPO.git" "$ROOT"
  else
    mkdir -p "$ROOT"
    curl -fsSL "https://codeload.github.com/$GH_REPO/tar.gz/refs/heads/$GH_REF" |
      tar xz -C "$ROOT" --strip-components=1
  fi
fi
cd "$ROOT"
say "  -> $ROOT"

# --------------------------------------------------------------------------- #
# 1. cairo + pango: the libraries manim's pycairo/manimpango need
# --------------------------------------------------------------------------- #
LIB_READY=0
BUNDLE_USED=0
INSTALLER=""

has_lib() { ldconfig -p 2>/dev/null | grep -q "lib${1}\.so"; }

if has_lib cairo && has_lib pango-1.0 && has_lib pangocairo-1.0; then
  LIB_READY=1
fi

pick_installer() {
  if [ "$(id -u)" = "0" ]; then INSTALLER=""
  elif have sudo; then INSTALLER="sudo"
  else INSTALLER="none"; fi
  if ! have apt-get && ! have dnf && ! have apk && ! have brew; then INSTALLER="none"; fi
}

install_system_libs() {
  pick_installer
  [ "$INSTALLER" = "none" ] && return 1
  if have apt-get; then
    $INSTALLER apt-get update -qq >/dev/null 2>&1 || true
    $INSTALLER apt-get install -y -qq --no-install-recommends \
      libcairo2-dev libpango1.0-dev pkg-config >/dev/null 2>&1
  elif have dnf; then
    $INSTALLER dnf install -y -q cairo-devel pango-devel pkgconf-pkg-config >/dev/null 2>&1
  elif have apk; then
    $INSTALLER apk add -q --no-progress cairo-dev pango-dev pkgconf >/dev/null 2>&1
  elif have brew; then
    brew install -q cairo pango pkg-config >/dev/null 2>&1
  fi
  has_lib cairo && has_lib pango-1.0 && has_lib pangocairo-1.0
}

fetch_native_bundle() {
  local out="$1"
  if [ -n "${ANIMATICA_NATIVE_URL:-}" ]; then
    curl -fsSL --max-time 240 "$ANIMATICA_NATIVE_URL" -o "$out" && return 0
  fi
  # published by .github/workflows/native-deps.yml (release asset)
  curl -fsSL --max-time 240 \
    "https://github.com/$GH_REPO/releases/latest/download/animatica-native.tar.gz" \
    -o "$out" 2>/dev/null && return 0
  # last resort: the repo tree, where the workflow can also commit it
  local tmp; tmp="$(mktemp -d)"
  if curl -fsSL --max-time 240 \
       "https://codeload.github.com/$GH_REPO/tar.gz/refs/heads/$GH_REF" -o "$tmp/tree.tgz" 2>/dev/null; then
    if tar xzf "$tmp/tree.tgz" -C "$tmp" --strip-components=1 "*/native/animatica-native.tar.gz" 2>/dev/null; then
      mv "$tmp/native/animatica-native.tar.gz" "$out" && rm -rf "$tmp" && return 0
    fi
  fi
  rm -rf "$tmp"
  return 1
}

if [ "$LIB_READY" = "1" ]; then
  say "[1/4] cairo/pango: already installed"
elif [ "$DO_NATIVE" = "0" ]; then
  say "[1/4] cairo/pango: skipped (ANIMATICA_NATIVE=0)"
else
  step "1/4" "cairo/pango (manim needs them; there are no Linux wheels)"
  if install_system_libs; then
    LIB_READY=1
    say "  -> installed from the system package manager"
  else
    say "  -> no usable package manager, fetching a prebuilt bundle instead"
    if fetch_native_bundle "$ROOT/animatica-native.tar.gz"; then
      rm -rf "$ROOT/native"
      mkdir -p "$ROOT/native"
      tar xzf "$ROOT/animatica-native.tar.gz" -C "$ROOT/native"
      rm -f "$ROOT/animatica-native.tar.gz"
      BUNDLE_USED=1
      LIB_READY=1
      say "  -> bundle unpacked into $ROOT/native (no shell setup needed)"
    else
      say "  !! could not get cairo/pango; manim renders will fail."
      say "     Retry with ANIMATICA_NATIVE_URL=<tar.gz> or install libcairo2-dev + libpango1.0-dev."
    fi
  fi
fi

[ "$MODE" = "native" ] && { say "\nNative dependency step finished."; exit 0; }

# --------------------------------------------------------------------------- #
# 2. python env + animatica
# --------------------------------------------------------------------------- #
step "2/4" "python environment"
if have uv; then
  :
else
  say "  installing uv (fast installer, no sudo needed)"
  curl -fsSL https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
  export PATH="$HOME/.local/bin:$PATH"
fi

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif have uv; then
  uv venv "$ROOT/.venv" >/dev/null
  PY="$ROOT/.venv/bin/python"
else
  python3 -m venv "$ROOT/.venv"
  PY="$ROOT/.venv/bin/python"
fi
say "  -> $PY"

# uv venvs ship without pip; add it so `pip install <extra>` works for the user too.
"$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true

pip_install() {
  if have uv; then uv pip install --python "$PY" "$@"; else "$PY" -m pip install -q "$@"; fi
}

if [ "$BUNDLE_USED" = "1" ]; then
  # Install the prebuilt extensions first: pip then sees them as satisfied and
  # never tries to compile pycairo/manimpango against missing headers.
  pip_install --no-deps "$ROOT"/native/wheels/*.whl
fi
say "  installing animatica + manim (this is the slow part, ~1 min)"
pip_install -e "$ROOT"

# --------------------------------------------------------------------------- #
# 3. LaTeX (optional: needed for MathTex, not for text or shapes)
# --------------------------------------------------------------------------- #
if [ "$DO_TEX" = "1" ] && ! have latex; then
  step "3/4" "LaTeX for equations (optional)"
  TEX_DIR="$ROOT/.tex"
  if [ -d "$TEX_DIR/bin" ]; then
    say "  -> already unpacked in $TEX_DIR"
  else
    mkdir -p "$TEX_DIR"
    # 1) the small curated bundle (latex + dvisvgm + the packages Manim uses)
    for asset in animatica-tex.tar.xz tinytex-manim.zip; do
      url="https://github.com/$GH_REPO/releases/latest/download/$asset"
      [ -n "${ANIMATICA_TEX_URL:-}" ] && url="$ANIMATICA_TEX_URL"
      if curl -fsSL --max-time 600 "$url" -o "/tmp/$asset" 2>/dev/null; then
        say "  -> downloaded $asset"
        case "$asset" in
          *.tar.xz)
            tar xf "/tmp/$asset" -C "$TEX_DIR" 2>/dev/null ||
              (cd "$TEX_DIR" && "$PY" -m tarfile -e "/tmp/$asset" .) 2>/dev/null || true
            ;;
          *.zip)
            (cd "$TEX_DIR" && "$PY" -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall('.')" "/tmp/$asset") 2>/dev/null || true
            ;;
        esac
        [ -d "$TEX_DIR/bin" ] && break
      fi
    done
    if [ -d "$TEX_DIR/bin" ]; then
      say "  -> TeX unpacked in $TEX_DIR (animatica finds it automatically)"
    else
      say "  -> skipped; equations will warn. Text and shapes render fine."
      say "     Add it later with: animatica doctor --fix"
    fi
  fi
else
  step "3/4" "LaTeX: not needed / already installed"
fi

# --------------------------------------------------------------------------- #
# 4. verify
# --------------------------------------------------------------------------- #
step "4/4" "verifying"
export PATH="$ROOT/.venv/bin:$PATH"
DOCTOR_OUT="$("$ROOT/.venv/bin/animatica" doctor 2>&1 || true)"
printf '%s\n' "$DOCTOR_OUT"
# LaTeX is optional (equations only): a missing TeX must not fail the setup.
# pipefail: grep exits 1 when it filters everything, so every stage tolerates that
FAIL_LINES="$(printf '%s\n' "$DOCTOR_OUT" | grep '^\[FAIL\]' || true)"
REQUIRED_FAILS=0
if [ -n "$FAIL_LINES" ]; then
  REQUIRED_FAILS="$(printf '%s\n' "$FAIL_LINES" | grep -v 'latex' | wc -l | tr -d ' ' || true)"
fi
if [ "${REQUIRED_FAILS:-1}" = "0" ]; then
  if printf '%s\n' "$DOCTOR_OUT" | grep -q '^\[FAIL\] latex' || true; then
    say ""
    say "Note: LaTeX is missing, so MathTex/equation scenes will warn."
    say "      Text, shapes, charts and everything else render fine."
    say "      Add it later with: animatica doctor --fix"
  fi
  cat <<'EOF'

Ready. Two commands from here:

  animatica tui                 # do everything, and set your defaults, here
  animatica make "graph of sin(x)" -o out/

`animatica tui` is the place to tweak quality, theme, provider and API keys:
pick with the arrow keys or start typing to filter the list. Nothing else to
configure and no environment variables to export.
EOF
else
  say ""
  say "Some checks failed (see the FAIL lines above). Re-run this script, or:"
  say "  $ROOT/.venv/bin/animatica doctor --fix --yes"
  exit 1
fi
