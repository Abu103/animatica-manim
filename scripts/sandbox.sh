#!/bin/sh
# Animatica one-command sandbox setup: from a bare machine (curl, tar, sh) to a
# working checkout in under a minute. See
# docs/superpowers/specs/2026-11-12-sandbox-bootstrap-design.md
#
#   curl -fsSL https://codeload.github.com/Abu103/animatica-manim/tar.gz/refs/heads/main | tar xz \
#     && sh animatica-manim-main/scripts/sandbox.sh
#
# Runtime fetch order, each step with its own timeout:
#   1. release asset            runtime-<key>/animatica-runtime-<key>.tar.gz
#   2. codeload branch parts    runtime-<key>  (part-NN + SHA256SUMS)
#   3. newest published runtime runtime-latest (+ pip repair when PyPI answers)
#   4. scripts/bootstrap.sh     unchanged, the last resort
#
# Environment (all optional): ANIMATICA_GH_REPO, ANIMATICA_REF, ANIMATICA_HOME,
# ANIMATICA_RELEASE_BASE, ANIMATICA_CODELOAD_BASE, ANIMATICA_BOOTSTRAP,
# ANIMATICA_BUDGET_S, ANIMATICA_PIP_CMD, ANIMATICA_PYPI_URL, ANIMATICA_CURL_TIMEOUT.
# Needs only POSIX sh, curl, tar, awk, sed, cut, sort and one sha256 tool.

GH_REPO="${ANIMATICA_GH_REPO:-Abu103/animatica-manim}"
GH_REF="${ANIMATICA_REF:-main}"
REL_BASE="${ANIMATICA_RELEASE_BASE:-https://github.com/$GH_REPO/releases/download}"
CODELOAD_BASE="${ANIMATICA_CODELOAD_BASE:-https://codeload.github.com/$GH_REPO}"
CURL_TIMEOUT="${ANIMATICA_CURL_TIMEOUT:-240}"
HERE="${ANIMATICA_SANDBOX_DIR:-$(cd "$(dirname "$0")" && pwd)}"

say() { printf '%s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }

# --------------------------------------------------------------------------- #
# checksums
# --------------------------------------------------------------------------- #
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 "$1" | sed 's/^.*= *//'
  else return 1
  fi
}

# verify_sum SUMSFILE NAME FILE: FILE must hash to the value SUMSFILE lists for NAME.
verify_sum() {
  _want="$(awk -v n="$2" '$2 == n || $2 == "*" n { print $1; exit }' "$1")"
  _got="$(sha256_of "$3")" || return 1
  [ -n "$_want" ] && [ "$_want" = "$_got" ]
}

fetch() { curl -fsSL --max-time "$CURL_TIMEOUT" "$1" -o "$2" 2>/dev/null; }

# --------------------------------------------------------------------------- #
# platform: the runtime is Linux x86_64, glibc >= 2.36
# --------------------------------------------------------------------------- #
platform_ok() {
  [ "${ANIMATICA_RT_FORCE_PLATFORM_OK:-0}" = "1" ] && return 0
  _os="$(uname -s 2>/dev/null)"
  _m="${ANIMATICA_RT_UNAME_M:-$(uname -m 2>/dev/null)}"
  [ "$_os" = "Linux" ] || { say "platform: $_os is not supported by the fast path"; return 1; }
  [ "$_m" = "x86_64" ] || { say "platform: $_m is not supported by the fast path (needs x86_64)"; return 1; }
  if [ "${ANIMATICA_RT_GLIBC+set}" = "set" ]; then _g="$ANIMATICA_RT_GLIBC"
  else _g="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"; fi
  [ -n "$_g" ] || { say "platform: no glibc found (musl?); the fast path needs glibc >= 2.36"; return 1; }
  if ! printf '%s\n' "$_g" | awk -F. '{ exit !($1 > 2 || ($1 == 2 && $2 >= 36)) }'; then
    say "platform: glibc $_g is older than 2.36"; return 1
  fi
  return 0
}

# --------------------------------------------------------------------------- #
# runtime sources. Each _try_* leaves a verified archive at $2 or fails.
# --------------------------------------------------------------------------- #
_try_release() {  # KEY OUT
  _d="$_RT_TMP/rel-$1"; mkdir -p "$_d"
  _n="animatica-runtime-$1.tar.gz"
  fetch "$REL_BASE/runtime-$1/SHA256SUMS" "$_d/SHA256SUMS" || return 1
  fetch "$REL_BASE/runtime-$1/$_n" "$_d/$_n" || return 1
  verify_sum "$_d/SHA256SUMS" "$_n" "$_d/$_n" || { say "release $1: checksum mismatch"; return 1; }
  mv "$_d/$_n" "$2"
}

