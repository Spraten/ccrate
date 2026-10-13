#!/usr/bin/env python3
"""Validate and restore a private deployment backup into an empty directory."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile

DEPLOY_PATH = Path(__file__).resolve().parent
if str(DEPLOY_PATH) not in sys.path:
    sys.path.insert(0, str(DEPLOY_PATH))

from release_bundle import BundleError, validate_bundle

_PUBLISHER = DEPLOY_PATH / "publish-users.py"


def _publisher_validator():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ccrate_publish_users", _PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._validate_backup_members


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _restore_selector(root, selected):
    """Atomically point application-current at the already validated sealed release."""
    selector = Path(root) / "work/application-current"
    selector.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = selector.with_name(".application-current.restore")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    relative_target = os.path.relpath(Path(selected), selector.parent)
    temporary.symlink_to(relative_target, target_is_directory=True)
    os.replace(temporary, selector)


def _extract_validated(archive, destination):
    """Extract only regular files/directories, independent of Python's tar filter API."""
    directory_modes = []
    for row in archive.getmembers():
        path = destination.joinpath(*row.name.split("/"))
        if row.isdir():
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory_modes.append((path, row.mode & 0o777))
        elif row.isfile():
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = archive.extractfile(row)
            if source is None:
                raise BundleError(f"cold backup member cannot be read: {row.name}")
            with source, path.open("xb") as output:
                shutil.copyfileobj(source, output)
            path.chmod(row.mode & 0o777)
        else:
            raise BundleError(f"cold backup contains an unsupported link or special member: {row.name}")
    for path, mode in sorted(directory_modes, key=lambda pair: len(pair[0].parts), reverse=True):
        path.chmod(mode)


def restore_backup(archive_path, destination):
    """Restore an archive into a new private directory; never touches a live root."""
    archive_path, destination = Path(archive_path), Path(destination)
    if destination.exists():
        raise BundleError("restore destination must not already exist")
    validator = _publisher_validator()
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest_member = archive.getmember("deployment-manifest.json")
        if not manifest_member.isfile() or manifest_member.size > 2 * 1024 * 1024:
            raise BundleError("cold backup manifest is not a bounded regular member")
        stream = archive.extractfile(manifest_member)
        if stream is None:
            raise BundleError("cold backup manifest cannot be read")
        manifest = json.loads(stream.read(2 * 1024 * 1024 + 1).decode("utf-8"))
        validator(archive_path, manifest)
        destination.mkdir(mode=0o700, parents=True)
        try:
            _extract_validated(archive, destination)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    try:
        for name, expected in manifest["sha256"].items():
            path = destination / name
            if path.is_symlink() or not path.is_file() or _sha256(path) != expected:
                raise BundleError(f"restored whole-store hash mismatch: {name}")
        for name in ("work/ops/ledger.db", "work/baseline/data/homebox.db"):
            with contextlib.closing(sqlite3.connect(destination / name)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BundleError(f"restored database integrity check failed: {name}")

        selected = manifest.get("selected_release") if manifest.get("format") == 2 else None
        if selected is not None:
            release = destination / selected["relative_path"]
            if release.is_symlink() or _sha256(release / "manifest.json") != selected["manifest_sha256"]:
                raise BundleError("restored selected-release manifest hash mismatch")
            for name, expected in selected["files"].items():
                path = release / name
                if path.is_symlink() or not path.is_file() or _sha256(path) != expected:
                    raise BundleError(f"restored selected-release hash mismatch: {name}")
            sealed = validate_bundle(release)
            if sealed.get("format") != 2:
                raise BundleError("restored selected release is not a sealed format-2 bundle")
            _restore_selector(destination, release)
            if (destination / "work/application-current").resolve(strict=True) != release.resolve(strict=True):
                raise BundleError("restored application-current selector does not match selected release")
        return {"status": "restored", "format": manifest["format"],
                "selected_release": selected["relative_path"] if selected else None,
                "destination": str(destination)}
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path,
                        help="new, empty private restore directory (never the live deployment)")
    args = parser.parse_args(argv)
    print(json.dumps(restore_backup(args.archive, args.destination), sort_keys=True))


if __name__ == "__main__":
    main()
