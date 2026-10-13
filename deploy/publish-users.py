"""Guarded operational publisher for a fully matched application bundle.

Importing this module is inert. Real baseline checks, private backup work,
service control, and live verification only run through the explicit CLI.
"""
import argparse
import calendar
import hashlib
import json
import os
import posixpath
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

# Direct script execution starts with work/ on sys.path. Resolve the sibling
# helper explicitly so the supported CLI does not depend on PYTHONPATH.
DEPLOY_PATH = Path(__file__).resolve().parents[1] / "deploy"
if str(DEPLOY_PATH) not in sys.path:
    sys.path.insert(0, str(DEPLOY_PATH))

from release_bundle import (FALLBACK_CHECKS, BundleError, _validate_fallback_receipt,
                            select_bundle, validate_bundle)


ROOT = Path("/home/user/Desktop/inventory-system")
REQUIRED_CHECKS = frozenset({
    "matched_previous_release_preserves_new_fixture_profiles_and_loans",
    "legacy_missing_member_api_is_not_a_rollback_target",
    *FALLBACK_CHECKS,
})


def _manifest_sha(release):
    return hashlib.sha256((Path(release) / "manifest.json").read_bytes()).hexdigest()


def _fallback_receipt_view(receipt):
    keys = {"execution_scope", "fallback_policy_sha256"}
    for label in ("previous", "candidate", "fallback"):
        keys.update({f"{label}_bundle_manifest_sha256", f"{label}_native_sha256"})
    return {**{key: receipt[key] for key in keys if key in receipt},
            "checks": {key: receipt.get("checks", {}).get(key) for key in FALLBACK_CHECKS}}


