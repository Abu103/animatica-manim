#!/bin/sh
# Build the relocatable sandbox runtime that scripts/sandbox.sh fetches.
#
#   sh scripts/build_runtime.sh OUTDIR                 full build (CI: Debian 12 container)
#   sh scripts/build_runtime.sh --pack-only STAGE OUTDIR   pack an existing stage dir (tests)
#   sh scripts/build_runtime.sh --closure STAGE            bundle the shared libraries the native libs need
#
# The runtime is a standalone CPython (python-build-standalone) with every
# dependency from pyproject.toml (including the test and TUI extras, the same
# list runtime_key.sh hashes) installed into it, plus the cairo/pango shared
# libraries (with everything they link against except glibc's own), the DejaVu
# fonts and a fontconfig file that uses only those, laid out as
#   python/   native/lib/   native/fonts/   native/etc/fonts.conf
# OUTDIR receives animatica-runtime-<key>.tar.gz, part-NN (each below
# ANIMATICA_PART_BYTES, GitHub's file limit is 100 MB) and SHA256SUMS.
#
# A full build needs, on the build host: build-essential pkg-config curl and the
# cairo/pango -dev and runtime packages (see .github/workflows/sandbox-runtime.yml).
set -eu

here="$(cd "$(dirname "$0")" && pwd)"

# Pinned: bump these three together, they are the only third-party artifact.
PBS_TAG=20261110
PBS_PYTHON=3.12.16
PBS_SHA256=c2f87d4b4e8db3abddb0f116c6ccfc503d0cbdbb9ee8faacddad1b679ec12e99
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG/cpython-$PBS_PYTHON+$PBS_TAG-x86_64-unknown-linux-gnu-install_only.tar.gz"

PART_BYTES="${ANIMATICA_PART_BYTES:-95000000}"
NATIVE_LIBS="cairo pixman-1 png16 Xrender Xext Xau Xdmcp lzo2 pango-1.0 pangoft2-1.0 pangocairo-1.0 harfbuzz fribidi thai datrie graphite2 xcb-render xcb-shm"

die() { echo "build_runtime: $*" >&2; exit 1; }

# closure STAGE: copy into native/lib every shared library the bundled native libs and the
# cairo/pango Python extensions resolve from the host (glib, fontconfig, freetype, libX11, zlib...),
# so a machine with only curl, tar and sh can load them. glibc and the compiler runtime stay with
# the host: they are the platform the runtime targets (glibc >= 2.36). Safe to run twice.
CORE_LIBS='^(libc\.so|libm\.so|libpthread|libdl|librt|libutil|libresolv|ld-linux|linux-vdso|libgcc_s|libstdc\+\+)'
closure() {
  command -v ldd >/dev/null 2>&1 || die "ldd is needed to compute the library closure"
  lib="$1/native/lib"
  [ -d "$lib" ] || die "stage has no native/lib: $1"
  list="$(mktemp)"
  pass=0; total=0
  while [ "$pass" -lt 3 ]; do
    pass=$((pass + 1)); added=0
    { find "$lib" -maxdepth 1 -name '*.so*' ; \
      find "$1/python" \( -name '*cairo*.so' -o -name '*manimpango*.so' -o -name 'libpango*.so*' \) -type f 2>/dev/null; } > "$list"
    while IFS= read -r f; do
      LD_LIBRARY_PATH="$lib" ldd "$f" 2>/dev/null | awk '$3 ~ /^\// { print $1, $3 }'
    done < "$list" | sort -u | while read -r name path; do
      printf '%s\n' "$name" | grep -Eq "$CORE_LIBS" && continue
      [ -e "$lib/$name" ] && continue
      cp -aL "$path" "$lib/$name" && echo "closure: $name"
    done > "$list.new"
    if [ -s "$list.new" ]; then added=1; total=$((total + $(wc -l < "$list.new"))); fi
    rm -f "$list.new"
    [ "$added" = "1" ] || break
  done
  rm -f "$list"
  echo "closure: $total librar$([ "$total" = 1 ] && echo y || echo ies) added to native/lib"
}

pack() {  # STAGE OUTDIR
  [ -x "$1/python/bin/python3" ] || die "stage has no python/bin/python3: $1"
  [ -d "$1/native" ] || die "stage has no native/ directory: $1"
  key="$(sh "$here/runtime_key.sh" "$here/../pyproject.toml")"
  name="animatica-runtime-$key.tar.gz"
  mkdir -p "$2"
  rm -f "$2"/part-* "$2/SHA256SUMS" "$2/$name"
  entries="$(ls -A "$1")"
  # shellcheck disable=SC2086  # entry names have no spaces; the list is the stage's top level
  tar czf "$2/$name" -C "$1" $entries
  split -b "$PART_BYTES" -d -a 2 "$2/$name" "$2/part-"
  ( cd "$2" && sha256sum part-* "$name" > SHA256SUMS )
  echo "packed $name: $(ls "$2"/part-* | wc -l | tr -d ' ') part(s), key $key"
}

