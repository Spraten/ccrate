"""Build and validate a bounded, provenance-bound application bundle."""
import hashlib
import json
import math
import os
import contextlib
import shutil
import stat
import sys
import fcntl
import time
import uuid
from pathlib import Path
from contextlib import contextmanager


class BundleError(ValueError):
    pass


class JournalAppendRollbackError(BundleError):
    """A journal append failed and its prior valid length could not be fsynced back."""


DEPLOY_FILES = frozenset({
    "kiosk-server.py", "workshop-gateway.py", "run-homebox.py",
    "homebox-native.service", "homebox-companion.service",
    "homebox-workshop-gateway.service",
})
LAUNCHER_FILES = frozenset({"run-release.py", "release_bundle.py"})
LAUNCHER_DEPLOY_FILES = DEPLOY_FILES | LAUNCHER_FILES


def _hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _walk(root, predicate):
    root = Path(root)
    if not root.is_dir():
        raise BundleError(f"missing required artifact directory: {root}")
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise BundleError(f"artifact link escapes supplied root: {rel}")
            # No links are needed in a runtime bundle. Do not follow them.
            continue
        if path.is_file() and predicate(rel, path):
            yield path, rel


def _runtime_files(source, deploy_files=DEPLOY_FILES):
    source = Path(source)
    selected = []
    for area in ("ops", "kiosk"):
        root = source / area
        for path, rel in _walk(root, lambda r, p: "__pycache__" not in r.parts and p.suffix != ".pyc"):
            if area == "ops" and path.suffix != ".py":
                continue
            if area == "kiosk" and path.suffix.lower() not in {
                    ".py", ".html", ".js", ".css", ".svg", ".png", ".ico",
                    ".jpg", ".jpeg", ".webmanifest", ".json", ".woff", ".woff2"}:
                continue
            selected.append((path, Path(area) / rel))
    deploy = source / "deploy"
    for path, rel in _walk(deploy, lambda r, p: len(r.parts) == 1 and r.name in deploy_files):
        selected.append((path, Path("deploy") / rel))
    required = {"ops/desktop_api.py", "ops/item_notes.py", "ops/label_layouts.py",
                "ops/label_render.py", "kiosk/index.html", "kiosk/scan_codes.py",
                *(f"deploy/{name}" for name in deploy_files)}
    found = {dest.as_posix() for _, dest in selected}
    missing = required - found
    if missing:
        raise BundleError(f"incomplete runtime source closure: {', '.join(sorted(missing))}")
    return selected


def _provenance(provenance, *, binary_sha, source_files, public_files, label_files,
                check_source_modes=True, check_receipt_bytes=False,
                source_hashes=None, source_modes=None, label_source_sha256=None):
    if not isinstance(provenance, dict):
        raise BundleError("matched build and test provenance is required")
    source_digest = provenance.get("source_manifest_digest")
    build, tests = provenance.get("build_receipt"), provenance.get("test_receipt")
    if not isinstance(source_digest, str) or len(source_digest) != 64:
        raise BundleError("source manifest digest is missing")
    if not isinstance(build, dict) or not isinstance(tests, dict):
        raise BundleError("build and test receipts are required")
    receipt_hashes = (provenance.get("build_receipt_sha256"), provenance.get("test_receipt_sha256"))
    receipt_paths = (provenance.get("build_receipt_path"), provenance.get("test_receipt_path"))
    if (any(not isinstance(value, str) or len(value) != 64 for value in receipt_hashes)
            or any(not isinstance(value, str) or not value for value in receipt_paths)
            or _json_hash(build) != provenance.get("build_receipt_canonical_sha256")
            or _json_hash(tests) != provenance.get("test_receipt_canonical_sha256")):
        raise BundleError("build or test receipt content does not match its binding")
    if check_receipt_bytes:
        for label, value, expected_hash, parsed in (
                ("build", provenance.get("build_receipt_raw"), receipt_hashes[0], build),
                ("test", provenance.get("test_receipt_raw"), receipt_hashes[1], tests)):
            if (not isinstance(value, str)
                    or hashlib.sha256(value.encode()).hexdigest() != expected_hash
                    or json.loads(value) != parsed):
                raise BundleError(f"{label} receipt bytes do not match their captured hash")
    static_digest = provenance.get("static_manifest_sha256")
    if (build.get("source_manifest_digest") != source_digest
            or tests.get("source_manifest_digest") != source_digest
            or build.get("static_manifest_sha256") != static_digest
            or not isinstance(tests.get("source_entries"), dict)):
        raise BundleError("build/test receipts do not match accepted source")
    verification = tests.get("verification", {})
    if (verification.get("exit_code") != 0 or not isinstance(verification.get("tests"), int)
            or verification["tests"] < 1):
        raise BundleError("test receipt is not a successful nonempty run")
    if provenance.get("native_sha256") != binary_sha:
        raise BundleError("native binary does not match captured artifact")
    actual_source = (source_hashes if source_hashes is not None else
                     {Path(name).as_posix(): _hash(path) for path, name in source_files})
    expected_source = provenance.get("runtime_files")
    if not isinstance(expected_source, dict) or expected_source != actual_source:
        raise BundleError("runtime source files do not match the source receipt")
    actual_modes = (source_modes if source_modes is not None else
                    {Path(name).as_posix(): path.stat().st_mode & 0o777 for path, name in source_files})
    expected_modes = provenance.get("runtime_modes")
    if check_source_modes and (not isinstance(expected_modes, dict) or expected_modes != actual_modes):
        raise BundleError("runtime source modes do not match the source receipt")
    receipt_sources = tests["source_entries"]
    for name, content_hash in actual_source.items():
        entry = receipt_sources.get(name)
        if not isinstance(entry, dict) or entry.get("sha256") != content_hash:
            raise BundleError(f"test source receipt does not bind {name}")
        if check_source_modes and entry.get("mode") != actual_modes[name]:
            raise BundleError(f"test source receipt mode does not bind {name}")
    if provenance.get("public_files") != public_files:
        raise BundleError("public frontend files do not match the captured manifest")
    if provenance.get("label_files") != label_files:
        raise BundleError("label renderer assets do not match the captured manifest")
    if label_source_sha256 is not None and provenance.get("label_source_sha256") != label_source_sha256:
        raise BundleError("label starter document does not match its manifest")
    workshop_capability = _validate_workshop_capability(
        provenance, runtime_files=actual_source, runtime_modes=expected_modes,
        public_files=public_files, label_files=label_files,
        label_source_sha256=label_source_sha256, native_sha256=binary_sha)
    matched = {
        "source_manifest_digest": source_digest,
        "static_manifest_sha256": static_digest,
        "build_receipt_sha256": provenance.get("build_receipt_sha256"),
        "build_receipt_canonical_sha256": provenance["build_receipt_canonical_sha256"],
        "test_receipt_sha256": provenance.get("test_receipt_sha256"),
        "test_receipt_canonical_sha256": provenance["test_receipt_canonical_sha256"],
        "build_receipt_path": provenance.get("build_receipt_path"),
        "test_receipt_path": provenance.get("test_receipt_path"),
        "native_sha256": binary_sha,
        "runtime_files": actual_source,
        "runtime_modes": expected_modes,
        "public_files": public_files,
        "label_files": label_files,
        "build_receipt": build,
        "test_receipt": tests,
    }
    if workshop_capability is not None:
        matched["workshop_capability"] = workshop_capability
    if label_source_sha256 is not None:
        matched["label_source_sha256"] = label_source_sha256
    return matched


