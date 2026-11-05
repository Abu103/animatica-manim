#!/usr/bin/env bash
# Animatica fast full-quality bootstrap (~25-40s on a normal connection).
# Self-contained: installs uv if missing, installs Python deps and downloads the
# pre-baked TinyTeX zip IN PARALLEL, then verifies with animatica doctor.
# Usage: curl -fsSL <raw>/scripts/bootstrap.sh | bash
set -euo pipefail
GH_REPO="${ANIMATICA_GH_REPO:-Abu103/animatica-manim}"
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/../src/animatica/__init__.py" ]; then
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
else
  # piped via curl|bash: clone into ~/animatica-manim
  ROOT="$HOME/animatica-manim"
  [ -f "$ROOT/src/animatica/__init__.py" ] || git clone "https://github.com/$GH_REPO.git" "$ROOT"
  cd "$ROOT"
fi
ROOT="$PWD"
TINYTEX_ZIP_URL="${ANIMATICA_TINYTEX_URL:-}"
TINYTEX_DIR="$ROOT/.tex"

# --- 0. uv (10s if missing) ---
if ! command -v uv >/dev/null 2>&1; then
  echo "[0/3] installing uv"
  curl -fsSL https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- 1+2 in parallel: python deps | pre-baked TinyTeX ---
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  uv venv "$ROOT/.venv"
fi
uv pip install --python "$ROOT/.venv/bin/python" -e "$ROOT" &
PIP_PID=$!

TEX_OK=0
fetch_tex() {
  # 1) explicit URL (public repo or signed URL), 2) gh CLI (works for PRIVATE repos
  #    when the user is logged in), 3) GITHUB_TOKEN against the API
  if [ -n "$TINYTEX_ZIP_URL" ]; then
    curl -fsSL --max-time 120 "$TINYTEX_ZIP_URL" -o /tmp/tinytex-manim.zip && return 0
  fi
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh release download --repo "$GH_REPO" --pattern tinytex-manim.zip -O /tmp/tinytex-manim.zip 2>/dev/null && return 0
  fi
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/octet-stream" \
      "https://api.github.com/repos/$GH_REPO/releases/latest/assets?per_page=100" >/dev/null 2>&1 || true
    url=$(curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/$GH_REPO/releases/latest" | grep -o '"browser_download_url": *"[^"]*tinytex-manim.zip"' | cut -d'"' -f4)
    [ -n "$url" ] && curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -L "$url" -o /tmp/tinytex-manim.zip && return 0
  fi
  return 1
}
fetch_tex && TEX_OK=1 &
TEX_PID=$!

wait "$PIP_PID"
if wait $TEX_PID; then TEX_OK=1; fi

if [ "$TEX_OK" = "1" ]; then
  mkdir -p "$TINYTEX_DIR" && unzip -oq /tmp/tinytex-manim.zip -d "$TINYTEX_DIR"
  TEX_BIN=$(ls -d "$TINYTEX_DIR"/bin/*/ 2>/dev/null | head -1 || true)
  if [ -z "$TEX_BIN" ]; then
    echo "TinyTeX archive has no bin directory" >&2
    exit 1
  fi
  export PATH="$TEX_BIN:$PATH"
  echo "[2/3] TinyTeX available in this bootstrap process at $TEX_BIN"
  echo "      for future shells, add to PATH: $TEX_BIN"
else
  echo "[2/3] pre-baked TinyTeX zip unavailable (release not published?) -- falling back to doctor --fix"
  # --yes: no prompt (stdin is the script itself under curl|bash). Failures are caught by the final check.
  "$ROOT/.venv/bin/animatica" doctor --fix --yes || true
fi

echo "[3/3] verifying"
if "$ROOT/.venv/bin/animatica" doctor; then
  echo ""
  echo "Done. Then: source .venv/bin/activate && animatica make \"graph of sin(x)\" -o out/"
else
  echo ""
  echo "Setup is NOT complete: see the FAIL lines above (re-run after fixing them)." >&2
  exit 1
fi