if [ "${1:-}" = "--closure" ]; then
  [ $# -eq 2 ] || die "usage: build_runtime.sh --closure STAGE"
  closure "$2"
  exit 0
fi

if [ "${1:-}" = "--pack-only" ]; then
  [ $# -eq 3 ] || die "usage: build_runtime.sh --pack-only STAGE OUTDIR"
  pack "$2" "$3"
  exit 0
fi

[ $# -eq 1 ] || die "usage: build_runtime.sh OUTDIR | --pack-only STAGE OUTDIR"
out="$1"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
stage="$work/stage"
mkdir -p "$stage/native/lib"

echo "== standalone Python $PBS_PYTHON ($PBS_TAG)"
curl -fsSL --retry 3 "$PBS_URL" -o "$work/python.tar.gz"
got="$(sha256sum "$work/python.tar.gz" | cut -d' ' -f1)"
[ "$got" = "$PBS_SHA256" ] || die "python-build-standalone checksum mismatch: $got"
tar xzf "$work/python.tar.gz" -C "$stage"
py="$stage/python/bin/python3"
[ -x "$stage/python/bin/python" ] || ln -s python3 "$stage/python/bin/python"

echo "== dependencies (pyproject.toml, including the test and TUI extras)"
sh "$here/runtime_key.sh" --deps "$here/../pyproject.toml" > "$work/requirements.txt"
# python-build-standalone records CC=clang, which the build host does not have; gcc is installed.
CC="${CC:-gcc}" CXX="${CXX:-g++}" "$py" -m pip install --no-cache-dir -q -r "$work/requirements.txt"

echo "== cairo and pango shared libraries"
libdir="${ANIMATICA_NATIVE_SRC:-/usr/lib/x86_64-linux-gnu}"
for lib in $NATIVE_LIBS; do
  cp -aL "$libdir"/lib"$lib".so* "$stage/native/lib/" 2>/dev/null || true
done
[ -e "$stage/native/lib/libcairo.so.2" ] || die "libcairo.so.2 is missing from $libdir"
[ -e "$stage/native/lib/libpango-1.0.so.0" ] || die "libpango-1.0.so.0 is missing from $libdir"

echo "== shared libraries the native libs link against (glib, fontconfig, freetype, X, zlib, ...)"
closure "$stage"

echo "== DejaVu fonts and a fontconfig file that uses only them"
fontdir="${ANIMATICA_FONT_SRC:-/usr/share/fonts/truetype/dejavu}"
mkdir -p "$stage/native/fonts" "$stage/native/etc"
for f in DejaVuSans.ttf DejaVuSans-Bold.ttf DejaVuSans-Oblique.ttf DejaVuSans-BoldOblique.ttf DejaVuSansMono.ttf DejaVuSansMono-Bold.ttf DejaVuSerif.ttf DejaVuSerif-Bold.ttf; do
  [ -f "$fontdir/$f" ] && cp "$fontdir/$f" "$stage/native/fonts/"
done
[ -f "$stage/native/fonts/DejaVuSans.ttf" ] || die "DejaVuSans.ttf is missing from $fontdir (apt: fonts-dejavu-core)"
cp "$here/sandbox_fonts.conf" "$stage/native/etc/fonts.conf"

echo "== making the tree relocatable and smaller"
# pip writes absolute shebangs into console scripts; point them at whichever python is first on PATH
for f in "$stage"/python/bin/*; do
  [ -f "$f" ] && [ ! -L "$f" ] || continue
  if head -c 2 "$f" | grep -q '^#!' && head -n 1 "$f" | grep -q "$stage"; then
    sed -i "1s|^#!.*|#!/usr/bin/env python3|" "$f"
  fi
done
rm -rf "$stage"/python/lib/python3.*/test
find "$stage/python/lib" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + 2>/dev/null || true

echo "== import check"
LD_LIBRARY_PATH="$stage/native/lib" "$py" -c "import manim, cairo, manimpango, av, numpy, pydantic, typer, httpx, mcp, pytest, textual; print('imports ok')"

echo "== a real render on the bundled libraries and fonts alone"
# Environment cleared: no system fontconfig, no host library path, only what ships in the runtime.
smoke="$work/smoke"; mkdir -p "$smoke"
env -i HOME="$smoke" PATH="$stage/python/bin:/usr/bin:/bin" LD_LIBRARY_PATH="$stage/native/lib" \
  FONTCONFIG_FILE="$stage/native/etc/fonts.conf" PYTHONPATH="$here/../src" \
  "$py" -m animatica make "bar chart of sales by quarter" -o "$smoke/out" --preview >"$smoke/log" 2>&1 \
  && [ -s "$smoke/out/video.mp4" ] || { tail -n 15 "$smoke/log" >&2; die "the smoke render failed on the bundled runtime"; }
echo "render ok"

pack "$stage" "$out"