def _inventory(root, expected):
    members = list(_walk(root, lambda r, p: True))
    if not isinstance(expected, dict) or {rel.as_posix() for _, rel in members} != set(expected):
        raise BundleError(f"artifact membership differs from captured manifest: {root}")
    return {
        rel.as_posix(): {"sha256": _hash(path), "size": path.stat().st_size}
        for path, rel in members
    }


def _assert_source_members(source_files, provenance):
    names = {dest.as_posix() for _, dest in source_files}
    if names != set(provenance.get("runtime_files", {})) or names != set(provenance.get("runtime_modes", {})):
        raise BundleError("runtime source membership differs from source receipt")


FALLBACK_POLICY_KEYS = frozenset({
    "schema", "evidence_scope", "strategy", "candidate_manifest_sha256",
    "roomsv2_read_versions", "workshop_mutation_mode",
    "member_profile_loan_compatibility", "runtime_state_policy", "physical_effect_policy",
})


def _validate_fallback_policy(policy):
    if not isinstance(policy, dict) or set(policy) != FALLBACK_POLICY_KEYS:
        raise BundleError("fallback policy schema is invalid")
    if (policy.get("schema") != 1
            or policy.get("evidence_scope") not in ("fixture-only", "production-matched")
            or policy.get("strategy") != "candidate-code-with-captured-previous-public"
            or not isinstance(policy.get("candidate_manifest_sha256"), str)
            or len(policy["candidate_manifest_sha256"]) != 64
            or policy.get("roomsv2_read_versions") != [1, 2]
            or policy.get("workshop_mutation_mode") not in ("v2", "disabled")
            or policy.get("member_profile_loan_compatibility") != "verified"
            or policy.get("runtime_state_policy") != "same-stores-no-restore"
            or policy.get("physical_effect_policy") != "never-replay"):
        raise BundleError("fallback policy does not describe compatible F recovery")
    return policy


def _workshop_closure_digest(runtime_files, runtime_modes, public_files, label_files,
                             label_source_sha256, native_sha256):
    return _json_hash({"runtime_files": runtime_files, "runtime_modes": runtime_modes,
                       "public_files": public_files, "label_files": label_files,
                       "label_source_sha256": label_source_sha256,
                       "native_sha256": native_sha256})


def _validate_workshop_capability(provenance, *, runtime_files, runtime_modes,
                                  public_files, label_files, label_source_sha256, native_sha256):
    capability = provenance.get("workshop_capability")
    if capability is None:
        return None
    if not isinstance(capability, dict) or set(capability) != {
            "schema", "read_versions", "write_mode", "closure_sha256", "test_names"}:
        raise BundleError("Workshop compatibility capability schema is invalid")
    reads, mode, names = (capability.get("read_versions"), capability.get("write_mode"),
                          capability.get("test_names"))
    if (type(capability.get("schema")) is not int or capability.get("schema") != 1
            or not isinstance(reads, list) or any(type(version) is not int for version in reads)
            or reads not in ([1], [2], [1, 2]) or mode not in ("v1", "v2", "disabled")
            or not isinstance(names, list) or any(not isinstance(name, str) for name in names)):
        raise BundleError("Workshop compatibility capability values are invalid")
    expected_names = [f"workshop_read_v{version}" for version in reads]
    expected_names.append({"v1": "workshop_write_v1", "v2": "workshop_write_v2",
                           "disabled": "workshop_write_disabled"}[mode])
    closure = _workshop_closure_digest(runtime_files, runtime_modes, public_files, label_files,
                                       label_source_sha256, native_sha256)
    receipt = provenance.get("test_receipt", {}).get("workshop_compatibility")
    if (capability.get("test_names") != expected_names
            or capability.get("closure_sha256") != closure
            or not isinstance(receipt, dict) or set(receipt) != {"closure_sha256", "tests"}
            or receipt.get("closure_sha256") != closure or not isinstance(receipt.get("tests"), list)):
        raise BundleError("Workshop capability is not bound to the exact runtime/static/native closure")
    actual = []
    for row in receipt["tests"]:
        if not isinstance(row, dict) or set(row) != {"name", "result"} or row.get("result") != "passed":
            raise BundleError("Workshop compatibility test receipt is invalid")
        actual.append(row["name"])
    if actual != expected_names:
        raise BundleError("Workshop capability lacks the named read/write compatibility tests")
    return capability


def _require_workshop_compatibility(manifest, *, role, require_writer=False):
    capability = manifest.get("provenance", {}).get("workshop_capability")
    if (manifest.get("format") != 2 or not isinstance(capability, dict)
            or capability.get("read_versions") != [1, 2]
            or capability.get("write_mode") not in (("v2",) if require_writer else ("v2", "disabled"))):
        requirement = "version-2 writer" if require_writer else "version-2 writer or disabled writes"
        raise BundleError(f"{role} bundle lacks artifact-matched Workshop v1/v2 read and {requirement} capability")
    return capability


