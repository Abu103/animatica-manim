#!/bin/sh
# Print the 12-hex key of the sandbox runtime a checkout needs.
#
#   sh scripts/runtime_key.sh [PYPROJECT]        (default: ../pyproject.toml)
#
# key = sha256(sorted, normalised [project] dependencies + python minor + platform)
# One implementation, called by scripts/sandbox.sh and by the runtime workflow, so
# the key the runtime was published under is the key the checkout asks for.
#
# Environment: ANIMATICA_RT_PYTHON (default 3.12), ANIMATICA_RT_PLATFORM (default
# linux-x86_64). Needs only POSIX sh, awk, sort and one of sha256sum, shasum, openssl.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
pyproject="${1:-$here/../pyproject.toml}"
py="${ANIMATICA_RT_PYTHON:-3.12}"
plat="${ANIMATICA_RT_PLATFORM:-linux-x86_64}"

[ -f "$pyproject" ] || { echo "runtime_key: no such file: $pyproject" >&2; exit 2; }

sha256_stdin() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 | cut -d' ' -f1
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 | sed 's/^.*= *//'
  else echo "runtime_key: no sha256 tool (sha256sum, shasum, openssl)" >&2; return 1
  fi
}

deps="$(awk '
  /^\[/ { in_project = ($0 == "[project]"); next }
  in_project && /^dependencies[ \t]*=[ \t]*\[/ { grab = 1; next }
  grab && /^[ \t]*\][ \t]*(#.*)?$/ { grab = 0; next }
  grab {
    line = $0
    sub(/[ \t]*#.*$/, "", line)          # comments
    gsub(/^[ \t]+|[ \t]+$/, "", line)    # outer whitespace
    sub(/,$/, "", line)                  # trailing comma
    if (line != "") print line
  }
' "$pyproject" | LC_ALL=C sort)"

[ -n "$deps" ] || { echo "runtime_key: no [project] dependencies found in $pyproject" >&2; exit 1; }

printf '%s\npython=%s\nplatform=%s\n' "$deps" "$py" "$plat" | sha256_stdin | cut -c1-12
