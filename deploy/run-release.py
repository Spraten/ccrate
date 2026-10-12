#!/usr/bin/env python3
"""Select one sealed application release and exec its packaged component."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


def _read_regular(path, expected_mode):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != expected_mode):
        raise ValueError("selected release bootstrap path is not a sealed regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        after = os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode) or after.st_nlink != 1
                or stat.S_IMODE(after.st_mode) != expected_mode
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise ValueError("selected release bootstrap changed during preflight")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            return stream.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _checked_helper(release):
    root_stat = release.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o555:
        raise ValueError("selected release is not a sealed real directory")
    deploy = release / "deploy"
    deploy_stat = deploy.lstat()
    if not stat.S_ISDIR(deploy_stat.st_mode) or stat.S_IMODE(deploy_stat.st_mode) != 0o555:
        raise ValueError("selected release deploy path is not a sealed real directory")
    manifest_bytes = _read_regular(release / "manifest.json", 0o444)
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("format") != 2:
        raise ValueError("selected release has no packaged launcher")
    helper_name = "deploy/release_bundle.py"
    record = manifest.get("files", {}).get(helper_name)
    if not isinstance(record, dict) or record.get("mode") != 0o444:
        raise ValueError("selected release helper is not sealed in its manifest")
    helper = _read_regular(release / helper_name, 0o444)
    helper_sha = hashlib.sha256(helper).hexdigest()
    if helper_sha != record.get("sha256"):
        raise ValueError("selected release helper hash differs from its manifest")
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("selected release helper has no source provenance")
    build, tests = provenance.get("build_receipt"), provenance.get("test_receipt")
    digest = provenance.get("source_manifest_digest")
    static_digest = provenance.get("static_manifest_sha256")
    if not isinstance(build, dict) or not isinstance(tests, dict) or not isinstance(digest, str):
        raise ValueError("selected release helper receipts are incomplete")
    try:
        canonical = lambda value: hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt_bindings = (
            (provenance.get("build_receipt_canonical_sha256"), canonical(build)),
            (provenance.get("test_receipt_canonical_sha256"), canonical(tests)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("selected release receipts are not canonical JSON") from exc
    if (len(digest) != 64
            or any(not isinstance(expected, str) or len(expected) != 64 or expected != actual
                   for expected, actual in receipt_bindings)
            or not isinstance(provenance.get("build_receipt_sha256"), str)
            or len(provenance["build_receipt_sha256"]) != 64
            or not isinstance(provenance.get("test_receipt_sha256"), str)
            or len(provenance["test_receipt_sha256"]) != 64
            or not isinstance(provenance.get("build_receipt_path"), str)
            or not isinstance(provenance.get("test_receipt_path"), str)
            or not provenance["build_receipt_path"] or not provenance["test_receipt_path"]
            or build.get("source_manifest_digest") != digest
            or tests.get("source_manifest_digest") != digest
            or not isinstance(static_digest, str) or len(static_digest) != 64
            or build.get("static_manifest_sha256") != static_digest):
        raise ValueError("selected release helper receipt bindings are invalid")
    runtime_files = provenance.get("runtime_files")
    runtime_modes = provenance.get("runtime_modes")
    source_entries = tests.get("source_entries")
    source_entry = source_entries.get(helper_name) if isinstance(source_entries, dict) else None
    if (not isinstance(runtime_files, dict) or runtime_files.get(helper_name) != helper_sha
            or not isinstance(runtime_modes, dict)
            or not isinstance(source_entry, dict)
            or source_entry.get("sha256") != helper_sha
            or type(source_entry.get("mode")) is not int
            or source_entry.get("mode") != runtime_modes.get(helper_name)):
        raise ValueError("selected release helper is not bound by its source and test receipts")
    verification = tests.get("verification")
    if (not isinstance(verification, dict) or verification.get("exit_code") != 0
            or type(verification.get("tests")) is not int or verification["tests"] < 1):
        raise ValueError("selected release helper test receipt is not successful")
    return helper, release / helper_name


def main():
    component = sys.argv[1] if len(sys.argv) == 2 else ""
    if component not in {"native", "companion", "gateway"}:
        raise ValueError("unknown release component")
    release = Path(__file__).resolve(strict=True).parent.parent
    helper_bytes, helper_path = _checked_helper(release)
    namespace = {"__name__": "_selected_release_bundle", "__file__": str(helper_path)}
    exec(compile(helper_bytes, str(helper_path), "exec"), namespace)
    root = Path(os.environ.get("WORKSHOP_ROOT", "/home/user/Desktop/inventory-system"))
    command, selected_env = namespace["release_command"](root, component, release=release)
    environment = os.environ.copy()
    environment.update(selected_env)
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