def stage_bundle(destination, *, binary, public, source, provenance, fallback_policy=None):
    """Copy only runtime allowlists and seal hashes, modes, and receipt bindings."""
    destination, binary, public, source = map(Path, (destination, binary, public, source))
    if destination.exists() or destination.is_symlink():
        raise BundleError(f"destination already exists: {destination}")
    if not binary.is_file() or binary.is_symlink():
        raise BundleError("native binary is missing or linked")
    deploy_files = (LAUNCHER_DEPLOY_FILES if all((source / "deploy" / name).is_file()
                                                  for name in LAUNCHER_FILES)
                    else DEPLOY_FILES)
    source_files = _runtime_files(source, deploy_files)
    _assert_source_members(source_files, provenance)
    public_files = _inventory(public, provenance.get("public_files"))
    label_root = source / "work" / "label-ui-build"
    label_files = _inventory(label_root, provenance.get("label_files"))
    label_source = source / "label-ui" / "src" / "starter-documents.json"
    label_source_sha256 = None
    if deploy_files == LAUNCHER_DEPLOY_FILES:
        if not label_source.is_file() or label_source.is_symlink():
            raise BundleError("launcher bundle lacks label starter documents")
        label_source_sha256 = _hash(label_source)
    native_sha = _hash(binary)
    matched = _provenance(provenance, binary_sha=native_sha, source_files=source_files,
                          public_files=public_files, label_files=label_files,
                          check_receipt_bytes=True, label_source_sha256=label_source_sha256)
    destination.mkdir(parents=True)
    try:
        native = destination / "native" / "homebox"
        native.parent.mkdir()
        shutil.copyfile(binary, native)
        os.chmod(native, (binary.stat().st_mode & 0o555) | 0o444)
        for path, rel in _walk(public, lambda r, p: True):
            target = destination / "public" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, (path.stat().st_mode & 0o555) | 0o444)
        for path, rel in source_files:
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, (path.stat().st_mode & 0o555) | 0o444)
        # Label editor files are runtime assets; preserve this finite sealed tree.
        label_assets = source / "work" / "label-ui-build"
        for path, rel in _walk(label_assets, lambda r, p: True):
            target = destination / "label-ui" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, (path.stat().st_mode & 0o555) | 0o444)
        if label_source_sha256 is not None:
            target = destination / "label-ui" / "src" / "starter-documents.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(label_source, target)
            os.chmod(target, 0o444)
        files = {}
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                files[path.relative_to(destination).as_posix()] = {
                    "sha256": _hash(path), "mode": path.stat().st_mode & 0o777}
        manifest = {"format": 2 if deploy_files == LAUNCHER_DEPLOY_FILES else 1,
                    "files": files, "provenance": matched}
        if fallback_policy is not None:
            manifest["fallback_policy"] = _validate_fallback_policy(fallback_policy)
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        os.chmod(manifest_path, 0o444)
        for directory in sorted((p for p in destination.rglob("*") if p.is_dir()), reverse=True):
            os.chmod(directory, 0o555)
        os.chmod(destination, 0o555)
        return manifest
    except Exception:
        shutil.rmtree(destination)
        raise


def _bundle_layout(release):
    try:
        root_stat = release.lstat()
    except OSError as exc:
        raise BundleError("release directory is missing") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise BundleError("release path must be a real directory")
    files, directories = {}, {".": root_stat}
    try:
        paths = sorted(release.rglob("*"))
        for path in paths:
            entry = path.lstat()
            rel = path.relative_to(release).as_posix()
            if stat.S_ISLNK(entry.st_mode):
                raise BundleError(f"links are not allowed in a release: {rel}")
            if stat.S_ISDIR(entry.st_mode):
                directories[rel] = entry
            elif stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1:
                files[rel] = entry
            else:
                raise BundleError(f"release entry is not an owned regular file or directory: {rel}")
    except OSError as exc:
        raise BundleError("release layout could not be inspected safely") from exc
    if "manifest.json" not in files:
        raise BundleError("release manifest must be a regular file")
    if any(stat.S_IMODE(entry.st_mode) != 0o555 for entry in directories.values()):
        raise BundleError("release directory mode differs from sealed mode")
    if any(stat.S_IMODE(entry.st_mode) not in (0o444, 0o555) for entry in files.values()):
        raise BundleError("release file mode differs from sealed mode")
    if stat.S_IMODE(files["manifest.json"].st_mode) != 0o444:
        raise BundleError("release manifest mode differs from sealed mode")
    return files, directories


def _open_checked(path, expected_stat):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        actual = os.fstat(fd)
        if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
                or (actual.st_dev, actual.st_ino) != (expected_stat.st_dev, expected_stat.st_ino)
                or stat.S_IMODE(actual.st_mode) != stat.S_IMODE(expected_stat.st_mode)):
            raise BundleError(f"release file changed during validation: {path}")
        return fd
    except OSError as exc:
        if "fd" in locals():
            os.close(fd)
        raise BundleError(f"release file could not be opened safely: {path}") from exc
    except Exception:
        if "fd" in locals():
            os.close(fd)
        raise


def _read_checked(path, expected_stat):
    fd = _open_checked(path, expected_stat)
    with os.fdopen(fd, "rb") as stream:
        return stream.read()