_try_branch() {  # KEY OUT
  _d="$_RT_TMP/br-$1"; mkdir -p "$_d/x"
  _n="animatica-runtime-$1.tar.gz"
  fetch "$CODELOAD_BASE/tar.gz/refs/heads/runtime-$1" "$_d/tree.tgz" || return 1
  tar xzf "$_d/tree.tgz" -C "$_d/x" --strip-components=1 2>/dev/null || return 1
  [ -f "$_d/x/SHA256SUMS" ] || return 1
  : > "$_d/joined"
  for _p in "$_d"/x/part-*; do
    [ -f "$_p" ] || return 1
    verify_sum "$_d/x/SHA256SUMS" "$(basename "$_p")" "$_p" || { say "branch $1: bad part $(basename "$_p")"; return 1; }
    cat "$_p" >> "$_d/joined"
  done
  verify_sum "$_d/x/SHA256SUMS" "$_n" "$_d/joined" || { say "branch $1: joined archive checksum mismatch"; return 1; }
  mv "$_d/joined" "$2"
}

# unpack ARCHIVE DEST: unpack beside DEST and rename, so DEST is never half-written.
unpack() {
  rm -rf "$2.tmp"; mkdir -p "$2.tmp"
  if tar xzf "$1" -C "$2.tmp" 2>/dev/null; then
    rm -rf "$2"; mv "$2.tmp" "$2"
  else
    rm -rf "$2.tmp"; return 1
  fi
}

_try_key() {  # KEY DEST -> prints source=release|branch on success
  _a="$_RT_TMP/archive-$1.tar.gz"
  if _try_release "$1" "$_a" && unpack "$_a" "$2"; then RT_USED_KEY="$1"; say "source=release key=$1"; return 0; fi
  rm -f "$_a"
  if _try_branch "$1" "$_a" && unpack "$_a" "$2"; then RT_USED_KEY="$1"; say "source=branch key=$1"; return 0; fi
  return 1
}

pip_repair() {  # DEST
  _pypi="${ANIMATICA_PYPI_URL:-https://pypi.org/simple/}"
  curl -fs --max-time 5 -o /dev/null "$_pypi" 2>/dev/null || return 1
  RT_DEST="$1"; RT_DEPS="$_RT_TMP/deps.txt"
  sh "$HERE/runtime_key.sh" --deps "$HERE/../pyproject.toml" > "$RT_DEPS" 2>/dev/null || return 1
  export RT_DEST RT_DEPS
  if [ -n "${ANIMATICA_PIP_CMD:-}" ]; then eval "$ANIMATICA_PIP_CMD"
  else "$1/python/bin/python3" -m pip install -q -r "$RT_DEPS"
  fi
}

# fetch_runtime KEY DEST: 0 with DEST populated, or nonzero with nothing left behind.
fetch_runtime() {
  platform_ok || return 1
  _RT_TMP="$(mktemp -d)" || return 1
  RT_DEGRADED=0
  _rc=1
  if _try_key "$1" "$2"; then _rc=0
  else
    _latest=""
    if fetch "$CODELOAD_BASE/tar.gz/refs/heads/runtime-latest" "$_RT_TMP/latest.tgz" \
       && mkdir -p "$_RT_TMP/latest" && tar xzf "$_RT_TMP/latest.tgz" -C "$_RT_TMP/latest" --strip-components=1 2>/dev/null; then
      _latest="$(tr -d ' \r\n' < "$_RT_TMP/latest/KEY" 2>/dev/null)"
    fi
    if [ -n "$_latest" ] && [ "$_latest" != "$1" ] && _try_key "$_latest" "$2"; then
      say "source=latest key=$_latest"
      RT_DEGRADED=1
      if pip_repair "$2"; then say "runtime repaired with pip against the current dependency list"
      else warn "runtime $_latest was used because $1 is not published yet; dependencies may be out of date"
      fi
      _rc=0
    fi
  fi
  rm -rf "$_RT_TMP"
  return $_rc
}

# --------------------------------------------------------------------------- #
# code layer: the checkout itself, always live
# --------------------------------------------------------------------------- #
GIT_IDENT="-c user.name=animatica-sandbox -c user.email=sandbox@localhost"

_exclude_runtime_files() {  # ROOT: keep `git status` clean
  [ -d "$1/.git" ] || return 0
  mkdir -p "$1/.git/info"
  for _e in ".animatica-runtime/" ".animatica-env" ".tex/" ".tex.log" ".superpowers/"; do
    grep -qxF "$_e" "$1/.git/info/exclude" 2>/dev/null || printf '%s\n' "$_e" >> "$1/.git/info/exclude"
  done
}

