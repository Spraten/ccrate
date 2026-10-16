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
                "ops/label_render.py", "kiosk/scan_codes.py", "kiosk/decode_codes.py",
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
    source_files =5ÓÎ÷¶‰žËkºwµçeÍ”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½ÉôìÁÉ•Ù¥½ÕÌÉ•½Ù•Éä™…¥±•èíÉ•½Ù•Éå}•ÉÉ½Éôì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹ÐÁ½¥¹ÑÌÑ¼íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥õíÉ•½É‘¥¹}‘•Ñ…¥±ôˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½ÉôìÁÉ•Ù¥½ÕÌ‰Õ¹‘±”É•ÍÑ½É•…¹Ù•É¥™¥•…ÐíÁÉ•Ù¥½ÕÍôˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È((€€€‘•˜™¥¹¥Í¡}™…±±‰…¬¡ÁÉ¥µ…Éå}•ÉÉ½È¤è(€€€€€€€ÑÉäè(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡±¥ÍÐ¡ÍÑ½À¤¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• È¤(€€€€€€€€€€€É•Á±…”¡™…±±‰…¬¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡™…±±‰…¬¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• È¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰™…±±‰…­}Í•±•Ñ•ˆ¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰™…±±‰…­}ÍÑ…ÉÑ•ˆ¤(€€€€€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡±¥ÍÐ¡ÍÑ…ÉÐ¤¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡™…±±‰…¬¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• È¤(€€€€€€€€€€€Ù•É¥™ä¡™…±±‰…¬¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡™…±±‰…¬¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• È¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰™…±±‰…­}Ù•É¥™¥•ˆ¤(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…ÌÉ•½Ù•Éå}•ÉÉ½Èè(€€€€€€€€€€€¥˜¥Í¥¹ÍÑ…¹”¡É•½Ù•Éå}•ÉÉ½È°)½ÕÉ¹…±ÁÁ•¹‘I½±±‰…­ÉÉ½È¤è(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½Éôì½µÁ…Ñ¥‰±”É•½Ù•ÉäÍÑ½ÁÁ•‰•…ÕÍ”€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰©½ÕÉ¹…°±•…¹ÕÀ™…¥±•ì¹¼™ÕÉÑ¡•È©½ÕÉ¹…°½ÈÍ•ÉÙ¥”…±±‰…­ÌÉ…¸ì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹ÐÁ½¥¹ÑÌÑ¼íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰É•½¹¥±¥…Ñ¥½¸É•ÅÕ¥É•èíÉ•½Ù•Éå}•ÉÉ½Éôˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È(€€€€€€€€€€€©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È€ô9½¹”(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰É•½Ù•Éå}™…¥±•ˆ¤(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€€€€€©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È€ô•áŒ(€€€€€€€€€€€É•½É‘¥¹}‘•Ñ…¥°€ô€¡˜ˆìÉ•½Ù•Éå}™…¥±•©½ÕÉ¹…°É•½É‘¥¹œ…±Í¼™…¥±•èí©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½Éôì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰ÑÉ…¹Í…Ñ¥½¸É•µ…¥¹ÌÕ¹É•Í½±Ù•…¹É•ÅÕ¥É•ÌÉ•½¹¥±¥…Ñ¥½¸ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¥˜©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È•±Í”€ˆˆ¤(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½Éôì½µÁ…Ñ¥‰±”É•½Ù•Éä™…¥±•èíÉ•½Ù•Éå}•ÉÉ½Éôì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹ÐÁ½¥¹ÑÌÑ¼íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥õíÉ•½É‘¥¹}‘•Ñ…¥±ôˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½Éôì½µÁ…Ñ¥‰±”Í•±•Ñ•…¹Ù•É¥™¥•…Ðí™…±±‰…­ôˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È((€€€‘•˜É•½É‘}ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”¡ÁÉ¥µ…Éå}•ÉÉ½È¤è(€€€€€€€ÑÉäè(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”ˆ¤(€€€€€€€•á•ÁÐ)½ÕÉ¹…±ÁÁ•¹‘I½±±‰…­ÉÉ½È…Ì©½ÕÉ¹…±}•ÉÉ½Èè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰ÁÉ”µ•áÁ½ÍÕÉ”½Á•É…Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½ÉôìÉ•½É‘¥¹œ€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”…±Í¼™…¥±•…¹©½ÕÉ¹…°±•…¹ÕÀ½Õ±¹½Ð‰”ÁÉ½Ù•¸è€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰í©½ÕÉ¹…±}•ÉÉ½Éôì…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹ÐÁ½¥¹ÑÌÑ¼€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôìÍ•ÉÙ¥•Ì…É”ÍÑ½ÁÁ•ì¹¼É•½Ù•Éä…±±‰…­Ì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰É…¸ìÉ•½¹¥±¥…Ñ¥½¸É•ÅÕ¥É•ˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì©½ÕÉ¹…±}•ÉÉ½Èè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰ÁÉ”µ•áÁ½ÍÕÉ”½Á•É…Ñ¥½¸™…¥±•èíÁÉ¥µ…Éå}•ÉÉ½ÉôìÉ•½É‘¥¹œ€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”…±Í¼™…¥±•èí©½ÕÉ¹…±}•ÉÉ½Éôì…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹ÐÁ½¥¹ÑÌ€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰Ñ¼íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôìÍ•ÉÙ¥•Ì…É”ÍÑ½ÁÁ•ì¹¼É•½Ù•Éä€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰…±±‰…­ÌÉ…¸ìÁÉ¥½È©½ÕÉ¹…°É•µ…¥¹Ì¥¹Ñ…Ð…¹É•½Ù•Éä…¸É•ÍÕµ”ˆ¤™É½´ÁÉ¥µ…Éå}•ÉÉ½È((€€€Ý¥Ñ }ÑÉ…¹Í…Ñ¥½¹}±½¬¡ÉÕ¹Ñ¥µ”¤è(€€€€€€€¥˜©½ÕÉ¹…°¹•á¥ÍÑÌ ¤è(€€€€€€€€€€€•Ù•¹ÑÌ€ô}É•…‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹ÑÌ¡©½ÕÉ¹…°°ÉÕ¹Ñ¥µ”¤(€€€€€€€€€€€¥˜•Ù•¹ÑÍl´Åul‰Á¡…Í”‰t¹½Ð¥¸QI5%91}A!MLè(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰…¸Õ¹É•Í½±Ù•É•±•…Í”ÑÉ…¹Í…Ñ¥½¸É•ÅÕ¥É•ÌÉ•½Ù•Éä‰•™½É”Í•±•Ñ¥½¸ˆ¤(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰ÑÉ…¹Í…Ñ¥½¹}ÁÉ•Á…É•ˆ¤(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰ÍÑ½Á}É•ÅÕ•ÍÑ•ˆ¤(€€€€€€€ÑÉäè(€€€€€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡±¥ÍÐ¡ÍÑ½À¤¤(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È€ô9½¹”(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰ÍÑ½Á}™…¥±•ˆ¤(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì©½ÕÉ¹…±}•ÉÉ½Èè(€€€€€€€€€€€€€€€©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È€ô©½ÕÉ¹…±}•ÉÉ½È(€€€€€€€€€€€É•½É‘¥¹}‘•Ñ…¥°€ô€¡˜ˆìÍÑ½Á}™…¥±•©½ÕÉ¹…°É•½É‘¥¹œ…±Í¼™…¥±•èí©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½Éôì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰ÑÉ…¹Í…Ñ¥½¸É•µ…¥¹ÌÕ¹É•Í½±Ù•…¹É•ÅÕ¥É•ÌÉ•½¹¥±¥…Ñ¥½¸ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€¥˜©½ÕÉ¹…±}É•½É‘¥¹}•ÉÉ½È•±Í”€ˆˆ¤(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰¥¹¥Ñ¥…°ÍÑ½À™…¥±•ìÍ•±•Ñ½ÈÕ¹¡…¹•…¹¹¼É•½Ù•Éä…ÑÑ•µÁÑ•èí•áôˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰íÉ•½É‘¥¹}‘•Ñ…¥±ôˆ¤™É½´•áŒ(€€€€€€€ÑÉäè(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡ÁÉ•Ù¥½ÕÌ¤(€€€€€€€€€€€™½È¥¹‘•à¥¸É…¹” Ì¤è(€€€€€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹•¡¥¹‘•à¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰Á½ÍÑ}ÍÑ½Á}ÁÉ•™±¥¡Ñ}Á…ÍÍ•ˆ¤(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€¥˜¥Í¥¹ÍÑ…¹”¡•áŒ°)½ÕÉ¹…±ÁÁ•¹‘I½±±‰…­ÉÉ½È¤è(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰ÁÉ”µ•áÁ½ÍÕÉ”©½ÕÉ¹…°±•…¹ÕÀ™…¥±•ìÍ•±•Ñ½ÈÁÉ•Í•ÉÙ•…Ð€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôì¹¼É•½Ù•Éä…±±‰…­ÌÉ…¸ì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰É•½¹¥±¥…Ñ¥½¸É•ÅÕ¥É•èí•áôˆ¤™É½´•áŒ(€€€€€€€€€€€É•½É‘}ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”¡•áŒ¤(€€€€€€€€€€€™¥¹¥Í¡}ÁÉ•Ù¥½ÕÌ¡•áŒ¤(€€€€€€€ÑÉäè(€€€€€€€€€€€É•Á±…”¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• Ä¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰…¹‘¥‘…Ñ•}Í•±•Ñ•ˆ¤(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€¥˜¥Í¥¹ÍÑ…¹”¡•áŒ°)½ÕÉ¹…±ÁÁ•¹‘I½±±‰…­ÉÉ½È¤è(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰…¹‘¥‘…Ñ”Í•±•Ñ¥½¸©½ÕÉ¹…°±•…¹ÕÀ™…¥±•ìÍ•±•Ñ½ÈÁÉ•Í•ÉÙ•…Ð€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôì¹¼É•½Ù•Éä…±±‰…­ÌÉ…¸ì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰É•½¹¥±¥…Ñ¥½¸É•ÅÕ¥É•èí•áôˆ¤™É½´•áŒ(€€€€€€€€€€€É•½É‘}ÁÉ•}•áÁ½ÍÕÉ•}™…¥±ÕÉ”¡•áŒ¤(€€€€€€€€€€€™¥¹¥Í¡}ÁÉ•Ù¥½ÕÌ¡•áŒ¤(€€€€€€€€ŒQ¡¥ÌÉ•½É¥Ì™¥±”´…¹‘¥É•Ñ½Éäµ™Íå¹•‰•™½É”…¹äÍÑ…ÉÐ…±±‰…¬¸(€€€€€€€€Œ%˜¥Ð…¹¹½Ð‰”‘ÕÉ…‰±äÉ•½É‘•°±•…Ù”Ñ¡”Í•ÉÙ¥•ÌÍÑ½ÁÁ•…¹(€€€€€€€€ŒÉ•ÅÕ¥É”•áÁ±¥¥Ð©½ÕÉ¹…°É•½¹¥±¥…Ñ¥½¸ì‘¼¹½Ð¥¹™•È<¥ÌÍ…™”¸(€€€€€€€ÑÉäè(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰…¹‘¥‘…Ñ•}•áÁ½ÍÕÉ•}Á½ÍÍ¥‰±”ˆ¤(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È (€€€€€€€€€€€€€€€€‰…¹‘¥‘…Ñ”¥ÌÍ•±•Ñ•‰ÕÐ•áÁ½ÍÕÉ”µ…É­•È½Õ±¹½Ð‰”‘ÕÉ…‰±äÉ•½É‘•ì€ˆ(€€€€€€€€€€€€€€€˜‰Í•±•Ñ½ÈÁÉ•Í•ÉÙ•…¹ÑÉ…¹Í…Ñ¥½¸É•ÅÕ¥É•ÌÉ•½¹¥±¥…Ñ¥½¸èí•áôˆ¤™É½´•áŒ(€€€€€€€…¹‘¥‘…Ñ•}ÍÑ…ÉÑ}…ÑÑ•µÁÑ•€ô…±Í”(€€€€€€€ÑÉäè(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰…¹‘¥‘…Ñ•}ÍÑ…ÉÑ•ˆ¤(€€€€€€€€€€€…¹‘¥‘…Ñ•}ÍÑ…ÉÑ}…ÑÑ•µÁÑ•€ôQÉÕ”(€€€€€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡±¥ÍÐ¡ÍÑ…ÉÐ¤¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• Ä¤(€€€€€€€€€€€Ù•É¥™ä¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Í•±•Ñ•¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€…ÍÍ•ÉÑ}Õ¹¡…¹• Ä¤(€€€€€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°•¹Ù•±½Á”°€‰…¹‘¥‘…Ñ•}Ù•É¥™¥•ˆ¤(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€•á•ÁÐ)½ÕÉ¹…±ÁÁ•¹‘I½±±‰…­ÉÉ½È…Ì•áŒè(€€€€€€€€€€€ÍÑ…ÉÑ}‘•Ñ…¥°€ô€ ‰…¹‘¥‘…Ñ”ÍÑ…ÉÑÕÀ…±±‰…¬µ…ä¡…Ù”ÉÕ¸ˆ¥˜…¹‘¥‘…Ñ•}ÍÑ…ÉÑ}…ÑÑ•µÁÑ•(€€€€€€€€€€€€€€€€€€€€€€€€€€€•±Í”€‰…¹‘¥‘…Ñ”ÍÑ…ÉÑÕÀ…±±‰…¬Ý…Ì¹½Ð¥¹Ù½­•ˆ¤(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰©½ÕÉ¹…°±•…¹ÕÀ™…¥±•ìíÍÑ…ÉÑ}‘•Ñ…¥±ôìÍ•±•Ñ½ÈÁÉ•Í•ÉÙ•…Ð€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰íÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥Ðõ…±Í”¥ôì¹¼™ÕÉÑ¡•ÈÉ•½Ù•Éä…±±‰…­ÌÉ…¸ì€ˆ(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€˜‰É•½¹¥±¥…Ñ¥½¸É•ÅÕ¥É•èí•áôˆ¤™É½´•áŒ(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€™¥¹¥Í¡}™…±±‰…¬¡•áŒ¤(()‘•˜Í•±•Ñ}‰Õ¹‘±”¡É½½Ð°É•±•…Í”°€¨°ÉÕ¹}Í•ÉÙ¥•Ì°Ù•É¥™ä°™…±±‰…¬õ9½¹”°™…±±‰…­}É••¥ÁÐõ9½¹”°(€€€€€€€€€€€€€€€€€‰…­ÕÁ}É••¥ÁÑ}Í¡„ÈÔØõ9½¹”¤è(€€€€ˆˆ‰M•±•Ð½¹”µ…Ñ¡•‰Õ¹‘±”ìÁÉ½‘ÕÑ¥½¸ÑÉ…¹Í¥Ñ¥½¹ÌÉ•ÅÕ¥É”©½ÕÉ¹…°µ‰½Õ¹<½½ÁÉ½½˜¸ˆˆˆ(€€€¥˜™…±±‰…¬¥Ì9½¹”è(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰Í•±•Ñ¥½¸É•ÅÕ¥É•Ì„‰½Õ¹<½½ÑÉ…¹Í…Ñ¥½¸…¹½µÁ…Ñ¥‰±”‰Õ¹‘±”ˆ¤(€€€¥˜™…±±‰…­}É••¥ÁÐ¥Ì9½¹”è(€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰™…±±‰…¬½µÁ…Ñ¥‰¥±¥ÑäÉ••¥ÁÐ¥ÌÉ•ÅÕ¥É•ˆ¤(€€€É•ÑÕÉ¸}Í•±•Ñ}‰Õ¹‘±•}‘ÕÉ…‰±”¡É½½Ð°É•±•…Í”°™…±±‰…¬õ™…±±‰…¬°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€™…±±‰…­}É••¥ÁÐõ™…±±‰…­}É••¥ÁÐ°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€‰…­ÕÁ}É••¥ÁÑ}Í¡„ÈÔØõ‰…­ÕÁ}É••¥ÁÑ}Í¡„ÈÔØ°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€ÉÕ¹}Í•ÉÙ¥•ÌõÉÕ¹}Í•ÉÙ¥•Ì°Ù•É¥™äõÙ•É¥™ä¤(()‘•˜É•½Ù•É}¥¹Ñ•ÉÉÕÁÑ•¡É½½Ð°€¨°ÉÕ¹}Í•ÉÙ¥•Ì°Ù•É¥™ä¤è(€€€€ˆˆ‰I•½Ù•È…¸¥¹½µÁ±•Ñ”<½½ÑÉ…¹Í…Ñ¥½¸™É½´¥ÑÌÑÉ…¹Í…Ñ¥½¸µ‰½Õ¹©½ÕÉ¹…°¸ˆˆˆ(€€€ÉÕ¹Ñ¥µ”€ôA…Ñ ¡É½½Ð¤¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤(€€€Í•±•Ñ½È€ôÉÕ¹Ñ¥µ”€¼€‰Ý½É¬ˆ€¼€‰…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹Ðˆ(€€€©½ÕÉ¹…°€ôÍ•±•Ñ½È¹Á…É•¹Ð€¼)=UI91}95(€€€Ý¥Ñ }ÑÉ…¹Í…Ñ¥½¹}±½¬¡ÉÕ¹Ñ¥µ”¤è(€€€€€€€•Ù•¹ÑÌ€ô}É•…‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹ÑÌ¡©½ÕÉ¹…°°ÉÕ¹Ñ¥µ”¤(€€€€€€€±…Ñ•ÍÑ}¥€ô•Ù•¹ÑÍl´Åul‰ÑÉ…¹Í…Ñ¥½¹}¥‰t(€€€€€€€ÑÉ…¹Í…Ñ¥½¸€ômÉ½Ü™½ÈÉ½Ü¥¸•Ù•¹ÑÌ¥˜É½Ýl‰ÑÉ…¹Í…Ñ¥½¹}¥‰t€ôô±…Ñ•ÍÑ}¥‘t(€€€€€€€¥˜ÑÉ…¹Í…Ñ¥½¹l´Åul‰Á¡…Í”‰t¥¸QI5%91}A!MLè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰¹¼¥¹Ñ•ÉÉÕÁÑ•É•±•…Í”ÑÉ…¹Í…Ñ¥½¸É•ÅÕ¥É•ÌÉ•½Ù•Éäˆ¤(€€€€€€€±…Ñ•ÍÐ€ôÑÉ…¹Í…Ñ¥½¹l´Åt(€€€€€€€Ý½É­}ÍÑ…Ð€ôÍ•±•Ñ½È¹Á…É•¹Ð¹±ÍÑ…Ð ¤(€€€€€€€¥˜€¡¹½ÐÍÑ…Ð¹M}%M%H¡Ý½É­}ÍÑ…Ð¹ÍÑ}µ½‘”¤½ÈÍÑ…Ð¹M}%M19,¡Ý½É­}ÍÑ…Ð¹ÍÑ}µ½‘”¤(€€€€€€€€€€€€€€€½È€¡Ý½É­}ÍÑ…Ð¹ÍÑ}‘•Ø°Ý½É­}ÍÑ…Ð¹ÍÑ}¥¹¼¤€„ô€¡±…Ñ•ÍÑl‰Ý½É­}‘•Ø‰t°±…Ñ•ÍÑl‰Ý½É­}¥¹¼‰t¤¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰É•±•…Í”Ý½É¬‘¥É•Ñ½Éä¡…¹•Í¥¹”ÑÉ…¹Í…Ñ¥½¸Ý…ÌÉ•½É‘•ˆ¤(€€€€€€€Ý½É­}¥‘•¹Ñ¥Ñä€ô€¡Ý½É­}ÍÑ…Ð¹ÍÑ}‘•Ø°Ý½É­}ÍÑ…Ð¹ÍÑ}¥¹¼¤((€€€€€€€‘•˜…ÍÍ•ÉÑ}Ý½É¬ ¤è(€€€€€€€€€€€ÕÉÉ•¹Ñ}Ý½É¬€ôÍ•±•Ñ½È¹Á…É•¹Ð¹±ÍÑ…Ð ¤(€€€€€€€€€€€¥˜€¡¹½ÐÍÑ…Ð¹M}%M%H¡ÕÉÉ•¹Ñ}Ý½É¬¹ÍÑ}µ½‘”¤½ÈÍÑ…Ð¹M}%M19,¡ÕÉÉ•¹Ñ}Ý½É¬¹ÍÑ}µ½‘”¤(€€€€€€€€€€€€€€€€€€€½È€¡ÕÉÉ•¹Ñ}Ý½É¬¹ÍÑ}‘•Ø°ÕÉÉ•¹Ñ}Ý½É¬¹ÍÑ}¥¹¼¤€„ôÝ½É­}¥‘•¹Ñ¥Ñä¤è(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰É•±•…Í”Ý½É¬‘¥É•Ñ½Éä¡…¹•‘ÕÉ¥¹œÉ•½Ù•Éäˆ¤((€€€€€€€Á½¥¹Ñ•É}ÍÑ…Ð€ôÍ•±•Ñ½È¹±ÍÑ…Ð ¤(€€€€€€€¥˜¹½ÐÍÑ…Ð¹M}%M19,¡Á½¥¹Ñ•É}ÍÑ…Ð¹ÍÑ}µ½‘”¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹Ð¡…¹•Ñ¼„¹½¸µÍåµ±¥¹¬‘ÕÉ¥¹œÉ•½Ù•Éäˆ¤(€€€€€€€Á…Ñ¡Ì€ôí­•äèA…Ñ ¡±…Ñ•ÍÑm­•åt¤¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤™½È­•ä¥¸€ ‰ÁÉ•Ù¥½ÕÌˆ°€‰…¹‘¥‘…Ñ”ˆ°€‰™…±±‰…¬ˆ¥ô(€€€€€€€ÕÉÉ•¹Ð€ôÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤(€€€€€€€•áÁ½ÍÕÉ”€ô…¹ä¡É½Ýl‰Á¡…Í”‰t€ôô€‰…¹‘¥‘…Ñ•}•áÁ½ÍÕÉ•}Á½ÍÍ¥‰±”ˆ™½ÈÉ½Ü¥¸ÑÉ…¹Í…Ñ¥½¸¤(€€€€€€€…±±½Ý•‘}ÕÉÉ•¹Ð€ô€¡Á…Ñ¡Íl‰…¹‘¥‘…Ñ”‰t°Á…Ñ¡Íl‰™…±±‰…¬‰t¤¥˜•áÁ½ÍÕÉ”•±Í”€¡Á…Ñ¡Íl‰ÁÉ•Ù¥½ÕÌ‰t°Á…Ñ¡Íl‰…¹‘¥‘…Ñ”‰t¤(€€€€€€€¥˜ÕÉÉ•¹Ð¹½Ð¥¸…±±½Ý•‘}ÕÉÉ•¹Ðè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰™½É•¥¸Í•±•Ñ½ÈÁÉ•Í•ÉÙ•…ÐíÕÉÉ•¹ÑôìÉ•½Ù•ÉäÉ•ÅÕ¥É•Ì½½É‘¥¹…Ñ½ÈÉ•Ù¥•Üˆ¤(€€€€€€€µ…¹¥™•ÍÑÌ€ôí­•äèÙ…±¥‘…Ñ•}‰Õ¹‘±”¡Á…Ñ ¤™½È­•ä°Á…Ñ ¥¸Á…Ñ¡Ì¹¥Ñ•µÌ ¥ô(€€€€€€€¥˜…¹ä¡µ…¹¥™•ÍÐ¹•Ð ‰™½Éµ…Ðˆ¤€„ô€È™½Èµ…¹¥™•ÍÐ¥¸µ…¹¥™•ÍÑÌ¹Ù…±Õ•Ì ¤¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰¥¹Ñ•ÉÉÕÁÑ•<½½‰Õ¹‘±•Ì…É”¹½Ð±…Õ¹¡•Èµ…Á…‰±”ˆ¤(€€€€€€€‘¥•ÍÑÌ€ôí­•äè}µ…¹¥™•ÍÑ}‘¥•ÍÐ¡Á…Ñ ¤™½È­•ä°Á…Ñ ¥¸Á…Ñ¡Ì¹¥Ñ•µÌ ¥ô(€€€€€€€¥˜…¹ä¡‘¥•ÍÑÍm­•åt€„ô±…Ñ•ÍÑm˜‰í­•åõ}µ…¹¥™•ÍÑ}Í¡„ÈÔØ‰t(€€€€€€€€€€€€€€™½È­•ä¥¸€ ‰ÁÉ•Ù¥½ÕÌˆ°€‰…¹‘¥‘…Ñ”ˆ°€‰™…±±‰…¬ˆ¤¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰¥¹Ñ•ÉÉÕÁÑ•<½½‰Õ¹‘±”µ…¹¥™•ÍÐ¡…¹•ˆ¤((€€€€€€€‘•˜…ÍÍ•ÉÑ}‰Õ¹‘±•}Õ¹¡…¹•¡¹…µ”¤è(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€ÕÉÉ•¹Ñ}µ…¹¥™•ÍÐ€ôÙ…±¥‘…Ñ•}‰Õ¹‘±”¡Á…Ñ¡Ím¹…µ•t¤(€€€€€€€€€€€€€€€ÕÉÉ•¹Ñ}‘¥•ÍÐ€ô}µ…¹¥™•ÍÑ}‘¥•ÍÐ¡Á…Ñ¡Ím¹…µ•t¤(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰í¹…µ•ô‰Õ¹‘±”¡…¹•‘ÕÉ¥¹œÉ•½Ù•Éäèí•áôˆ¤™É½´•áŒ(€€€€€€€€€€€¥˜ÕÉÉ•¹Ñ}µ…¹¥™•ÍÐ€„ôµ…¹¥™•ÍÑÍm¹…µ•t½ÈÕÉÉ•¹Ñ}‘¥•ÍÐ€„ô‘¥•ÍÑÍm¹…µ•tè(€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰í¹…µ•ô‰Õ¹‘±”¡…¹•‘ÕÉ¥¹œÉ•½Ù•Éäˆ¤((€€€€€€€ÁÉ½½˜€ô±…Ñ•ÍÑl‰™…±±‰…­}É••¥ÁÐ‰t(€€€€€€€ÁÉ½½™}¡…Í €ô¡…Í¡±¥ˆ¹Í¡„ÈÔØ¡©Í½¸¹‘ÕµÁÌ¡ÁÉ½½˜°Í½ÉÑ}­•åÌõQÉÕ”°Í•Á…É…Ñ½ÉÌô ˆ°ˆ°€ˆèˆ¤¤¹•¹½‘” ¤¤¹¡•á‘¥•ÍÐ ¤(€€€€€€€¥˜ÁÉ½½™}¡…Í €„ô±…Ñ•ÍÑl‰™…±±‰…­}É••¥ÁÑ}Í¡„ÈÔØ‰tè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰¥¹Ñ•ÉÉÕÁÑ•™…±±‰…¬ÁÉ½½˜¡…¹•ˆ¤(€€€€€€€}Ù…±¥‘…Ñ•}™…±±‰…­}É••¥ÁÐ¡ÁÉ½½˜°Á…Ñ¡Íl‰ÁÉ•Ù¥½ÕÌ‰t°Á…Ñ¡Íl‰…¹‘¥‘…Ñ”‰t°Á…Ñ¡Íl‰™…±±‰…¬‰t¤(€€€€€€€¥˜•áÁ½ÍÕÉ”è(€€€€€€€€€€€Ñ…É•Ð°Í•±•Ñ•‘}Á¡…Í”°ÍÑ…ÉÑ•‘}Á¡…Í”°Ù•É¥™¥•‘}Á¡…Í”°É•ÍÕ±Ð€ô€ (€€€€€€€€€€€€€€€Á…Ñ¡Íl‰™…±±‰…¬‰t°€‰™…±±‰…­}Í•±•Ñ•ˆ°€‰™…±±‰…­}ÍÑ…ÉÑ•ˆ°€‰™…±±‰…­}Ù•É¥™¥•ˆ°€‰™…±±‰…­}Ù•É¥™¥•ˆ¤(€€€€€€€•±Í”è(€€€€€€€€€€€Ñ…É•Ð°Í•±•Ñ•‘}Á¡…Í”°ÍÑ…ÉÑ•‘}Á¡…Í”°Ù•É¥™¥•‘}Á¡…Í”°É•ÍÕ±Ð€ô€ (€€€€€€€€€€€€€€€Á…Ñ¡Íl‰ÁÉ•Ù¥½ÕÌ‰t°€‰ÁÉ•Ù¥½ÕÍ}Í•±•Ñ•ˆ°€‰ÁÉ•Ù¥½ÕÍ}ÍÑ…ÉÑ•ˆ°€‰ÁÉ•Ù¥½ÕÍ}Ù•É¥™¥•ˆ°€‰ÁÉ•Ù¥½ÕÍ}Ù•É¥™¥•ˆ¤(€€€€€€€‰•™½É•}ÍÑ½À€ôÕÉÉ•¹Ð(€€€€€€€É•½Ù•Éå}•¹Ù•±½Á”€ôí¬è±…Ñ•ÍÑm­t™½È¬¥¸±…Ñ•ÍÐ¥˜¬¹½Ð¥¸€ ‰Á¡…Í”ˆ°€‰É•½É‘•‘}…Ðˆ¥ô(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°É•½Ù•Éå}•¹Ù•±½Á”°€‰É•½Ù•Éå}…ÑÑ•µÁÑ•ˆ¤(€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡l‰ÍÑ½Àˆ°€‰¡½µ•‰½àµÝ½É­Í¡½Àµ…Ñ•Ý…äˆ°€‰¡½µ•‰½àµ½µÁ…¹¥½¸ˆ°€‰¡½µ•‰½àµ¹…Ñ¥Ù”‰t¤(€€€€€€€…ÍÍ•ÉÑ}Ý½É¬ ¤(€€€€€€€™½È¹…µ”¥¸Á…Ñ¡Ìè(€€€€€€€€€€€…ÍÍ•ÉÑ}‰Õ¹‘±•}Õ¹¡…¹•¡¹…µ”¤(€€€€€€€ÕÉÉ•¹Ð€ôÍ•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤(€€€€€€€¥˜ÕÉÉ•¹Ð€„ô‰•™½É•}ÍÑ½Àè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È¡˜‰Í•±•Ñ½È¡…¹•‘ÕÉ¥¹œÉ•½Ù•ÉäÍÑ½Àì™½É•¥¸Í•±•Ñ½ÈÁÉ•Í•ÉÙ•…ÐíÕÉÉ•¹Ñôˆ¤(€€€€€€€¥˜ÕÉÉ•¹Ð€„ôÑ…É•Ðè(€€€€€€€€€€€Ñ•µÁ½É…Éä€ôÍ•±•Ñ½È¹Ý¥Ñ¡}¹…µ”¡˜ˆ¹…ÁÁ±¥…Ñ¥½¸µÕÉÉ•¹Ð¹íÕÕ¥¹ÕÕ¥Ð ¤¹¡•áô¹¹•áÐˆ¤(€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€½Ì¹Íåµ±¥¹¬¡½Ì¹Á…Ñ ¹É•±Á…Ñ ¡Ñ…É•Ð°Í•±•Ñ½È¹Á…É•¹Ð¤°Ñ•µÁ½É…Éä°Ñ…É•Ñ}¥Í}‘¥É•Ñ½ÉäõQÉÕ”¤(€€€€€€€€€€€€€€€…ÍÍ•ÉÑ}Ý½É¬ ¤(€€€€€€€€€€€€€€€¥˜Í•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤€„ô‰•™½É•}ÍÑ½Àè(€€€€€€€€€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰Í•±•Ñ½È‘É¥™Ð‘•Ñ•Ñ•‰•™½É”É•½Ù•ÉäÉ•Á±…”ˆ¤(€€€€€€€€€€€€€€€½Ì¹É•Á±…”¡Ñ•µÁ½É…Éä°Í•±•Ñ½È¤(€€€€€€€€€€€€€€€}‘¥É•Ñ½Éå}™Íå¹Œ¡Í•±•Ñ½È¹Á…É•¹Ð¤(€€€€€€€€€€€™¥¹…±±äè(€€€€€€€€€€€€€€€Ý¥Ñ ½¹Ñ•áÑ±¥ˆ¹ÍÕÁÁÉ•ÍÌ¡¥±•9½Ñ½Õ¹‘ÉÉ½È¤è(€€€€€€€€€€€€€€€€€€€Ñ•µÁ½É…Éä¹Õ¹±¥¹¬ ¤(€€€€€€€¥˜Í•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤€„ôÑ…É•Ðè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰É•½Ù•ÉäÍ•±•Ñ½È‘¥¹½ÐÉ•Í½±Ù”Ñ¼Ñ¡”Í•±•Ñ•‰Õ¹‘±”ˆ¤(€€€€€€€…ÍÍ•ÉÑ}‰Õ¹‘±•}Õ¹¡…¹• ‰™…±±‰…¬ˆ¥˜•áÁ½ÍÕÉ”•±Í”€‰ÁÉ•Ù¥½ÕÌˆ¤(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°É•½Ù•Éå}•¹Ù•±½Á”°Í•±•Ñ•‘}Á¡…Í”¤(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°É•½Ù•Éå}•¹Ù•±½Á”°ÍÑ…ÉÑ•‘}Á¡…Í”¤(€€€€€€€ÉÕ¹}Í•ÉÙ¥•Ì¡l‰ÍÑ…ÉÐˆ°€‰¡½µ•‰½àµ¹…Ñ¥Ù”ˆ°€‰¡½µ•‰½àµ½µÁ…¹¥½¸ˆ°€‰¡½µ•‰½àµÝ½É­Í¡½Àµ…Ñ•Ý…ä‰t¤(€€€€€€€…ÍÍ•ÉÑ}Ý½É¬ ¤(€€€€€€€¥˜Í•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤€„ôÑ…É•Ðè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰Í•±•Ñ½È¡…¹•Ý¡¥±”É•½Ù•ÉäÍ•ÉÙ¥•ÌÍÑ…ÉÑ•ˆ¤(€€€€€€€…ÍÍ•ÉÑ}‰Õ¹‘±•}Õ¹¡…¹• ‰™…±±‰…¬ˆ¥˜•áÁ½ÍÕÉ”•±Í”€‰ÁÉ•Ù¥½ÕÌˆ¤(€€€€€€€Ù•É¥™ä¡Ñ…É•Ð¤(€€€€€€€…ÍÍ•ÉÑ}Ý½É¬ ¤(€€€€€€€¥˜Í•±•Ñ½È¹É•Í½±Ù”¡ÍÑÉ¥ÐõQÉÕ”¤€„ôÑ…É•Ðè(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰Í•±•Ñ½È¡…¹•‘ÕÉ¥¹œÉ•½Ù•ÉäÙ•É¥™¥…Ñ¥½¸ˆ¤(€€€€€€€¥˜…¹ä¡}µ…¹¥™•ÍÑ}‘¥•ÍÐ¡Á…Ñ¡Ím¹…µ•t¤€„ô‘¥•ÍÑÍm¹…µ•t™½È¹…µ”¥¸Á…Ñ¡Ì¤è(€€€€€€€€€€€É…¥Í”	Õ¹‘±•ÉÉ½È ‰Í•±•Ñ•‰Õ¹‘±”¡…¹•‘ÕÉ¥¹œÉ•½Ù•ÉäÙ•É¥™¥…Ñ¥½¸ˆ¤(€€€€€€€…ÍÍ•ÉÑ}‰Õ¹‘±•}Õ¹¡…¹• ‰™…±±‰…¬ˆ¥˜•áÁ½ÍÕÉ”•±Í”€‰ÁÉ•Ù¥½ÕÌˆ¤(€€€€€€€}…ÁÁ•¹‘}ÑÉ…¹Í…Ñ¥½¹}•Ù•¹Ð¡©½ÕÉ¹…°°É•½Ù•Éå}•¹Ù•±½Á”°Ù•É¥™¥•‘}Á¡…Í”¤(€€€€€€€É•ÑÕÉ¸É•ÍÕ±Ð(