def validate_matched_receipt(receipt, previous_manifest, candidate_manifest, fallback_manifest=None, *, allow_fixture=False):
    """Bind readiness checks to the exact bundle pair and their native artifacts."""
    if not isinstance(receipt, dict):
        raise BundleError("matched verification receipt is required")
    scope = receipt.get("execution_scope")
    if scope != "production-matched" and not (allow_fixture and scope == "fixture-only"):
        raise BundleError("fixture-only evidence cannot authorize a production publication")
    expected = {
        "previous_bundle_manifest_sha256": previous_manifest["manifest_sha256"],
        "candidate_bundle_manifest_sha256": candidate_manifest["manifest_sha256"],
        "previous_native_sha256": previous_manifest["provenance"]["native_sha256"],
        "candidate_native_sha256": candidate_manifest["provenance"]["native_sha256"],
    }
    if fallback_manifest is not None:
        expected.update({
            "fallback_bundle_manifest_sha256": fallback_manifest["manifest_sha256"],
            "fallback_native_sha256": fallback_manifest["provenance"]["native_sha256"],
            "fallback_policy_sha256": hashlib.sha256(json.dumps(
                fallback_manifest["fallback_policy"], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        })
    if any(receipt.get(name) != value for name, value in expected.items()):
        raise BundleError("matched verification receipt does not bind the current bundle pair")
    checks = receipt.get("checks")
    if (not isinstance(checks, dict)
            or any(checks.get(name) is not True for name in REQUIRED_CHECKS)):
        raise BundleError("matched verification receipt lacks required named checks")
    if fallback_manifest is not None:
        _validate_fallback_receipt(_fallback_receipt_view(receipt),
                                   _manifest_path(previous_manifest),
                                   _manifest_path(candidate_manifest),
                                   _manifest_path(fallback_manifest))
    return receipt


def _manifest_path(manifest):
    path = manifest.get("bundle_path") if isinstance(manifest, dict) else None
    if not isinstance(path, str):
        raise BundleError("matched manifest is missing its bound bundle path")
    return Path(path)


def _archive_manifest(archive_path):
    archive_path = Path(archive_path)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember("deployment-manifest.json")
            if not member.isfile() or member.size > 2 * 1024 * 1024:
                raise BundleError("cold backup manifest is not a bounded regular member")
            stream = archive.extractfile(member)
            if stream is None:
                raise BundleError("cold backup manifest cannot be read")
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise BundleError("cold backup manifest is too large")
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, tarfile.TarError, UnicodeError, ValueError, KeyError) as exc:
        raise BundleError("cold backup archive is missing a valid deployment manifest") from exc
    return raw, manifest


def _validate_backup_members(archive_path, manifest):
    """Check producer-declared paths against the tar and hash the archived bytes."""
    required = {
        "AGENTS.md", ".git", "ops", "kiosk", "deploy", "docs", "upstream/homebox",
        "work/baseline/data", "work/baseline/pepper", "work/baseline/test-account.json",
        "work/ops", "work/homebox-bin/homebox", "work/hardware/python",
        "work/supvan-cups/target/release/examples/kiosk-label",
    }
    if not isinstance(manifest, dict):
        raise BundleError("cold backup manifest is not an object")
    members = manifest.get("members")
    hashes = manifest.get("sha256")
    backup_format = manifest.get("format")
    if (type(backup_format) is not int or backup_format not in (1, 2)
            or not isinstance(members, list)
            or any(not isinstance(name, str) or not name or "\\" in name for name in members)
            or not required <= set(members) or not isinstance(hashes, dict)
            or not {"work/ops/ledger.db", "work/baseline/data/homebox.db",
                    "work/homebox-bin/homebox",
                    "work/supvan-cups/target/release/examples/kiosk-label"} <= set(hashes)):
        raise BundleError("cold backup manifest lacks required whole-store members")
    selected = manifest.get("selected_release")
    if backup_format == 2:
        if selected is None and any(isinstance(name, str) and name.startswith("work/releases/")
                                    for name in members):
            raise BundleError("format-2 backup omits the selected sealed release")
        if selected is not None:
            release_path = selected.get("relative_path") if isinstance(selected, dict) else None
            files = selected.get("files") if isinstance(selected, dict) else None
            manifest_hash = selected.get("manifest_sha256") if isinstance(selected, dict) else None
            parts = release_path.split("/") if isinstance(release_path, str) else []
            if (not isinstance(selected, dict)
                    or set(selected) != {"relative_path", "manifest_sha256", "files"}
                    or not isinstance(release_path, str) or "\\" in release_path
                    or len(parts) < 3 or parts[:2] != ["work", "releases"]
                    or any(part in ("", ".", "..") for part in parts)
                    or release_path not in members
                    or not isinstance(manifest_hash, str) or len(manifest_hash) != 64
                    or any(c not in "0123456789abcdef" for c in manifest_hash)
                    or not isinstance(files, dict) or "manifest.json" not in files
                    or any(not isinstance(name, str) or not name or "\\" in name
                           or posixpath.isabs(name) or any(part in ("", ".", "..")
                           for part in name.split("/"))
                           or not isinstance(digest, str) or len(digest) != 64
                           or any(c not in "0123456789abcdef" for c in digest)
                           for name, digest in files.items())):
                raise BundleError("format-2 backup selected-release binding is invalid")
    elif selected is not None:
        raise BundleError("format-1 backup cannot declare a selected sealed release")
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            rows = {}
            for row in archive.getmembers():
                name = row.name.rstrip("/")
                if (not name or "\\" in name or posixpath.isabs(name)
                        or posixpath.normpath(name) != name or ".." in name.split("/")
                        or name in rows):
                    raise BundleError("cold backup archive contains an unsafe or duplicate member")
                rows[name] = row
            for name in required:
                if name not in rows and not any(path.startswith(name + "/") for path in rows):
                    raise BundleError(f"cold backup archive is missing required member {name}")
            required_directories = {".git", "ops", "kiosk", "deploy", "docs", "upstream/homebox",
                                    "work/baseline/data", "work/ops", "work/hardware/python"}
            if any(name not in rows or not rows[name].isdir() for name in required_directories):
                raise BundleError("cold backup archive is missing a required directory tree")
            required_files = {"AGENTS.md", "work/baseline/pepper", "work/baseline/test-account.json",
                              "work/homebox-bin/homebox",
                              "work/supvan-cups/target/release/examples/kiosk-label"}
            if any(name not in rows or not rows[name].isfile() for name in required_files):
                raise BundleError("cold backup archive is missing a required regular file")
            for name, expected in hashes.items():
                row = rows.get(name)
                if (not isinstance(name, str) or not isinstance(expected, str)
                        or len(expected) != 64 or row is None or not row.isfile()):
                    raise BundleError(f"cold backup hash declaration has no regular archived file: {name}")
                stream = archive.extractfile(row)
                if stream is None:
                    raise BundleError(f"cold backup archived file cannot be read: {name}")
                digest = hashlib.sha256()
                with stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != expected:
                    raise BundleError(f"cold backup archived hash mismatch for {name}")
            if backup_format == 2 and selected is not None:
                release_path = selected["relative_path"]
                prefix = release_path + "/"
                selected_files = selected["files"]
                archived_files = {name[len(prefix):]: row for name, row in rows.items()
                                  if name.startswith(prefix) and row.isfile()}
                archived_directories = {name for name, row in rows.items()
                                        if (name == release_path or name.startswith(prefix)) and row.isdir()}
                if set(archived_files) != set(selected_files) or release_path not in archived_directories:
                    raise BundleError("cold backup selected-release membership differs from its manifest")
                expected_directories = {release_path}
                for name in selected_files:
                    parent = posixpath.dirname(name)
                    while parent:
                        expected_directories.add(release_path + "/" + parent)
                        parent = posixpath.dirname(parent)
                if archived_directories != expected_directories:
                    raise BundleError("cold backup selected-release directory membership differs from its manifest")
                if any(row.issym() or row.islnk() or row.isdev() or row.isfifo()
                       for name, row in rows.items() if name == release_path or name.startswith(prefix)):
                    raise BundleError("cold backup selected release contains a non-regular member")
                if any(rows[name].mode & 0o777 != 0o555 for name in archived_directories):
                    raise BundleError("cold backup selected-release directory is not sealed")
                for name, expected in selected_files.items():
                    row = archived_files[name]
                    if row.mode & 0o777 not in (0o444, 0o555):
                        raise BundleError(f"cold backup selected-release file is not sealed: {name}")
                    stream = archive.extractfile(row)
                    if stream is None:
                        raise BundleError(f"cold backup selected-release file cannot be read: {name}")
                    digest = hashlib.sha256()
                    with stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest() != expected:
                        raise BundleError(f"cold backup selected-release hash mismatch for {name}")
                if selected_files.get("manifest.json") != selected["manifest_sha256"]:
                    raise BundleError("cold backup selected-release manifest hash is inconsistent")
    except (OSError, tarfile.TarError) as exc:
        raise BundleError("cold backup archive members could not be validated") from exc


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_cold_backup_receipt(result, root, previous, candidate, fallback):
    if (not isinstance(result, dict) or result.get("status") != "completed"
            or result.get("database_integrity") != "ok" or not isinstance(result.get("backup"), str)
            or Path(result["backup"]).name != result["backup"]):
        raise BundleError("whole-store cold backup did not complete successfully")
    root = Path(root).resolve(strict=True)
    archive_path = root / "work/backups" / result["backup"]
    if archive_path.is_symlink() or not archive_path.is_file():
        raise BundleError("cold backup archive is missing or linked")
    archive_stat = archive_path.stat()
    if archive_stat.st_mode & 0o077 or archive_stat.st_size != result.get("bytes"):
        raise BundleError("cold backup archive permissions or size differ from its result")
    archive_sha = _sha256_file(archive_path)
    sidecar = archive_path.with_suffix(".sha256")
    if sidecar.is_symlink() or not sidecar.is_file():
        raise BundleError("cold backup checksum sidecar is missing or linked")
    if sidecar.read_text(encoding="utf-8") != f"{archive_sha}  {archive_path.name}\n":
        raise BundleError("cold backup checksum sidecar does not match the archive")
    raw_manifest, backup_manifest = _archive_manifest(archive_path)
    _validate_backup_members(archive_path, backup_manifest)
    selected = backup_manifest.get("selected_release")
    try:
        previous_path = Path(previous["bundle_path"]).resolve(strict=True)
        previous_relative = previous_path.relative_to(root).as_posix()
    except (KeyError, OSError, ValueError) as exc:
        raise BundleError("publication previous bundle is outside the deployment root") from exc
    if (backup_manifest.get("format") != 2 or not isinstance(selected, dict)
            or selected.get("relative_path") != previous_relative
            or selected.get("manifest_sha256") != previous["manifest_sha256"]):
        raise BundleError("cold backup does not bind the currently selected sealed previous bundle")
    receipt = {
        "schema": 1,
        "execution_scope": "production-matched",
        "status": "completed",
        "exit_code": 0,
        "database_integrity": "ok",
        "root": str(root),
        "backup_path": str(archive_path),
        "backup_archive_sha256": archive_sha,
        "backup_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "backup_created_at": backup_manifest.get("created_at"),
        "backup_bytes": archive_stat.st_size,
        "selected_release_path": selected["relative_path"],
        "selected_release_manifest_sha256": selected["manifest_sha256"],
        "previous_bundle_manifest_sha256": previous["manifest_sha256"],
        "candidate_bundle_manifest_sha256": candidate["manifest_sha256"],
        "fallback_bundle_manifest_sha256": fallback["manifest_sha256"],
        "previous_native_sha256": previous["provenance"]["native_sha256"],
        "candidate_native_sha256": candidate["provenance"]["native_sha256"],
        "fallback_native_sha256": fallback["provenance"]["native_sha256"],
    }
    receipt_path = root / "work/matched-release-cold-backup-receipt.json"
    _atomic_json(receipt_path, receipt)
    return receipt_path, receipt


def validate_cold_backup_receipt(receipt, root, previous, candidate, fallback):
    expected_keys = {
        "schema", "execution_scope", "status", "exit_code", "database_integrity", "root",
        "backup_path", "backup_archive_sha256", "backup_manifest_sha256", "backup_created_at",
        "backup_bytes", "selected_release_path", "selected_release_manifest_sha256",
        "previous_bundle_manifest_sha256", "candidate_bundle_manifest_sha256",
        "fallback_bundle_manifest_sha256", "previous_native_sha256", "candidate_native_sha256",
        "fallback_native_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise BundleError("cold backup receipt schema is invalid")
    root = Path(root).resolve(strict=True)
    if (receipt["schema"] != 1 or receipt["execution_scope"] != "production-matched"
            or receipt["status"] != "completed" or receipt["exit_code"] != 0
            or receipt["database_integrity"] != "ok" or receipt["root"] != str(root)):
        raise BundleError("cold backup receipt does not prove a successful whole-store backup")
    for label, manifest in (("previous", previous), ("candidate", candidate), ("fallback", fallback)):
        if (receipt[f"{label}_bundle_manifest_sha256"] != manifest["manifest_sha256"]
                or receipt[f"{label}_native_sha256"] != manifest["provenance"]["native_sha256"]):
            raise BundleError("cold backup receipt is not bound to the exact O/C/F bundle set")
    backup_path = Path(receipt["backup_path"])
    backup_root = (root / "work/backups").resolve(strict=True)
    try:
        backup_path.resolve(strict=True).relative_to(backup_root)
    except (OSError, ValueError) as exc:
        raise BundleError("cold backup receipt path is outside the retained backup store") from exc
    if backup_path.is_symlink() or not backup_path.is_file():
        raise BundleError("cold backup receipt archive is missing or linked")
    st = backup_path.stat()
    if st.st_mode & 0o077 or st.st_size != receipt["backup_bytes"]:
        raise BundleError("cold backup receipt archive permissions or size changed")
    archive_sha = _sha256_file(backup_path)
    sidecar = backup_path.with_suffix(".sha256")
    if (archive_sha != receipt["backup_archive_sha256"] or sidecar.is_symlink()
            or not sidecar.is_file()
            or sidecar.read_text(encoding="utf-8") != f"{archive_sha}  {backup_path.name}\n"):
        raise BundleError("cold backup archive hash or checksum sidecar changed")
    raw_manifest, manifest = _archive_manifest(backup_path)
    _validate_backup_members(backup_path, manifest)
    if hashlib.sha256(raw_manifest).hexdigest() != receipt["backup_manifest_sha256"]:
        raise BundleError("cold backup deployment manifest changed")
    if manifest.get("created_at") != receipt["backup_created_at"]:
        raise BundleError("cold backup timestamp changed")
    selected = manifest.get("selected_release")
    try:
        previous_path = Path(previous["bundle_path"]).resolve(strict=True)
        previous_relative = previous_path.relative_to(root).as_posix()
    except (KeyError, OSError, ValueError) as exc:
        raise BundleError("publication previous bundle is outside the deployment root") from exc
    if (manifest.get("format") != 2 or not isinstance(selected, dict)
            or selected.get("relative_path") != previous_relative
            or selected.get("manifest_sha256") != previous["manifest_sha256"]
            or receipt["selected_release_path"] != selected["relative_path"]
            or receipt["selected_release_manifest_sha256"] != selected["manifest_sha256"]):
        raise BundleError("cold backup receipt is not bound to the selected previous sealed bundle")
    try:
        created = calendar.timegm(time.strptime(receipt["backup_created_at"], "%Y%m%dT%H%M%SZ"))
    except (ValueError, TypeError) as exc:
        raise BundleError("cold backup timestamp is invalid") from exc
    if created > time.time() + 60 or time.time() - created > 24 * 60 * 60:
        raise BundleError("cold backup receipt is not fresh")
    return receipt


def _run_services(arguments):
    subprocess.run(["systemctl", "--user", *arguments], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Select one matched application release")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--fallback", required=True, type=Path)
    parser.add_argument("--verification-receipt", required=True, type=Path)
    parser.add_argument("--apply", action="store_true",
                        help="perform approved baseline, backup, service, and verification actions")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("--apply is required; publication has operational effects")

    selector = ROOT / "work" / "application-current"
    try:
        previous = selector.resolve(strict=True)
    except OSError as exc:
        raise BundleError("previous application bundle is not selected") from exc
    candidate = args.candidate.resolve(strict=True)
    fallback = args.fallback.resolve(strict=True)
    previous_manifest = validate_bundle(previous)
    candidate_manifest = validate_bundle(candidate)
    fallback_manifest = validate_bundle(fallback)
    if any(item.get("format") != 2 for item in (previous_manifest, candidate_manifest, fallback_manifest)):
        raise BundleError("publication requires matched format-2 O/C/F bundles")
    previous_manifest = {**previous_manifest,
                         "manifest_sha256": _manifest_sha(previous), "bundle_path": str(previous)}
    candidate_manifest = {**candidate_manifest,
                          "manifest_sha256": _manifest_sha(candidate), "bundle_path": str(candidate)}
    fallback_manifest = {**fallback_manifest,
                         "manifest_sha256": _manifest_sha(fallback), "bundle_path": str(fallback)}
    receipt = json.loads(args.verification_receipt.read_text())
    validate_matched_receipt(receipt, previous_manifest, candidate_manifest, fallback_manifest)

    # Preserve the live baseline and private backup safeguards behind --apply.
    os.umask(0o077)
    subprocess.run(["python3", str(ROOT / "deploy/verify-desktop-inventory.py"), "--before"],
                   check=True, cwd=ROOT)
    shutil.copy2(ROOT / "work/desktop-before-inventory.json",
                 ROOT / "work/users-before-inventory.json")
    backup_process = subprocess.run(["python3", str(ROOT / "deploy/backup-deployment.py")],
                                    check=True, cwd=ROOT, capture_output=True, text=True)
    try:
        backup_result = json.loads(backup_process.stdout)
    except (TypeError, ValueError) as exc:
        raise BundleError("cold backup did not return a bounded success receipt") from exc
    backup_receipt_path, backup_receipt = _build_cold_backup_receipt(
        backup_result, ROOT, previous_manifest, candidate_manifest, fallback_manifest)
    validate_cold_backup_receipt(backup_receipt, ROOT,
                                 previous_manifest, candidate_manifest, fallback_manifest)
    backup_receipt_sha256 = hashlib.sha256(
        json.dumps(backup_receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    # Baseline and backup helpers are external boundaries. Bind the readiness
    # receipt again to the still-selected previous/candidate pair before the
    # first service callback can run.
    try:
        current_previous = selector.resolve(strict=True)
    except OSError as exc:
        raise BundleError("previous application bundle changed during preflight") from exc
    if current_previous != previous:
        raise BundleError("previous application bundle changed during preflight")
    rebound_previous = validate_bundle(current_previous)
    rebound_candidate = validate_bundle(candidate)
    rebound_fallback = validate_bundle(fallback)
    if any(item.get("format") != 2 for item in (rebound_previous, rebound_candidate, rebound_fallback)):
        raise BundleError("publication requires matched format-2 O/C/F bundles")
    previous_manifest = {**rebound_previous,
                         "manifest_sha256": _manifest_sha(current_previous), "bundle_path": str(current_previous)}
    candidate_manifest = {**rebound_candidate,
                          "manifest_sha256": _manifest_sha(candidate), "bundle_path": str(candidate)}
    fallback_manifest = {**rebound_fallback,
                         "manifest_sha256": _manifest_sha(fallback), "bundle_path": str(fallback)}
    validate_matched_receipt(receipt, previous_manifest, candidate_manifest, fallback_manifest)
    validate_cold_backup_receipt(backup_receipt, ROOT,
                                 previous_manifest, candidate_manifest, fallback_manifest)

    def verify(release):
        validate_bundle(release)
        subprocess.run(["python3", str(ROOT / "deploy/verify-desktop-inventory.py")],
                       check=True, cwd=ROOT)

    select_bundle(ROOT, candidate, fallback=fallback,
                  fallback_receipt=_fallback_receipt_view(receipt),
                  backup_receipt_sha256=backup_receipt_sha256,
                  run_services=_run_services, verify=verify)
    record = {
        "previous_bundle_manifest_sha256": previous_manifest["manifest_sha256"],
        "candidate_bundle_manifest_sha256": candidate_manifest["manifest_sha256"],
        "candidate_native_sha256": candidate_manifest["provenance"]["native_sha256"],
        "fallback_bundle_manifest_sha256": fallback_manifest["manifest_sha256"],
        "backup_receipt": str(backup_receipt_path),
        "backup_receipt_sha256": backup_receipt_sha256,
        "selected_bundle": str(candidate),
        "inventory_preserved": True,
    }
    _atomic_json(ROOT / "work/users-published-release.json", record)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