# fetch_code ROOT: ROOT already holds the extracted tree. Never touches its files.
fetch_code() {
  command -v git >/dev/null 2>&1 || { say "code: git not found; using the extracted tree as is"; return 0; }
  if [ -e "$1/.git" ]; then _exclude_runtime_files "$1"; say "code: existing git checkout kept as is"; return 0; fi
  _url="${ANIMATICA_GIT_URL:-https://github.com/$GH_REPO.git}"
  _gt="$(mktemp -d)" || return 0
  if GIT_TERMINAL_PROMPT=0 GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=15 \
       git clone -q --depth 1 --branch "$GH_REF" "$_url" "$_gt/c" >/dev/null 2>&1; then
    mv "$_gt/c/.git" "$1/.git"
    git -C "$1" reset -q >/dev/null 2>&1
    say "code: cloned $GH_REF with history; files left untouched"
  else
    git -C "$1" init -q -b "$GH_REF" >/dev/null 2>&1 || git -C "$1" init -q >/dev/null 2>&1
    git -C "$1" remote add origin "$_url" >/dev/null 2>&1
    _exclude_runtime_files "$1"
    git -C "$1" add -A >/dev/null 2>&1
    git -C "$1" $GIT_IDENT commit -q -m "sandbox snapshot of $GH_REF" >/dev/null 2>&1
    say "code: no git access; local repository created with one snapshot commit"
  fi
  _exclude_runtime_files "$1"
  rm -rf "$_gt"
}

# --------------------------------------------------------------------------- #
# activation
# --------------------------------------------------------------------------- #
shq() { printf "'"; printf '%s' "$1" | sed "s/'/'\\\\''/g"; printf "'"; }

# write_env ROOT: .pth into the runtime's site-packages, the shim, and .animatica-env.
write_env() {
  _rt="$1/.animatica-runtime"
  _sp="$(ls -d "$_rt"/python/lib/python3.*/site-packages 2>/dev/null | head -n 1)"
  [ -n "$_sp" ] || { say "activation: no site-packages in the runtime"; return 1; }
  printf '%s\n' "$1/src" > "$_sp/animatica-src.pth"
  mkdir -p "$_rt/bin"
  {
    printf '#!/bin/sh\nexec '; shq "$_rt/python/bin/python3"; printf ' -m animatica "$@"\n'
  } > "$_rt/bin/animatica"
  chmod +x "$_rt/bin/animatica"
  {
    printf 'export ANIMATICA_HOME=%s\n' "$(shq "$1")"
    printf 'export ANIMATICA_NATIVE_DIR=%s\n' "$(shq "$_rt/native/lib")"
    printf 'export PATH=%s:%s:"$PATH"\n' "$(shq "$_rt/bin")" "$(shq "$_rt/python/bin")"
    printf 'export LD_LIBRARY_PATH=%s${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\n' "$(shq "$_rt/native/lib")"
  } > "$1/.animatica-env"
}

# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
main() {
  RUNTIME_ONLY=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --runtime-only) RUNTIME_ONLY=1 ;;
      --ref) shift; GH_REF="${1:-$GH_REF}" ;;
      *) ;;
    esac
    shift
  done
  ROOT="$(cd "$HERE/.." && pwd)"
  RT="$ROOT/.animatica-runtime"
  [ "$RUNTIME_ONLY" = "1" ] || fetch_code "$ROOT"
  KEY="$(sh "$HERE/runtime_key.sh" "$ROOT/pyproject.toml")" || return 1
  say "runtime key: $KEY"
  if [ -f "$RT/KEY" ] && [ "$(cat "$RT/KEY")" = "$KEY" ]; then
    say "runtime up to date ($KEY)"
  elif RT_USED_KEY=""; fetch_runtime "$KEY" "$RT"; then
    printf '%s\n' "$RT_USED_KEY" > "$RT/KEY"
  elif [ -d "$RT/python" ]; then
    warn "could not fetch runtime $KEY; keeping the one already installed"
  else
    say "no runtime reachable; falling back to scripts/bootstrap.sh"
    BOOT="${ANIMATICA_BOOTSTRAP:-$ROOT/scripts/bootstrap.sh}"
    exec sh "$BOOT"
  fi
  write_env "$ROOT" || return 1
  say "activate with: . $(shq "$ROOT/.animatica-env")"
}

if [ "${ANIMATICA_SANDBOX_SOURCE_ONLY:-0}" != "1" ]; then main "$@"; fi
