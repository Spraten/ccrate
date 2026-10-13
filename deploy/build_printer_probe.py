#!/usr/bin/env python3
"""Rebuild the C-Crate printer adapter against the pinned Supvan protocol library."""
import json
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
SOURCE = ROOT / "deploy" / "kiosk-label.rs"
REPOSITORY = WORK / "supvan-cups"
EXAMPLE = REPOSITORY / "crates" / "supvan-proto" / "examples" / "kiosk-label.rs"


def main():
    pin = json.loads((ROOT / "docs" / "runtime-manifest.json").read_text())["printer_source_pin"]
    actual = subprocess.check_output(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], text=True).strip()
    if actual != pin:
        raise SystemExit(f"Supvan source must be checked out at {pin}; found {actual}")
    if not SOURCE.is_file():
        raise SystemExit(f"Missing persistent adapter source: {SOURCE}")

    tool_bin = ROOT / "work" / "toolchains" / "rust-home" / "bin"
    cargo = str(tool_bin / "cargo") if (tool_bin / "cargo").is_file() else shutil.which("cargo")
    if not cargo:
        raise SystemExit("Rust/Cargo not found; install Rust 1.88 or newer and rerun this script")
    EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, EXAMPLE)
    env = os.environ.copy()
    env.setdefault("CARGO_HOME", str(ROOT / "work" / "toolchains" / "rust-home"))
    env.setdefault("RUSTUP_HOME", str(ROOT / "work" / "toolchains" / "rustup-home"))
    subprocess.run([cargo, "build", "--locked", "--release", "-p", "supvan-proto", "--example", "kiosk-label"],
                   cwd=REPOSITORY, env=env, check=True)
    binary = REPOSITORY / "target" / "release" / "examples" / "kiosk-label"
    if not binary.is_file():
        raise SystemExit(f"Cargo completed without producing {binary}")
    print(binary)


if __name__ == "__main__":
    main()
