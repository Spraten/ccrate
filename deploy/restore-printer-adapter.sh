#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PIN=9fd7af09580c3e710202e5471e77e0b88db0e3bb
SOURCE="$ROOT/work/supvan-cups"
EXAMPLE="$SOURCE/crates/supvan-proto/examples/kiosk-label.rs"
PATCH="$ROOT/deploy/printer-hidraw.patch"
OLD_EXAMPLE_SHA256=1203baa5c09e9e0d1876d208f76c7a5367ec7d676c5b105cfd56d90b977e274a
BUILD_ROOT="$ROOT/work/printer-adapter-build"
BUILT="$BUILD_ROOT/release/examples/kiosk-label"
DEST="$ROOT/work/supvan-cups/target/release/examples/kiosk-label"

missing=""
for tool in cargo rustc pkg-config git; do
  if ! command -v "$tool" >/dev/null 2>&1; then missing="$missing $tool"; fi
done
if [ -n "$missing" ] || ! pkg-config --exists liblzma 2>/dev/null; then
  echo "Printer adapter restore needs system Rust tools and liblzma development files." >&2
  echo "On Debian Trixie, ask an administrator to enable official trixie-backports and run: echo 'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.pgp] http://deb.debian.org/debian trixie-backports main' | sudo tee /etc/apt/sources.list.d/trixie-backports.list && sudo apt update && sudo apt install -t trixie-backports cargo rustc pkg-config liblzma-dev" >&2
  [ -z "$missing" ] || echo "Missing commands:$missing" >&2
  exit 1
fi
rust_version=$(rustc --version | sed -n 's/^rustc \([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1 \2/p')
if [ -z "$rust_version" ]; then
  echo "Could not determine the installed rustc version; adapter build requires Rust 1.88 or newer." >&2
  exit 1
fi
set -- $rust_version
if [ "$1" -lt 1 ] || { [ "$1" -eq 1 ] && [ "$2" -lt 88 ]; }; then
  echo "Installed rustc is too old ($rust_version); adapter build requires Rust 1.88 or newer." >&2
  echo "On Debian Trixie, ask an administrator to enable official trixie-backports and run: echo 'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.pgp] http://deb.debian.org/debian trixie-backports main' | sudo tee /etc/apt/sources.list.d/trixie-backports.list && sudo apt update && sudo apt install -t trixie-backports cargo rustc pkg-config liblzma-dev" >&2
  exit 1
fi
if [ ! -d "$SOURCE/.git" ]; then
  mkdir -p "$ROOT/work"
  git clone https://github.com/heeen/supvan-cups.git "$SOURCE"
fi
status=$(git -C "$SOURCE" status --porcelain --untracked-files=all)
keep_patch=false
if [ -n "$status" ]; then
  example_status="?? crates/supvan-proto/examples/kiosk-label.rs"
  patch_status=" M crates/supvan-proto/src/hidraw.rs"
  example_and_patch="$example_status
$patch_status"
  patch_and_example="$patch_status
$example_status"
  if [ "$status" != "$example_status" ] \
    && [ "$status" != "$patch_status" ] \
    && [ "$status" != "$example_and_patch" ] \
    && [ "$status" != "$patch_and_example" ]; then
    echo "Refusing to change a dirty printer source checkout: $SOURCE" >&2
    exit 1
  fi
  if [ -f "$EXAMPLE" ]; then
    example_sha256=$(sha256sum "$EXAMPLE" | cut -d' ' -f1)
    if [ "$example_sha256" != "$OLD_EXAMPLE_SHA256" ] \
      && ! cmp -s "$EXAMPLE" "$ROOT/deploy/kiosk-label.rs"; then
      echo "Refusing to replace an unknown kiosk-label example: $EXAMPLE" >&2
      exit 1
    fi
  elif [ "$status" = "$example_status" ] || [ "$status" = "$example_and_patch" ] || [ "$status" = "$patch_and_example" ]; then
    echo "Refusing to change a dirty printer source checkout: missing kiosk-label example." >&2
    exit 1
  fi
  if [ "$status" = "$patch_status" ] || [ "$status" = "$example_and_patch" ] || [ "$status" = "$patch_and_example" ]; then
    current_diff=$(git -C "$SOURCE" diff --no-ext-diff --no-color -- crates/supvan-proto/src/hidraw.rs)
    expected_diff=$(cat "$PATCH")
    if [ "$current_diff" != "$expected_diff" ]; then
      echo "Refusing to change a printer source checkout with an unknown hidraw edit: $SOURCE" >&2
      exit 1
    fi
    if [ "$(git -C "$SOURCE" rev-parse HEAD)" != "$PIN" ]; then
      echo "Refusing to change a patched printer checkout at an unexpected revision: $SOURCE" >&2
      exit 1
    fi
    keep_patch=true
  fi
fi
if [ "$keep_patch" != true ]; then
  git -C "$SOURCE" checkout --detach "$PIN"
fi
if [ "$(git -C "$SOURCE" rev-parse HEAD)" != "$PIN" ]; then
  echo "Printer source pin verification failed." >&2
  exit 1
fi
current_diff=$(git -C "$SOURCE" diff --no-ext-diff --no-color -- crates/supvan-proto/src/hidraw.rs)
if [ -z "$current_diff" ]; then
  git -C "$SOURCE" apply --check "$PATCH"
  git -C "$SOURCE" apply "$PATCH"
elif [ "$current_diff" != "$(cat "$PATCH")" ]; then
  echo "Pinned hidraw source has an unexpected modification after checkout." >&2
  exit 1
fi
mkdir -p "$(dirname -- "$EXAMPLE")"
cp "$ROOT/deploy/kiosk-label.rs" "$EXAMPLE"
CARGO_TARGET_DIR="$BUILD_ROOT" cargo build --locked --release -p supvan-proto --example kiosk-label -j2 --manifest-path "$SOURCE/Cargo.toml"
if [ ! -x "$BUILT" ]; then
  echo "Cargo completed without producing the kiosk-label adapter." >&2
  exit 1
fi
mkdir -p "$(dirname -- "$DEST")"
tmp="$DEST.restore-tmp.$$"
trap 'rm -f "$tmp"' EXIT HUP INT TERM
cp "$BUILT" "$tmp"
chmod 755 "$tmp"
mv -f "$tmp" "$DEST"
echo "Printer adapter restored at $DEST"
echo "Use Workshop > System > Reconnect printer to verify readiness. This script does not print or restart services."