def _hash_checked(path, expected_stat):
    value = hashlib.sha256()
    fd = _open_checked(path, expected_stat)
    with os.fdopen(fd, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_bundle(release):
    """Validate path types and exact membership before opening bundle contents."""
    release = Path(release)
    files, _ = _bundle_layout(release)
    manifest_path = release / "manifest.json"
    try:
        manifest = json.loads(_read_checked(manifest_path, files["manifest.json"]).decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise BundleError("release has no valid manifest") from exc
    except OSError as exc:
        raise BundleError("release manifest could not be read safely") from exc
    if not isinstance(manifest, dict) or manifest.get("format") not in (1, 2) or not isinstance(manifest.get("files"), dict):
        raise BundleError("unsupported release manifest")
    allowed_manifest_keys = {"format", "files", "provenance", "fallback_policy"}
    if not set(manifest) <= allowed_manifest_keys:
        raise BundleError("release manifest contains unrecognized fields")
    if "fallback_policy" in manifest:
        _validate_fallback_policy(manifest["fallback_policy"])
    expected_names = set(manifest["files"])
    actual_names = set(files) - {"manifest.json"}
    if actual_names != expected_names:
        raise BundleError("release membership differs from manifest")
    actual = {}
    for name in sorted(expected_names):
        entry = files[name]
        actual[name] = {"sha256": _hash_checked(release / name, entry),
                        "mode": stat.S_IMODE(entry.st_mode)}
    if actual != manifest["files"]:
        raise BundleError("release file hashes or modes differ from manifest")
    if not actual.get("native/homebox", {}).get("mode", 0) & 0o111:
        raise BundleError("native executable is not executable")
    required = {"native/homebox", "public/index.html", "kiosk/index.html", "kiosk/scan_codes.py",
                "ops/desktop_api.py", "ops/item_notes.py", "ops/label_layouts.py", "ops/label_render.py",
                *(f"deploy/{name}" for name in DEPLOY_FILES)}
    if manifest["format"] == 2:
        required.update(f"deploy/{name}" for name in LAUNCHER_FILES)
        required.add("label-ui/src/starter-documents.json")
    if not required <= actual.keys():
        raise BundleError("release is incomplete")
    source_files = [(release / name, name) for name in sorted(actual)
                    if name.startswith(("ops/", "kiosk/", "deploy/"))]
    provenance = manifest.get("provenance")
    source_map = provenance.get("runtime_files") if isinstance(provenance, dict) else None
    actual_source = {name: record["sha256"] for name, record in actual.items()
                     if name.startswith(("ops/", "kiosk/", "deploy/"))}
    if source_map != actual_source:
        raise BundleError("release runtime membership differs from source receipt")
    actual_public = {name.removeprefix("public/"): {"sha256": rec["sha256"], "size": files[name].st_size}
                     for name, rec in actual.items() if name.startswith("public/")}
    actual_labels = {name.removeprefix("label-ui/"): {"sha256": rec["sha256"], "size": files[name].st_size}
                     for name, rec in actual.items()
                     if name.startswith("label-ui/") and name != "label-ui/src/starter-documents.json"}
    source_modes = {name: record["mode"] for name, record in actual.items()
                    if name.startswith(("ops/", "kiosk/", "deploy/"))}
    matched = _provenance(provenance, binary_sha=actual["native/homebox"]["sha256"],
                          source_files=source_files, public_files=actual_public,
                          label_files=actual_labels, check_source_modes=False,
                          source_hashes=actual_source, source_modes=source_modes,
                          label_source_sha256=actual.get("label-ui/src/starter-documents.json", {}).get("sha256")
                          if manifest["format"] == 2 else None)
    if matched != provenance:
        raise BundleError("release provenance does not match its manifest")
    return manifest


def release_command(root, component, *, release=None):
    """Resolve and validate one immutable release, then describe its entrypoint."""
    entries = {"native": "run-homebox.py", "companion": "kiosk-server.py",
               "gateway": "workshop-gateway.py"}
    if component not in entries:
        raise BundleError("unknown release component")
    runtime_root = Path(root).resolve()
    selected = Path(release) if release is not None else runtime_root / "work/application-current"
    try:
        selected = selected.resolve(strict=True)
    except OSError as exc:
        raise BundleError("selected release is missing") from exc
    manifest = validate_bundle(selected)
    if manifest.get("format") != 2:
        raise BundleError("selected release has no packaged launcher")
    env = {"WORKSHOP_ROOT": str(runtime_root), "WORKSHOP_CODE_ROOT": str(selected),
           "HOMEBOX_UI_ROOT": str(selected / "public")}
    return [sys.executable, str(selected / "deploy" / entries[component])], env


JOURNAL_NAME = "application-release-journal.jsonl"
LOCK_NAME = ".application-release.lock"
JOURNAL_PHASES = frozenset({
    "transaction_prepared", "stop_requested", "stop_failed",
    "post_stop_preflight_passed", "candidate_selected",
    "candidate_exposure_possible", "candidate_started", "candidate_verified",
    "pre_exposure_failure", "recovery_attempted", "fallback_selected", "fallback_started",
    "fallback_verified", "previous_selected", "previous_started",
    "previous_verified", "recovery_failed",
})
TERMINAL_PHASES = frozenset({"stop_failed", "candidate_verified", "fallback_verified", "previous_verified"})
RECOVERY_RESTART_PHASES = JOURNAL_PHASES - TERMINAL_PHASES
PREVIOUS_PHASES = frozenset({"previous_selected", "previous_started", "previous_verified"})
FALLBACK_PHASES = frozenset({"fallback_selected", "fallback_started", "fallback_verified"})
FALLBACK_CHECKS = frozenset({
    "fallback_candidate_compatible_handlers",
    "fallback_reads_rooms_v1_v2_writes_v2_or_disables_mutation",
    "fallback_preserves_member_profile_loan_state",
    "same_runtime_stores_no_restore_or_physical_replay",
})


def _manifest_digest(release):
    return hashlib.sha256((Path(release) / "manifest.json").read_bytes()).hexdigest()


def _directory_fsync(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise BundleError("release transaction directory changed")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISDIR(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise BundleError("release transaction directory changed during fsync")
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _transaction_lock(root):
    work = Path(root) / "work"
    info = work.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise BundleError("release work directory is not a real directory")
    lock = work / LOCK_NAME
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            raise BundleError("release transaction lock is not an owned regular file")
        if st.st_mode & 0o077:
            raise BundleError("release transaction lock permissions are too broad")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BundleError("another release transaction is active") from exc
        current = work.lstat()
        if (not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode)
                or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
            raise BundleError("release work directory changed while acquiring lock")
        yield
    finally:
        os.close(fd)


def _append_transaction_event(path, envelope, phase):
    if phase not in JOURNAL_PHASES:
        raise BundleError("invalid release transaction phase")
    path = Path(path)
    existed = path.exists()
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            raise BundleError("release transaction journal is not an owned regular file")
        if st.st_mode & 0o077:
            raise BundleError("release transaction journal permissions are too broad")
        original_size = st.st_size
        row = {**envelope, "phase": phase, "recorded_at": time.time()}
        data = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        offset = 0
        try:
            while offset < len(data):
                written = os.write(fd, data[offset:])
                if written <= 0:
                    raise OSError("release transaction journal write made no progress")
                offset += written
            os.fsync(fd)
        except Exception as append_error:
            try:
                os.ftruncate(fd, original_size)
                os.fsync(fd)
            except Exception as cleanup_error:
                raise JournalAppendRollbackError(
                    f"journal append could not restore and fsync prior length {original_size}; "
                    f"transaction requires reconciliation: {cleanup_error}") from append_error
            raise
    finally:
        os.close(fd)
    if not existed:
        _directory_fsync(path.parent)


def _read_transaction_events(path, root):
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise BundleError("release transaction journal is missing or unsafe") from exc
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o077):
            raise BundleError("release transaction journal is not safely owned")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise BundleError("release transaction journal could not be read") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not lines:
        raise BundleError("release transaction journal is empty")
    required = {
        "schema", "transaction_id", "root", "previous", "candidate", "fallback",
        "work_dev", "work_ino",
        "previous_manifest_sha256", "candidate_manifest_sha256", "fallback_manifest_sha256",
        "fallback_receipt", "fallback_receipt_sha256", "backup_receipt_sha256",
        "phase", "recorded_at",
    }
    events, bindings = [], {}
    next_phases = {
        "transaction_prepared": {"stop_requested"},
        "stop_requested": {"stop_failed", "post_stop_preflight_passed", "pre_exposure_failure"},
        "post_stop_preflight_passed": {"candidate_selected", "pre_exposure_failure"},
        "candidate_selected": {"candidate_exposure_possible", "pre_exposure_failure"},
        # Exposure is already committed at this point. If recording the
        # start edge fails, selection must still recover to F and journal
        # that decision directly from the exposure marker.
        "candidate_exposure_possible": {"candidate_started", "fallback_selected", "recovery_failed"},
        "candidate_started": {"candidate_verified", "fallback_selected", "recovery_failed"},
        "pre_exposure_failure": {"previous_selected", "recovery_failed"},
        "fallback_selected": {"fallback_started", "recovery_failed"},
        "fallback_started": {"fallback_verified", "recovery_failed"},
        "previous_selected": {"previous_started", "recovery_failed"},
        "previous_started": {"previous_verified", "recovery_failed"},
        "stop_failed": set(), "candidate_verified": set(),
        "fallback_verified": set(), "previous_verified": set(),
        "recovery_failed": set(),
    }
    next_phases["recovery_attempted"] = {
        "recovery_attempted", "previous_selected", "fallback_selected",
    }
    for phase in RECOVERY_RESTART_PHASES:
        next_phases.setdefault(phase, set()).add("recovery_attempted")
    for line in lines:
        try:
            row = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise BundleError("release transaction journal is malformed") from exc
        if not isinstance(row, dict) or set(row) != required or row.get("schema") != 1:
            raise BundleError("release transaction journal has ambiguous fields")
        if row.get("root") != str(Path(root).resolve()):
            raise BundleError("release transaction journal is bound to another root")
        try:
            uuid.UUID(row.get("transaction_id"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise BundleError("release transaction journal id is invalid") from exc
        if (row.get("phase") not in JOURNAL_PHASES
                or not isinstance(row.get("recorded_at"), (int, float))
                or not math.isfinite(row["recorded_at"])):
            raise BundleError("release transaction journal phase is invalid")
        if any(not isinstance(row.get(key), str) or len(row[key]) != 64
               for key in ("previous_manifest_sha256", "candidate_manifest_sha256", "fallback_manifest_sha256",
                           "fallback_receipt_sha256")):
            raise BundleError("release transaction journal hashes are invalid")
        if any(not isinstance(row.get(key), int) or row[key] < 1 for key in ("work_dev", "work_ino")):
            raise BundleError("release transaction journal work identity is invalid")
        if not isinstance(row.get("fallback_receipt"), dict):
            raise BundleError("release transaction journal fallback receipt is invalid")
        backup_digest = row.get("backup_receipt_sha256")
        if backup_digest is not None and (not isinstance(backup_digest, str) or len(backup_digest) != 64):
            raise BundleError("release transaction journal backup receipt hash is invalid")
        if not isinstance(row.get("recorded_at"), (int, float)):
            raise BundleError("release transaction journal timestamp is invalid")
        binding = {key: row[key] for key in required - {"phase", "recorded_at"}}
        prior = bindings.setdefault(row["transaction_id"], binding)
        if prior != binding:
            raise BundleError("release transaction journal binding changed")
        if events:
            prior = events[-1]
            if row["transaction_id"] == prior["transaction_id"]:
                if row["phase"] not in next_phases[prior["phase"]]:
                    raise BundleError("release transaction journal has impossible phase progression")
            elif prior["phase"] not in TERMINAL_PHASES:
                raise BundleError("release transaction journal starts a new transaction before the prior one is terminal")
            elif row["phase"] != "transaction_prepared":
                raise BundleError("release transaction journal has an invalid transaction boundary")
        elif row["phase"] != "transaction_prepared":
            raise BundleError("release transaction journal does not start at transaction_prepared")
        prior_phases = {event["phase"] for event in events
                        if event["transaction_id"] == row["transaction_id"]}
        transaction_phases = prior_phases | {row["phase"]}
        if (transaction_phases & PREVIOUS_PHASES
                and "candidate_exposure_possible" in transaction_phases):
            raise BundleError("release transaction journal selects O after possible candidate exposure")
        if (transaction_phases & FALLBACK_PHASES
                and "candidate_exposure_possible" not in transaction_phases):
            raise BundleError("release transaction journal selects F without positive exposure evidence")
        events.append(row)
    return events


def _validate_fallback_receipt(receipt, previous, candidate, fallback):
    expected_keys = {"execution_scope", "checks", "fallback_policy_sha256"}
    for label in ("previous", "candidate", "fallback"):
        expected_keys.update({f"{label}_bundle_manifest_sha256", f"{label}_native_sha256"})
    if (not isinstance(receipt, dict) or set(receipt) != expected_keys
            or receipt.get("execution_scope") not in ("fixture-only", "production-matched")):
        raise BundleError("fallback receipt schema is invalid or missing")
    expected = {}
    for name, path in (("previous", previous), ("candidate", candidate), ("fallback", fallback)):
        manifest = validate_bundle(path)
        if name == "fallback":
            capability = _require_workshop_compatibility(manifest, role="fallback")
            policy = _validate_fallback_policy(manifest.get("fallback_policy"))
            if (policy["roomsv2_read_versions"] != capability["read_versions"]
                    or policy["workshop_mutation_mode"] != capability["write_mode"]):
                raise BundleError("fallback policy does not match its artifact-bound Workshop capability")
        expected[f"{name}_bundle_manifest_sha256"] = _manifest_digest(path)
        expected[f"{name}_native_sha256"] = manifest["provenance"]["native_sha256"]
    fallback_manifest = validate_bundle(fallback)
    candidate_digest = _manifest_digest(candidate)
    policy = _validate_fallback_policy(fallback_manifest.get("fallback_policy"))
    if (policy["candidate_manifest_sha256"] != candidate_digest
            or policy["evidence_scope"] != receipt.get("execution_scope")
            or receipt.get("fallback_policy_sha256") != _json_hash(policy)):
        raise BundleError("fallback policy is not bound to this candidate and receipt")
    _validate_fallback_code_pair(previous, candidate, fallback)
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise BundleError("fallback receipt does not bind the exact O/C/F bundle set")
    checks = receipt.get("checks")
    if (not isinstance(checks, dict) or set(checks) != FALLBACK_CHECKS
            or any(checks.get(name) is not True for name in FALLBACK_CHECKS)):
        raise BundleError("fallback receipt lacks compatible recovery checks")
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_fallback_code_pair(previous, candidate, fallback):
    previous_files = validate_bundle(previous)["files"]
    candidate_files = validate_bundle(candidate)["files"]
    fallback_files = validate_bundle(fallback)["files"]
    code_names = {name for name in candidate_files
                  if name == "native/homebox" or name.startswith("ops/")
                  or name.startswith("deploy/") or (name.startswith("kiosk/") and name.endswith(".py"))}
    code_names.update(name for name in candidate_files if name.startswith("label-ui/"))
    if (not code_names or not code_names <= fallback_files.keys()
            or any(candidate_files[name]["sha256"] != fallback_files[name]["sha256"] for name in code_names)):
        raise BundleError("fallback does not retain candidate-compatible code and native capability")
    old_static = {name: row["sha256"] for name, row in previous_files.items()
                  if name.startswith("public/") or (name.startswith("kiosk/") and not name.endswith(".py"))}
    fallback_static = {name: row["sha256"] for name, row in fallback_files.items()
                       if name.startswith("public/") or (name.startswith("kiosk/") and not name.endswith(".py"))}
    if old_static != fallback_static:
        raise BundleError("fallback does not retain the captured previous public and Terminal tree")


def _select_bundle_durable(root, release, *, fallback, fallback_receipt,
                           backup_receipt_sha256, run_services, verify):
    runtime = Path(root).resolve(strict=True)
    selector = runtime / "work" / "application-current"
    work_stat = selector.parent.lstat()
    if not stat.S_ISDIR(work_stat.st_mode) or stat.S_ISLNK(work_stat.st_mode):
        raise BundleError("release work directory must be a real directory")
    try:
        pointer_stat = selector.lstat()
        previous = selector.resolve(strict=True)
        candidate = Path(release).resolve(strict=True)
        fallback = Path(fallback).resolve(strict=True)
    except OSError as exc:
        raise BundleError("O, C and F releases must all exist before service stop") from exc
    if not stat.S_ISLNK(pointer_stat.st_mode):
        raise BundleError("application-current must be one real symlink")
    paths = (previous, candidate, fallback)
    if len(set(paths)) != 3:
        raise BundleError("O, C and F must be separate release bundles")
    manifests = tuple(validate_bundle(path) for path in paths)
    if any(manifest.get("format") != 2 for manifest in manifests):
        raise BundleError("O, C and F must all be launcher-capable format-2 bundles")
    _require_workshop_compatibility(manifests[0], role="previous")
    _require_workshop_compatibility(manifests[1], role="candidate", require_writer=True)
    _require_workshop_compatibility(manifests[2], role="fallback")
    receipt_digest = _validate_fallback_receipt(fallback_receipt, *paths)
    if (fallback_receipt["execution_scope"] == "production-matched"
            and (not isinstance(backup_receipt_sha256, str) or len(backup_receipt_sha256) != 64)):
        raise BundleError("production selection requires a bound whole-store cold-backup receipt")
    if backup_receipt_sha256 is not None and (not isinstance(backup_receipt_sha256, str)
                                               or len(backup_receipt_sha256) != 64):
        raise BundleError("cold-backup receipt hash is invalid")
    snapshots = tuple(_manifest_digest(path) for path in paths)
    transaction_id = str(uuid.uuid4())
    envelope = {
        "schema": 1, "transaction_id": transaction_id, "root": str(runtime),
        "previous": str(previous), "candidate": str(candidate), "fallback": str(fallback),
        "work_dev": work_stat.st_dev, "work_ino": work_stat.st_ino,
        "previous_manifest_sha256": snapshots[0], "candidate_manifest_sha256": snapshots[1],
        "fallback_manifest_sha256": snapshots[2], "fallback_receipt": fallback_receipt,
        "fallback_receipt_sha256": receipt_digest,
        "backup_receipt_sha256": backup_receipt_sha256,
    }
    journal = selector.parent / JOURNAL_NAME
    stop = ["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"]
    start = ["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"]

    def assert_work():
        current = selector.parent.lstat()
        if (not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode)
                or (current.st_dev, current.st_ino) != (work_stat.st_dev, work_stat.st_ino)):
            raise BundleError("release work directory changed")

    def assert_selected(expected):
        assert_work()
        try:
            pointer = selector.lstat()
            selected = selector.resolve(strict=True)
        except OSError as exc:
            raise BundleError("application-current selector changed") from exc
        if not stat.S_ISLNK(pointer.st_mode) or selected != expected:
            raise BundleError(f"application-current selector changed (expected {expected}, found {selected})")

    def assert_unchanged(index):
        path, expected, digest = paths[index], manifests[index], snapshots[index]
        actual = validate_bundle(path)
        if actual != expected or _manifest_digest(path) != digest:
            raise BundleError(f"{('previous','candidate','fallback')[index]} bundle changed after preflight")

    def replace(target):
        assert_work()
        temporary = selector.with_name(f".application-current.{uuid.uuid4().hex}.next")
        try:
            os.symlink(os.path.relpath(target, selector.parent), temporary, target_is_directory=True)
            assert_work()
            os.replace(temporary, selector)
            _directory_fsync(selector.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def finish_previous(primary_error):
        try:
            selected = selector.resolve(strict=True)
            if selected not in (previous, candidate):
                raise BundleError(f"foreign selector preserved at {selected}")
            if selected == candidate:
                assert_unchanged(0)
                replace(previous)
            assert_selected(previous)
            assert_unchanged(0)
            _append_transaction_event(journal, envelope, "previous_selected")
            _append_transaction_event(journal, envelope, "previous_started")
            run_services(list(start))
            assert_selected(previous)
            assert_unchanged(0)
            verify(previous)
            assert_selected(previous)
            assert_unchanged(0)
            _append_transaction_event(journal, envelope, "previous_verified")
        except Exception as recovery_error:
            if isinstance(recovery_error, JournalAppendRollbackError):
                raise BundleError(f"selection failed: {primary_error}; previous recovery stopped because "
                                  f"journal cleanup failed; no further journal or service callbacks ran; "
                                  f"application-current points to {selector.resolve(strict=False)}; "
                                  f"reconciliation required: {recovery_error}") from primary_error
            journal_recording_error = None
            try:
                _append_transaction_event(journal, envelope, "recovery_failed")
            except Exception as exc:
                journal_recording_error = exc
            recording_detail = (f"; recovery_failed journal recording also failed: {journal_recording_error}; "
                                f"transaction remains unresolved and requires reconciliation"
                                if journal_recording_error else "")
            raise BundleError(f"selection failed: {primary_error}; previous recovery failed: {recovery_error}; "
                              f"application-current points to {selector.resolve(strict=False)}{recording_detail}") from primary_error
        raise BundleError(f"selection failed: {primary_error}; previous bundle restored and verified at {previous}") from primary_error

    def finish_fallback(primary_error):
        try:
            assert_selected(candidate)
            run_services(list(stop))
            assert_selected(candidate)
            assert_unchanged(2)
            replace(fallback)
            assert_selected(fallback)
            assert_unchanged(2)
            _append_transaction_event(journal, envelope, "fallback_selected")
            _append_transaction_event(journal, envelope, "fallback_started")
            run_services(list(start))
            assert_selected(fallback)
            assert_unchanged(2)
            verify(fallback)
            assert_selected(fallback)
            assert_unchanged(2)
            _append_transaction_event(journal, envelope, "fallback_verified")
        except Exception as recovery_error:
            if isinstance(recovery_error, JournalAppendRollbackError):
                raise BundleError(f"selection failed: {primary_error}; compatible F recovery stopped because "
                                  f"journal cleanup failed; no further journal or service callbacks ran; "
                                  f"application-current points to {selector.resolve(strict=False)}; "
                                  f"reconciliation required: {recovery_error}") from primary_error
            journal_recording_error = None
            try:
                _append_transaction_event(journal, envelope, "recovery_failed")
            except Exception as exc:
                journal_recording_error = exc
            recording_detail = (f"; recovery_failed journal recording also failed: {journal_recording_error}; "
                                f"transaction remains unresolved and requires reconciliation"
                                if journal_recording_error else "")
            raise BundleError(f"selection failed: {primary_error}; compatible F recovery failed: {recovery_error}; "
                              f"application-current points to {selector.resolve(strict=False)}{recording_detail}") from primary_error
        raise BundleError(f"selection failed: {primary_error}; compatible F selected and verified at {fallback}") from primary_error

    def record_pre_exposure_failure(primary_error):
        try:
            _append_transaction_event(journal, envelope, "pre_exposure_failure")
        except JournalAppendRollbackError as journal_error:
            raise BundleError(f"pre-exposure operation failed: {primary_error}; recording "
                              f"pre_exposure_failure also failed and journal cleanup could not be proven: "
                              f"{journal_error}; application-current points to "
                              f"{selector.resolve(strict=False)}; services are stopped; no recovery callbacks "
                              f"ran; reconciliation required") from primary_error
        except Exception as journal_error:
            raise BundleError(f"pre-exposure operation failed: {primary_error}; recording "
                              f"pre_exposure_failure also failed: {journal_error}; application-current points "
                              f"to {selector.resolve(strict=False)}; services are stopped; no recovery "
                              f"callbacks ran; prior journal remains intact and recovery can resume") from primary_error

    with _transaction_lock(runtime):
        if journal.exists():
            events = _read_transaction_events(journal, runtime)
            if events[-1]["phase"] not in TERMINAL_PHASES:
                raise BundleError("an unresolved release transaction requires recovery before selection")
        _append_transaction_event(journal, envelope, "transaction_prepared")
        _append_transaction_event(journal, envelope, "stop_requested")
        try:
            run_services(list(stop))
        except Exception as exc:
            journal_recording_error = None
            try:
                _append_transaction_event(journal, envelope, "stop_failed")
            except Exception as journal_error:
                journal_recording_error = journal_error
            recording_detail = (f"; stop_failed journal recording also failed: {journal_recording_error}; "
                                f"transaction remains unresolved and requires reconciliation"
                                if journal_recording_error else "")
            raise BundleError(f"initial stop failed; selector unchanged and no recovery attempted: {exc}"
                              f"{recording_detail}") from exc
        try:
            assert_selected(previous)
            for index in range(3):
                assert_unchanged(index)
            _append_transaction_event(journal, envelope, "post_stop_preflight_passed")
        except Exception as exc:
            if isinstance(exc, JournalAppendRollbackError):
                raise BundleError(f"pre-exposure journal cleanup failed; selector preserved at "
                                  f"{selector.resolve(strict=False)}; no recovery callbacks ran; "
                                  f"reconciliation required: {exc}") from exc
            record_pre_exposure_failure(exc)
            finish_previous(exc)
        try:
            replace(candidate)
            assert_selected(candidate)
            assert_unchanged(1)
            _append_transaction_event(journal, envelope, "candidate_selected")
        except Exception as exc:
            if isinstance(exc, JournalAppendRollbackError):
                raise BundleError(f"candidate selection journal cleanup failed; selector preserved at "
                                  f"{selector.resolve(strict=False)}; no recovery callbacks ran; "
                                  f"reconciliation required: {exc}") from exc
            record_pre_exposure_failure(exc)
            finish_previous(exc)
        # This record is file- and directory-fsynced before any start callback.
        # If it cannot be durably recorded, leave the services stopped and
        # require explicit journal reconciliation; do not infer O is safe.
        try:
            _append_transaction_event(journal, envelope, "candidate_exposure_possible")
        except Exception as exc:
            raise BundleError(
                "candidate is selected but exposure marker could not be durably recorded; "
                f"selector preserved and transaction requires reconciliation: {exc}") from exc
        candidate_start_attempted = False
        try:
            _append_transaction_event(journal, envelope, "candidate_started")
            candidate_start_attempted = True
            run_services(list(start))
            assert_selected(candidate)
            assert_unchanged(1)
            verify(candidate)
            assert_selected(candidate)
            assert_unchanged(1)
            _append_transaction_event(journal, envelope, "candidate_verified")
            return
        except JournalAppendRollbackError as exc:
            start_detail = ("candidate startup callback may have run" if candidate_start_attempted
                            else "candidate startup callback was not invoked")
            raise BundleError(f"journal cleanup failed; {start_detail}; selector preserved at "
                              f"{selector.resolve(strict=False)}; no further recovery callbacks ran; "
                              f"reconciliation required: {exc}") from exc
        except Exception as exc:
            finish_fallback(exc)


def select_bundle(root, release, *, run_services, verify, fallback=None, fallback_receipt=None,
                  backup_receipt_sha256=None):
    """Select one matched bundle; production transitions require journal-bound O/C/F proof."""
    if fallback is None:
        raise BundleError("selection requires a bound O/C/F transaction and compatible F bundle")
    if fallback_receipt is None:
        raise BundleError("fallback compatibility receipt is required")
    return _select_bundle_durable(root, release, fallback=fallback,
                                  fallback_receipt=fallback_receipt,
                                  backup_receipt_sha256=backup_receipt_sha256,
                                  run_services=run_services, verify=verify)


def recover_interrupted(root, *, run_services, verify):
    """Recover an incomplete O/C/F transaction from its transaction-bound journal."""
    runtime = Path(root).resolve(strict=True)
    selector = runtime / "work" / "application-current"
    journal = selector.parent / JOURNAL_NAME
    with _transaction_lock(runtime):
        events = _read_transaction_events(journal, runtime)
        latest_id = events[-1]["transaction_id"]
        transaction = [row for row in events if row["transaction_id"] == latest_id]
        if transaction[-1]["phase"] in TERMINAL_PHASES:
            raise BundleError("no interrupted release transaction requires recovery")
        latest = transaction[-1]
        work_stat = selector.parent.lstat()
        if (not stat.S_ISDIR(work_stat.st_mode) or stat.S_ISLNK(work_stat.st_mode)
                or (work_stat.st_dev, work_stat.st_ino) != (latest["work_dev"], latest["work_ino"])):
            raise BundleError("release work directory changed since transaction was recorded")
        work_identity = (work_stat.st_dev, work_stat.st_ino)

        def assert_work():
            current_work = selector.parent.lstat()
            if (not stat.S_ISDIR(current_work.st_mode) or stat.S_ISLNK(current_work.st_mode)
                    or (current_work.st_dev, current_work.st_ino) != work_identity):
                raise BundleError("release work directory changed during recovery")

        pointer_stat = selector.lstat()
        if not stat.S_ISLNK(pointer_stat.st_mode):
            raise BundleError("application-current changed to a non-symlink during recovery")
        paths = {key: Path(latest[key]).resolve(strict=True) for key in ("previous", "candidate", "fallback")}
        current = selector.resolve(strict=True)
        exposure = any(row["phase"] == "candidate_exposure_possible" for row in transaction)
        allowed_current = (paths["candidate"], paths["fallback"]) if exposure else (paths["previous"], paths["candidate"])
        if current not in allowed_current:
            raise BundleError(f"foreign selector preserved at {current}; recovery requires coordinator review")
        manifests = {key: validate_bundle(path) for key, path in paths.items()}
        if any(manifest.get("format") != 2 for manifest in manifests.values()):
            raise BundleError("interrupted O/C/F bundles are not launcher-capable")
        digests = {key: _manifest_digest(path) for key, path in paths.items()}
        if any(digests[key] != latest[f"{key}_manifest_sha256"]
               for key in ("previous", "candidate", "fallback")):
            raise BundleError("interrupted O/C/F bundle manifest changed")

        def assert_bundle_unchanged(name):
            try:
                current_manifest = validate_bundle(paths[name])
                current_digest = _manifest_digest(paths[name])
            except Exception as exc:
                raise BundleError(f"{name} bundle changed during recovery: {exc}") from exc
            if current_manifest != manifests[name] or current_digest != digests[name]:
                raise BundleError(f"{name} bundle changed during recovery")

        proof = latest["fallback_receipt"]
        proof_hash = hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if proof_hash != latest["fallback_receipt_sha256"]:
            raise BundleError("interrupted fallback proof changed")
        _validate_fallback_receipt(proof, paths["previous"], paths["candidate"], paths["fallback"])
        if exposure:
            target, selected_phase, started_phase, verified_phase, result = (
                paths["fallback"], "fallback_selected", "fallback_started", "fallback_verified", "fallback_verified")
        else:
            target, selected_phase, started_phase, verified_phase, result = (
                paths["previous"], "previous_selected", "previous_started", "previous_verified", "previous_verified")
        before_stop = current
        recovery_envelope = {k: latest[k] for k in latest if k not in ("phase", "recorded_at")}
        _append_transaction_event(journal, recovery_envelope, "recovery_attempted")
        run_services(["stop", "homebox-workshop-gateway", "homebox-companion", "homebox-native"])
        assert_work()
        for name in paths:
            assert_bundle_unchanged(name)
        current = selector.resolve(strict=True)
        if current != before_stop:
            raise BundleError(f"selector changed during recovery stop; foreign selector preserved at {current}")
        if current != target:
            temporary = selector.with_name(f".application-current.{uuid.uuid4().hex}.next")
            try:
                os.symlink(os.path.relpath(target, selector.parent), temporary, target_is_directory=True)
                assert_work()
                if selector.resolve(strict=True) != before_stop:
                    raise BundleError("selector drift detected before recovery replace")
                os.replace(temporary, selector)
                _directory_fsync(selector.parent)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    temporary.unlink()
        if selector.resolve(strict=True) != target:
            raise BundleError("recovery selector did not resolve to the selected bundle")
        assert_bundle_unchanged("fallback" if exposure else "previous")
        _append_transaction_event(journal, recovery_envelope, selected_phase)
        _append_transaction_event(journal, recovery_envelope, started_phase)
        run_services(["start", "homebox-native", "homebox-companion", "homebox-workshop-gateway"])
        assert_work()
        if selector.resolve(strict=True) != target:
            raise BundleError("selector changed while recovery services started")
        assert_bundle_unchanged("fallback" if exposure else "previous")
        verify(target)
        assert_work()
        if selector.resolve(strict=True) != target:
            raise BundleError("selector changed during recovery verification")
        if any(_manifest_digest(paths[name]) != digests[name] for name in paths):
            raise BundleError("selected bundle changed during recovery verification")
        assert_bundle_unchanged("fallback" if exposure else "previous")
        _append_transaction_event(journal, recovery_envelope, verified_phase)
        return result
