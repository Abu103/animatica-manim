#!/usr/bin/env bash
# Animatica one-command setup.
#
#   curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
#
# Gets you from a bare machine to a working render: Python + Manim, cairo/pango
# (system packages or a prebuilt bundle), ffmpeg, and optional LaTeX. After
# verification, it opens `animatica setup` on an interactive terminal. Use
# ANIMATICA_SKIP_SETUP=1 for unattended installs; then run the printed command.
#
# Environment (all optional):
#   ANIMATICA_HOME        where to put the checkout        (default ~/animatica-manim)
#   ANIMATICA_REF         git branch/tag to install        (default main)
#   ANIMATICA_NATIVE_URL  tar.gz with wheels/ + lib/       (default: repo release)
#   ANIMATICA_TEX=0       skip the LaTeX (TinyTeX) step
#   ANIMATICA_NATIVE=0    never touch cairo/pango
#   ANIMATICA_SKIP_SETUP=1 install only; do not launch the setup wizard
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

# If the caller points us at an old existing checkout, switch that clean checkout to
# the requested ref before installing. Never overwrite local edits or unpushed commits.
sync_existing_checkout() {
  if [ ! -e "$ROOT/.git" ]; then
    say "ERROR: $ROOT is not a Git checkout, so I cannot safely update it to $GH_REF."
    say "Use a fresh folder, for example: ANIMATICA_HOME=\"$HOME/animatica-manim-test\""
    return 1
  fi
  if ! have git; then
    say "ERROR: Git is needed to update the existing checkout at $ROOT."
    say "Use a fresh folder with Git installed, or set ANIMATICA_HOME to another path."
    return 1
  fi

  local status remote_ref
  if ! status="$(git -C "$ROOT" status --porcelain 2>/dev/null)"; then
    say "ERROR: could not inspect the existing checkout at $ROOT."
    return 1
  fi
  if [ -n "$status" ]; then
    say "ERROR: $ROOT has local changes; I will not switch branches or overwrite them."
    say "For a safe test, set ANIMATICA_HOME to a new folder and rerun this installer."
    return 1
  fi

  remote_ref="refs/remotes/origin/$GH_REF"
  if git -C "$ROOT" fetch -q origin "+refs/heads/$GH_REF:$remote_ref" 2>/dev/null; then
    if git -C "$ROOT" show-ref --quiet --verify "refs/heads/$GH_REF"; then
      if ! git -C "$ROOT" merge-base --is-ancestor "refs/heads/$GH_REF" "$remote_ref" 2>/dev/null; then
        say "ERROR: local branch $GH_REF has commits not on origin; I will not discard them."
        say "For a safe test, set ANIMATICA_HOME to a new folder and rerun this installer."
        return 1
      fi
      git -C "$ROOT" checkout -q "$GH_REF" || return 1
      git -C "$ROOT" merge --ff-only -q "$remote_ref" || return 1
    else
      git -C "$ROOT" checkout -q --track -b "$GH_REF" "$remote_ref" || return 1
    fi
  elif git -C "$ROOT" fetch -q origin "refs/tags/$GH_REF:refs/tags/$GH_REF" 2>/dev/null; then
    git -C "$ROOT" checkout -q --detach "refs/tags/$GH_REF" || return 1
  else
    say "ERROR: could not fetch branch or tag '$GH_REF' from origin."
    say "Check the ref/network, or use a fresh ANIMATICA_HOME folder."
    return 1
  fi

  say "  -> $(git -C "$ROOT" rev-parse --abbrev-ref HEAD) @ $(git -C "$ROOT" rev-parse --short HEAD)"
}

USE_EXISTING_ROOT=0
if [ -n "$self_dir" ] && [ -f "$self_dir/../src/animatica/__init__.py" ]; then
  ROOT="$(cd "$self_dir/.." && pwd)"
  say "Using the checkout at $ROOT"
elif [ -f "$ROOT/src/animatica/__init__.py" ]; then
  USE_EXISTING_ROOT=1
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
if [ "$USE_EXISTING_ROOT" = "1" ]; then
  sync_existing_checkout
