#!/usr/bin/env python3
"""Build independently fingerprinted C-Crate components into a verified cache."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


INPUTS = {
    "backend": (
        "deploy/build-homebox-backend.py", "homebox-backend", "upstream/homebox/backend",
        "upstream/homebox/PIN",
    ),
    "frontend": (
        "deploy/build-homebox-ui.py", "homebox-ui/overlay", "homebox-ui/pnpm-lock.yaml", "homebox-ui/upstream-typecheck.json",
        "upstream/homebox/frontend", "kiosk/branding", "kiosk/member-avatar.js", "kiosk/label-editor.js",
    ),
    "labels": (
        "deploy/build-label-ui.py", "label-ui/vendor", "label-ui/src", "label-ui/public",
        "label-ui/patches", "label-ui/pnpm-lock.yaml", "label-ui/vendor-manifest.json",
        "label-ui/package.json", "label-ui/vite.config.ts", "label-ui/editor.html", "label-ui/render.html",
    ),
}
TOOL_KEYS = {"backend": ("go", "target"), "frontend": ("node", "pnpm"), "labels": ("node", "pnpm")}


def _component_files(component, source_root):
    root = pathlib.Path(source_root).resolve()
    files = []
    for item in INPUTS[component]:
        path = root / item
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file() and ".git" not in p.parts)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _upstream_revision(root):
    pin = root / "upstream/homebox/PIN"
    if pin.is_file():
        return pin.read_text().strip()
    checkout = root / "upstream/homebox"
    if not (checkout / ".git").exists():
        raise RuntimeError("Pinned Homebox submodule is missing or uninitialized")
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    expected = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD:upstream/homebox"], text=True).strip()
    if revision != expected:
        raise RuntimeError("Homebox submodule does not match the publication pin")
    if subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("Homebox submodule has uncommitted source changes")
    return revision


def component_fingerprint(component: str, source_root: pathlib.Path, tools: dict) -> str:
    if component not in INPUTS:
        raise ValueError(f"Unknown component: {component}")
    root = pathlib.Path(source_root).resolve()
    digest = hashlib.sha256()
    for path in _component_files(component, root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if component in ("backend", "frontend"):
        digest.update(b"upstream/homebox/.revision\0")
        digest.update(_upstream_revision(root).encode())
        digest.update(b"\0")
    selected_tools = {key: tools[key] for key in TOOL_KEYS[component] if key in tools}
    digest.update(json.dumps(selected_tools, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def _capture_tools(component, toolchain_root):
    root = pathlib.Path(toolchain_root)
    tools = {}
    if component == "backend":
        path_file = root / "go-path.txt"
        go = pathlib.Path(path_file.read_text().strip()) / "bin/go" if path_file.is_file() else pathlib.Path("go")
        try:
            tools["go"] = subprocess.check_output([str(go), "version"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            tools["go"] = "unavailable"
        tools["target"] = "linux/arm64"
    else:
        node_path = root / "node-path.txt"
        node = pathlib.Path(node_path.read_text().strip()) / "bin/node" if node_path.is_file() else pathlib.Path("node")
        pnpm = root / "pnpm/node_modules/.bin/pnpm"
        for key, command in (("node", [str(node), "--version"]), ("pnpm", [str(pnpm), "--version"])):
            try:
                tools[key] = subprocess.check_output(command, text=True).strip()
            except (OSError, subprocess.CalledProcessError):
                tools[key] = "unavailable"
    return tools


def _outputs(path):
    result = {}
    for file in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.relative_to(path).as_posix()):
        relative = file.relative_to(path).as_posix()
        result[relative] = {
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "size": file.stat().st_size,
            "mode": stat.S_IMODE(file.stat().st_mode),
        }
    return result


def _cache_valid(output_path, metadata_path, fingerprint):
    try:
        metadata = json.loads(metadata_path.read_text())
        return metadata["fingerprint"] == fingerprint and metadata["outputs"] == _outputs(output_path)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _invoke_builder(component, *, source_root, toolchain_root, output_path):
    root = pathlib.Path(source_root).resolve()
    output_path = pathlib.Path(output_path)
    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if component == "backend":
        command = [sys.executable, str(root / "deploy/build-homebox-backend.py"), "--source-root", str(root),
                   "--toolchain-root", str(toolchain_root), "--output", str(output_path), "--external-frontend"]
        env.update(CCRATE_GOOS="linux", CCRATE_GOARCH="arm64")
        subprocess.run(command, cwd=root, env=env, check=True)
    elif component == "frontend":
        command = [sys.executable, str(root / "deploy/build-homebox-ui.py"), "--toolchain-root", str(toolchain_root), "--upstream-root", str(root)]
        subprocess.run(command, cwd=root, env=env, check=True)
        shutil.copytree(work / "homebox-ui-build/.output/public", output_path, dirs_exist_ok=True)
    else:
        staging = pathlib.Path(tempfile.mkdtemp(prefix="component-label-stage-", dir=work))
        command = [sys.executable, str(root / "deploy/build-label-ui.py"), "--source-root", str(root),
                   "--output", str(staging), "--toolchain-root", str(toolchain_root)]
        subprocess.run(command, cwd=root, env=env, check=True)
        shutil.copytree(staging, output_path, dirs_exist_ok=True)
        shutil.rmtree(staging)
    if component == "backend":
        raw = (output_path / "homebox").read_bytes()
        if len(raw) < 20 or raw[:6] != b"\x7fELF\x02\x01" or int.from_bytes(raw[18:20], "little") != 183:
            raise RuntimeError("Backend builder did not produce a Linux ARM64 ELF artifact")
    return {"component": component, "command": command, "target": "linux/arm64" if component == "backend" else "static"}


def _verified_source(root):
    git = root / ".git"
    if not git.exists():
        return True
    try:
        status = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True)
        if status.strip():
            return False
        submodules = subprocess.check_output(["git", "-C", str(root), "submodule", "status", "--recursive"], text=True)
        for line in submodules.splitlines():
            fields = line.split()
            if not fields or line[0] != " ":
                return False
            child = root / fields[1]
            child_status = subprocess.check_output(["git", "-C", str(child), "status", "--porcelain", "--untracked-files=all"], text=True)
            if child_status.strip():
                return False
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def build_component(component: str, *, source_root: pathlib.Path, toolchain_root: pathlib.Path, cache_root: pathlib.Path, tools=None) -> dict:
    root = pathlib.Path(source_root).resolve()
    cache = pathlib.Path(cache_root).resolve() / component
    tools = dict(_capture_tools(component, toolchain_root) if tools is None else tools)
    fingerprint = component_fingerprint(component, root, tools)
    output_path = cache / fingerprint / "output"
    metadata_path = cache / fingerprint / "build.json"
    can_cache = _verified_source(root)
    if can_cache and _cache_valid(output_path, metadata_path, fingerprint):
        metadata = json.loads(metadata_path.read_text())
        return {"fingerprint": fingerprint, "output_path": str(output_path), "outputs": metadata["outputs"],
                "build_receipt": metadata["build_receipt"], "tools": metadata["tools"], "cache_hit": True}
    if output_path.parent.exists():
        shutil.rmtree(output_path.parent)
    output_path.mkdir(parents=True)
    receipt = _invoke_builder(component, source_root=root, toolchain_root=pathlib.Path(toolchain_root), output_path=output_path)
    outputs = _outputs(output_path)
    if not outputs:
        raise RuntimeError(f"{component} builder produced no output files")
    metadata = {"component": component, "fingerprint": fingerprint, "tools": tools, "outputs": outputs, "build_receipt": receipt}
    if can_cache:
        metadata_path.write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    return {"fingerprint": fingerprint, "output_path": str(output_path), "outputs": outputs,
            "build_receipt": receipt, "tools": tools, "cache_hit": False}


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_revision(root):
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Source commit must be a full 40-character Git SHA")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True).strip():
        raise RuntimeError("Release publication requires a clean source checkout")
    pin = (root / "upstream/homebox/PIN").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise RuntimeError("Pinned Homebox revision must be a full 40-character Git SHA")
    checkout = root / "upstream/homebox"
    actual_pin = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    gitlink = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD:upstream/homebox"], text=True).strip()
    if actual_pin != pin or gitlink != pin:
        raise RuntimeError("Initialized Homebox submodule, repository gitlink, and PIN file disagree")
    if subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"], text=True).strip():
        raise RuntimeError("Release publication requires a clean pinned Homebox checkout")
    return commit, pin


def _manifest_files(root):
    root = pathlib.Path(root)
    return {
        path.relative_to(root).as_posix(): {
            "sha256": _file_hash(path), "size": path.stat().st_size,
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        if path.is_file() and not path.is_symlink()
    }


def _verify_component_results(component_results):
    if set(component_results) != {"backend", "frontend", "labels"}:
        raise RuntimeError("All three component builds are required for publication")
    for name, result in component_results.items():
        output = pathlib.Path(result["output_path"]).resolve()
        if not output.is_dir() or result.get("outputs") != _outputs(output):
            raise RuntimeError(f"{name} component output changed after build or cache verification")
        if not re.fullmatch(r"[0-9a-f]{64}", result.get("fingerprint", "")):
            raise RuntimeError(f"{name} component fingerprint is missing")
        if not isinstance(result.get("build_receipt"), dict):
            raise RuntimeError(f"{name} component build receipt is missing")
    backend = pathlib.Path(component_results["backend"]["output_path"]) / "homebox"
    raw = backend.read_bytes()
    if len(raw) < 20 or raw[:6] != b"\x7fELF\x02\x01" or int.from_bytes(raw[18:20], "little") != 183:
        raise RuntimeError("Backend output is not a Linux ARM64 ELF executable")


def verification_commands(python_executable):
    """Checks required to produce a review-only candidate artifact receipt."""
    return [[python_executable, "-m", "unittest", "tests.test_build_release",
             "tests.test_update_ccrate",
             "tests.test_release_bundle.ReleaseBundleTests.test_format2_backup_restores_selected_release",
             "tests.test_release_bundle.ReleaseBundleTests.test_production_backup_restores_sealed_selection_and_receipt_binding",
             "-v"]]


def capture_verification(source_root: pathlib.Path, artifacts: dict) -> dict:
    """Run isolated repository checks and capture the exact tested source/artifact closure."""
    root = pathlib.Path(source_root).resolve()
    _verify_component_results(artifacts["components"])
    public, labels, binary = (pathlib.Path(artifacts[key]).resolve() for key in ("public", "labels", "binary"))
    for path in (public, labels):
        if not path.is_dir() or not _manifest_files(path):
            raise RuntimeError(f"Required static artifact tree is missing or empty: {path}")
    if not binary.is_file() or _file_hash(binary) != _file_hash(
            pathlib.Path(artifacts["components"]["backend"]["output_path"]) / "homebox"):
        raise RuntimeError("Assembled native binary does not match the verified backend build")

    # Candidate receipts cover component packaging, bundle validation, and updater preflight.
    # Activation and migration suites remain a separate release gate; their failure is not hidden.
    commands = verification_commands(sys.executable)
    logs, test_count, exit_code = [], 0, 0
    for command in commands:
        completed = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, check=False)
        output = completed.stdout or ""
        logs.append({"command": command, "exit_code": completed.returncode, "output": output})
        if completed.returncode:
            exit_code = completed.returncode
        for match in re.finditer(r"Ran\s+(\d+)\s+tests?", output):
            test_count += int(match.group(1))
    if not test_count:
        exit_code = exit_code or 1

    # Bind all runtime source entries and static/native bytes to one closure digest.
    sys.path.insert(0, str(root / "deploy"))
    try:
        import release_bundle
        runtime = release_bundle._runtime_files(root, release_bundle.LAUNCHER_DEPLOY_FILES)
    finally:
        sys.path.pop(0)
        sys.modules.pop("release_bundle", None)
    source_entries = {destination.as_posix(): _file_hash(path) for path, destination in runtime}
    source_modes = {destination.as_posix(): stat.S_IMODE(path.stat().st_mode) for path, destination in runtime}
    public_files, label_files = _manifest_files(public), _manifest_files(labels)
    native_sha = _file_hash(binary)
    closure = _json_hash({"runtime_files": source_entries, "runtime_modes": source_modes,
                          "public_files": {key: {"sha256": value["sha256"], "size": value["size"]}
                                           for key, value in public_files.items()},
                          "label_files": {key: {"sha256": value["sha256"], "size": value["size"]}
                                          for key, value in label_files.items()},
                          "label_source_sha256": _file_hash(root / "label-ui/src/starter-documents.json"),
                          "native_sha256": native_sha})
    return {
        "source_manifest_digest": _json_hash({"files": source_entries, "modes": source_modes}),
        "source_entries": source_entries, "source_modes": source_modes,
        "public_files": {key: {"sha256": value["sha256"], "size": value["size"]}
                         for key, value in public_files.items()},
        "label_files": {key: {"sha256": value["sha256"], "size": value["size"]}
                        for key, value in label_files.items()},
        "native_sha256": native_sha, "closure_sha256": closure,
        "release_metadata": artifacts.get("release_metadata"),
        "verification": {"exit_code": exit_code, "tests": test_count, "commands": logs},
    }


def _write_json(path, value):
    data = json.dumps(value, sort_keys=True, indent=2) + "\n"
    pathlib.Path(path).write_text(data, encoding="utf-8")
    return data


def package_release(source_root: pathlib.Path, component_results: dict, verification: dict,
                    destination: pathlib.Path) -> dict:
    """Seal a format-2 runtime, then package exactly one candidate/ tree and its descriptor."""
    root, destination = pathlib.Path(source_root).resolve(), pathlib.Path(destination).resolve()
    _verify_component_results(component_results)
    if (not isinstance(verification, dict) or verification.get("verification", {}).get("exit_code") != 0
            or not isinstance(verification.get("verification", {}).get("tests"), int)
            or verification["verification"]["tests"] < 1):
        raise RuntimeError("A successful nonempty captured verification is required to publish")
    sys.path.insert(0, str(root / "deploy"))
    try:
        import release_bundle as bundle_contract
        current_runtime = bundle_contract._runtime_files(root, bundle_contract.LAUNCHER_DEPLOY_FILES)
    finally:
        sys.path.pop(0)
        sys.modules.pop("release_bundle", None)
    current_entries = {destination.as_posix(): _file_hash(path) for path, destination in current_runtime}
    current_modes = {destination.as_posix(): stat.S_IMODE(path.stat().st_mode)
                     for path, destination in current_runtime}
    if (verification.get("source_entries") != current_entries
            or verification.get("source_modes") != current_modes
            or verification.get("source_manifest_digest") != _json_hash({"files": current_entries,
                                                                            "modes": current_modes})):
        raise RuntimeError("Captured verification does not bind the current runtime source and modes")
    commit, upstream_pin = _source_revision(root)
    if destination.exists():
        raise RuntimeError(f"Release output already exists: {destination}")
    destination.mkdir(parents=True)
    work = destination.parent / (destination.name + ".assembly")
    if work.exists():
        raise RuntimeError(f"Release assembly path already exists: {work}")
    work.mkdir(parents=True)
    try:
        public = work / "public"
        shutil.copytree(pathlib.Path(component_results["frontend"]["output_path"]), public)
        labels = pathlib.Path(component_results["labels"]["output_path"]).resolve()
        binary = pathlib.Path(component_results["backend"]["output_path"]) / "homebox"
        metadata = verification.get("release_metadata") if isinstance(verification, dict) else None
        if not isinstance(metadata, dict):
            metadata = {"format": 1, "application": "ccrate", "commit": commit,
                        "upstream_pin": upstream_pin,
                        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")}
        if (metadata.get("commit") != commit or metadata.get("upstream_pin") != upstream_pin
                or metadata.get("format") != 1 or metadata.get("application") != "ccrate"):
            raise RuntimeError("Captured UI release metadata does not match this source revision")
        _write_json(public / "ccrate-release.json", metadata)
        artifacts = {"components": component_results, "public": public, "labels": labels, "binary": binary,
                     "release_metadata": metadata}
        # The metadata is part of the delivered UI and therefore belongs to the tested closure.
        verification = capture_verification(root, artifacts)
        if verification["verification"]["exit_code"] != 0:
            raise RuntimeError("Release verification failed; candidate was not packaged")
        public_files = {name: {"sha256": row["sha256"], "size": row["size"]}
                        for name, row in _manifest_files(public).items()}
        label_files = {name: {"sha256": row["sha256"], "size": row["size"]}
                       for name, row in _manifest_files(labels).items()}
        source_manifest_digest = verification["source_manifest_digest"]
        static_digest = _json_hash({"public": public_files, "labels": label_files})
        build = {
            "source_manifest_digest": source_manifest_digest,
            "static_manifest_sha256": static_digest,
            "native_sha256": verification["native_sha256"], "target": "linux/arm64",
            "components": {name: {"fingerprint": result["fingerprint"], "tools": result.get("tools", {}),
                                   "outputs": result["outputs"], "cache_hit": result["cache_hit"],
                                   "build_receipt": {key: value for key, value in result["build_receipt"].items()
                                                     if key != "command"}}
                           for name, result in sorted(component_results.items())},
        }
        tests = {
            "source_manifest_digest": source_manifest_digest,
            "static_manifest_sha256": static_digest,
            "source_entries": {name: {"sha256": digest, "mode": verification["source_modes"][name]}
                               for name, digest in verification["source_entries"].items()},
            "verification": verification["verification"],
            "closure_sha256": verification["closure_sha256"],
            "execution_scope": "isolated-release-candidate",
            "workshop_compatibility": {
                "status": "not-established",
                "required_cases": ["workshop_read_v1", "workshop_read_v2", "workshop_write_v2"],
            },
        }
        build_raw = _write_json(destination / "build-receipt.json", build)
        tests_raw = _write_json(destination / "test-receipt.json", tests)
        provenance = {
            "source_manifest_digest": source_manifest_digest, "static_manifest_sha256": static_digest,
            "build_receipt": build, "build_receipt_sha256": hashlib.sha256(build_raw.encode()).hexdigest(),
            "build_receipt_raw": build_raw, "build_receipt_canonical_sha256": _json_hash(build),
            "build_receipt_path": "build-receipt.json", "test_receipt": tests,
            "test_receipt_sha256": hashlib.sha256(tests_raw.encode()).hexdigest(),
            "test_receipt_raw": tests_raw, "test_receipt_canonical_sha256": _json_hash(tests),
            "test_receipt_path": "test-receipt.json", "native_sha256": verification["native_sha256"],
            "runtime_files": verification["source_entries"], "runtime_modes": verification["source_modes"],
            "public_files": public_files, "label_files": label_files,
            "label_source_sha256": _file_hash(root / "label-ui/src/starter-documents.json"),
        }
        sys.path.insert(0, str(root / "deploy"))
        try:
            import release_bundle
            stage_source = work / "source"
            stage_source.mkdir()
            for directory in ("ops", "kiosk", "deploy"):
                shutil.copytree(root / directory, stage_source / directory)
            (stage_source / "label-ui/src").mkdir(parents=True)
            shutil.copy2(root / "label-ui/src/starter-documents.json",
                         stage_source / "label-ui/src/starter-documents.json")
            (stage_source / "work").mkdir()
            shutil.copytree(labels, stage_source / "work/label-ui-build")
            candidate = destination / "candidate"
            release_bundle.stage_bundle(candidate, binary=binary, public=public, source=stage_source,
                                        provenance=provenance)
            manifest = release_bundle.validate_bundle(candidate)
        finally:
            sys.modules.pop("release_bundle", None)
            sys.path.pop(0)
        manifest_path = candidate / "manifest.json"
        manifest_sha = _file_hash(manifest_path)
        archive = f"ccrate-linux-arm64-{commit[:12]}.tar.gz"
        archive_path = destination / archive
        with tarfile.open(archive_path, "w:gz", compresslevel=9) as stream:
            stream.add(candidate, arcname="candidate", recursive=True)
        compressed_bytes = archive_path.stat().st_size
        expanded_bytes = sum(path.stat().st_size for path in candidate.rglob("*") if path.is_file())
        descriptor = {"format": 1, "application": "ccrate", "architecture": "linux-arm64",
                      "commit": commit, "upstream_pin": upstream_pin, "archive": archive,
                      "compressed_bytes": compressed_bytes, "expanded_bytes": expanded_bytes,
                      "sha256": _file_hash(archive_path), "manifest_sha256": manifest_sha}
        _write_json(destination / "release.json", descriptor)
        checksums = (f"{descriptor['sha256']}  {archive}\n"
                     f"{_file_hash(destination / 'release.json')}  release.json\n"
                     f"{_file_hash(destination / 'build-receipt.json')}  build-receipt.json\n"
                     f"{_file_hash(destination / 'test-receipt.json')}  test-receipt.json\n")
        (destination / "SHA256SUMS").write_text(checksums, encoding="ascii")
        return descriptor
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument("--toolchain-root", type=pathlib.Path)
    parser.add_argument("--cache-root", type=pathlib.Path)
    parser.add_argument("--component", choices=(*INPUTS, "all"), default="all")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    toolchain = args.toolchain_root or root / "work/toolchains"
    cache = args.cache_root or root / "work/component-builds"
    components = INPUTS if args.component == "all" else (args.component,)
    result = {name: build_component(name, source_root=root, toolchain_root=toolchain, cache_root=cache) for name in components}
    if args.component != "all":
        print(json.dumps(result, indent=2))
        return
    if not args.output:
        parser.error("--output is required when building a release")
    commit, upstream_pin = _source_revision(root)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    metadata = {"format": 1, "application": "ccrate", "commit": commit,
                "upstream_pin": upstream_pin, "built_at": timestamp}
    public = pathlib.Path(tempfile.mkdtemp(prefix="ccrate-public-", dir=root / "work"))
    try:
        shutil.copytree(result["frontend"]["output_path"], public, dirs_exist_ok=True)
        _write_json(public / "ccrate-release.json", metadata)
        artifacts = {"components": result, "public": public,
                     "labels": pathlib.Path(result["labels"]["output_path"]),
                     "binary": pathlib.Path(result["backend"]["output_path"]) / "homebox",
                     "release_metadata": metadata}
        verification = capture_verification(root, artifacts)
        descriptor = package_release(root, result, verification, args.output)
    finally:
        shutil.rmtree(public, ignore_errors=True)
    print(json.dumps(descriptor, indent=2))


if __name__ == "__main__":
    main()