fi

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
  # hosted hosts that can only reach codeload: the `artifacts` branch carries the
  # bundles as plain files, so no release CDN or API token is involved.
  local tmp; tmp="$(mktemp -d)"
  for branch in "${ANIMATICA_ARTIFACT_BRANCH:-artifacts}" "$GH_REF"; do
    if curl -fsSL --max-time 240 \
         "https://codeload.github.com/$GH_REPO/tar.gz/refs/heads/$branch" -o "$tmp/tree.tgz" 2>/dev/null; then
      if tar xzf "$tmp/tree.tgz" -C "$tmp" --strip-components=0 --wildcards \
           "*/native/animatica-native.tar.gz" 2>/dev/null; then
        found=$(find "$tmp" -name animatica-native.tar.gz -type f | head -1)
        if [ -n "$found" ]; then mv "$found" "$out" && rm -rf "$tmp" && return 0; fi
      fi
    fi
  done
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
say "  installing animatica + manim + TUI (this is the slow part, ~1 min)"
pip_install -e ".[tui]"

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
    # codeload-only hosts: the same bundle, committed to the artifacts branch
    if [ ! -d "$TEX_DIR/bin" ]; then
      tmp="$(mktemp -d)"
      if curl -fsSL --max-time 600 \
           "https://codeload.github.com/$GH_REPO/tar.gz/refs/heads/${ANIMATICA_ARTIFACT_BRANCH:-artifacts}" \
           -o "$tmp/art.tgz" 2>/dev/null; then
        tar xzf "$tmp/art.tgz" -C "$tmp" --wildcards "*/native/animatica-tex.tar.xz" 2>/dev/null || true
        found=$(find "$tmp" -name animatica-tex.tar.xz -type f | head -1)
        if [ -n "$found" ]; then
          say "  -> downloaded animatica-tex.tar.xz from the artifacts branch"
          tar xf "$found" -C "$TEX_DIR" 2>/dev/null || true
        fi
      fi
      rm -rf "$tmp"
    fi
    if [ -d "$TEX_DIR/bin" ]; then
      say "  -> TeX unpacked in $TEX_DIR (animatica finds it automatically)"
      # The bundle carries most of what Manim needs but not all of it:
      # standalone.cls loads varwidth for its border box, and without it every
      # formula fails to compile and the equations degrade to plain text. The
      # doctor knows the full list; ask its tlmgr for the rest.
      for tlmgr in "$TEX_DIR"/bin/*/tlmgr; do
        [ -x "$tlmgr" ] || continue
        PKGS="$("$PY" -c \
          'from animatica.doctor import TEX_PACKAGES; print(" ".join(TEX_PACKAGES))' \
          2>/dev/null || true)"
        if [ -n "$PKGS" ]; then
          say "  -> completing the TeX packages (tlmgr install $PKGS)"
          "$tlmgr" install $PKGS >/dev/null 2>&1 || \
            say "  -> tlmgr could not install every package; run 'animatica doctor --fix' later"
        fi
        break
      done
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
  say ""
  say "Install complete and verified."
  if [ "${ANIMATICA_SKIP_SETUP:-0}" = "1" ]; then
    say "Interactive setup skipped (ANIMATICA_SKIP_SETUP=1)."
    say "Run this when ready: $ROOT/.venv/bin/animatica setup"
  elif [ -z "${CI:-}" ] && [ -z "${GITHUB_ACTIONS:-}" ] && [ -t 1 ] \
      && ( : </dev/tty ) 2>/dev/null; then
    say "Starting Animatica setup. Choose Template for offline examples, or an AI provider."
    if "$ROOT/.venv/bin/animatica" setup </dev/tty; then
      say ""
      say "Setup complete. Open Animatica Studio with:"
      say "  $ROOT/.venv/bin/animatica tui"
    else
      setup_status=$?
      say "Setup wizard exited with status $setup_status. The install is complete; rerun:"
      say "  $ROOT/.venv/bin/animatica setup"
      exit "$setup_status"
    fi
  else
    say "No interactive terminal detected; install is ready."
    say "Run this in a terminal to configure your provider:"
    say "  $ROOT/.venv/bin/animatica setup"
  fi
else
  say ""
  say "Some checks failed (see the FAIL lines above). Re-run this script, or:"
  say "  $ROOT/.venv/bin/animatica doctor --fix --yes"
  exit 1
fi
