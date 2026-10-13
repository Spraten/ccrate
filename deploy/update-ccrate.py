#!/usr/bin/env python3
"""Download and preflight a trusted prebuilt C-Crate release."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path, PurePosixPath

try:
    from release_bundle import BundleError, validate_bundle
except ImportError:  # Importing this module from an arbitrary working directory remains inert.
    BundleError = ValueError
    validate_bundle = None


OWNER = "Spraten"
REPOSITORY = "ccrate"
API = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_DESCRIPTOR_BYTES = 256 * 1024
FREE_SPACE_RESERVE = 100 * 1024 * 1024
UPSTREAM_PIN = "e01dd737238a3fa7e1a6454b37de6c6fc88c86e4"
DESCRIPTOR_KEYS = {"format", "application", "architecture", "commit", "upstream_pin", "archive",
                   "compressed_bytes", "expanded_bytes", "sha256", "manifest_sha256"}
TAG_RE = re.compile(r"^ccrate-([0-9a-f]{12})$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(RuntimeError):
    """Refusal that is safe to show to an operator."""


def _read_response(response, limit, expected=None):
    headers = getattr(response, "headers", {})
    raw_length = headers.get("Content-Length") if hasattr(headers, "get") else None
    if raw_length is not None:
        try:
            if int(raw_length) > limit or (expected is not None and int(raw_length) != expected):
                raise UpdateError("release response size does not match its trusted bound")
        except ValueError as exc:
            raise UpdateError("release response has invalid size metadata") from exc
    data = response.read(limit + 1)
    if len(data) > limit or (expected is not None and len(data) != expected):
        raise UpdateError("release response is truncated or exceeds its trusted bound")
    final_url = response.geturl() if hasattr(response, "geturl") else ""
    if final_url and not final_url.startswith("https://"):
        raise UpdateError("release response left HTTPS")
    return data


def _request(url, *, opener, accept="application/vnd.github+json", limit=MAX_DESCRIPTOR_BYTES,
             expected=None):
    if not isinstance(url, str) or not url.startswith("https://api.github.com/repos/Spraten/ccrate/"):
        raise UpdateError("release asset URL is outside the trusted repository API")
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "ccrate-prebuilt-updater/1"})
    try:
        with opener(request, timeout=30) as response:
            body = _read_response(response, limit, expected)
            final_url = response.geturl()
            if not _trusted_asset_response(final_url):
                raise UpdateError("release asset redirected outside GitHub's HTTPS asset service")
            return body, final_url
    except UpdateError:
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError("trusted release could not be downloaded") from exc


def _trusted_asset_response(url):
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = urlparse(url).hostname
    return host == "api.github.com" or host == "github.com" or (host or "").endswith(".githubusercontent.com")


def _json_response(url, *, opener):
    body, final_url = _request(url, opener=opener)
    if final_url != url:
        raise UpdateError("GitHub API redirected a release identity request")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise UpdateError("GitHub returned invalid release metadata") from exc
    if not isinstance(result, dict):
        raise UpdateError("GitHub release metadata has an invalid shape")
    return result


def _decode_release(tag, response):
    final_url = response.geturl() if hasattr(response, "geturl") else ""
    expected = f"{API}/releases/tags/{tag}"
    if final_url != expected:
        raise UpdateError("release metadata came from another repository")
    try:
        value = json.loads(response.read(MAX_DESCRIPTOR_BYTES + 1).decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise UpdateError("GitHub returned invalid release metadata") from exc
    if not isinstance(value, dict) or value.get("tag_name") != tag or not isinstance(value.get("assets"), list):
        raise UpdateError("release tag identity does not match the requested version")
    return value


def _tag_commit(tag, *, opener):
    ref = _json_response(f"{API}/git/ref/tags/{tag}", opener=opener)
    obj = ref.get("object")
    seen = set()
    while isinstance(obj, dict) and obj.get("type") == "tag":
        sha = obj.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or sha in seen:
            raise UpdateError("release tag has invalid annotated-tag identity")
        seen.add(sha)
        annotated = _json_response(f"{API}/git/tags/{sha}", opener=opener)
        obj = annotated.get("object")
    if not isinstance(obj, dict) or obj.get("type") != "commit":
        raise UpdateError("release tag does not resolve to a commit")
    commit = obj.get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError("release tag commit is invalid")
    return commit


def _asset(assets, name):
    matches = [item for item in assets if isinstance(item, dict) and item.get("name") == name]
    if len(matches) != 1:
        raise UpdateError("release is missing one uniquely named trusted asset")
    asset = matches[0]
    asset_id = asset.get("id")
    digest = asset.get("digest")
    if (not isinstance(asset_id, int) or asset_id <= 0 or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or not isinstance(asset.get("size"), int) or isinstance(asset.get("size"), bool)
            or asset["size"] <= 0 or asset["size"] > MAX_ARCHIVE_BYTES):
        raise UpdateError("release asset has no trusted SHA-256 identity")
    url = f"{API}/releases/assets/{asset_id}"
    return {"id": asset_id, "name": name, "size": asset.get("size"), "digest": digest,
            "url": url}


def _validate_descriptor(tag, descriptor, archive_asset):
    match = TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
    if not match or not isinstance(descriptor, dict) or set(descriptor) != DESCRIPTOR_KEYS:
        raise UpdateError("release version must be ccrate- followed by 12 lowercase commit characters")
    commit = descriptor.get("commit")
    expected_name = f"ccrate-linux-arm64-{match.group(1)}.tar.gz"
    if (descriptor.get("format") != 1 or descriptor.get("application") != "ccrate"
            or descriptor.get("architecture") != "linux-arm64"
            or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not commit.startswith(match.group(1))
            or descriptor.get("upstream_pin") != UPSTREAM_PIN
            or descriptor.get("archive") != expected_name
            or archive_asset.get("name") != expected_name):
        raise UpdateError("release descriptor identity or architecture is unsupported")
    compressed = descriptor.get("compressed_bytes")
    expanded = descriptor.get("expanded_bytes")
    digest = descriptor.get("sha256")
    manifest_sha = descriptor.get("manifest_sha256")
    if (not isinstance(compressed, int) or isinstance(compressed, bool) or compressed <= 0
            or compressed > MAX_ARCHIVE_BYTES
            or not isinstance(expanded, int) or isinstance(expanded, bool) or expanded <= 0
            or expanded > MAX_EXPANDED_BYTES
            or archive_asset.get("size") != compressed
            or archive_asset.get("digest") != f"sha256:{digest}"
            or not isinstance(digest, str) or not SHA_RE.fullmatch(digest)
            or not isinstance(manifest_sha, str) or not SHA_RE.fullmatch(manifest_sha)):
        raise UpdateError("release descriptor digest or size does not match trusted asset metadata")
    return descriptor


def fetch_release(tag: str, *, opener=urllib.request.urlopen) -> dict:
    """Resolve a GitHub release and bind descriptor/archive to its commit and asset digests."""
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise UpdateError("release version must be ccrate- followed by 12 lowercase commit characters")
    url = f"{API}/releases/tags/{tag}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                    "User-Agent": "ccrate-prebuilt-updater/1"})
    try:
        with opener(request, timeout=30) as response:
            metadata = _decode_release(tag, response)
    except UpdateError:
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError("trusted release could not be resolved") from exc
    commit = _tag_commit(tag, opener=opener)
    descriptor_asset = _asset(metadata["assets"], "release.json")
    descriptor_bytes, final_url = _request(descriptor_asset["url"], opener=opener,
                                           accept="application/octet-stream",
                                           limit=MAX_DESCRIPTOR_BYTES, expected=descriptor_asset["size"])
    if hashlib.sha256(descriptor_bytes).hexdigest() != descriptor_asset["digest"][7:]:
        raise UpdateError("release descriptor digest does not match GitHub asset metadata")
    try:
        descriptor = json.loads(descriptor_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise UpdateError("release descriptor is invalid") from exc
    archive_name = f"ccrate-linux-arm64-{commit[:12]}.tar.gz"
    archive_asset = _asset(metadata["assets"], archive_name)
    _validate_descriptor(tag, descriptor, archive_asset)
    if descriptor["commit"] != commit:
        raise UpdateError("release tag does not identify the descriptor source commit")
    return {"tag": tag, "commit": commit, "descriptor": descriptor,
            "descriptor_asset_url": descriptor_asset["url"], "descriptor_asset_digest": descriptor_asset["digest"],
            "archive_asset_url": archive_asset["url"], "archive_asset_digest": archive_asset["digest"]}


def _sha256(path):
    digest = hashlib.sha256()
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise UpdateError("release manifest is not a regular file")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
            os.close(fd)
            raise UpdateError("release manifest changed while opening")
        stream_context = os.fdopen(fd, "rb")
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError("release manifest could not be read safely") from exc
    with stream_context as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_release_object(release):
    if not isinstance(release, dict):
        raise UpdateError("release metadata is invalid")
    tag = release.get("tag")
    descriptor = release.get("descriptor")
    url = release.get("archive_asset_url")
    digest = release.get("archive_asset_digest")
    if (not isinstance(descriptor, dict) or not isinstance(url, str) or not url.startswith(API + "/releases/assets/")
            or not isinstance(digest, str) or digest != "sha256:" + str(descriptor.get("sha256", ""))):
        raise UpdateError("release archive is not bound to trusted GitHub asset metadata")
    _validate_descriptor(tag, descriptor, {"name": descriptor.get("archive"),
                                            "size": descriptor.get("compressed_bytes"),
                                            "digest": digest})


def _download_file(url, path, *, opener, limit, expected):
    if not isinstance(url, str) or not url.startswith(API + "/releases/assets/"):
        raise UpdateError("release archive URL is outside the trusted repository API")
    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream",
                                                    "User-Agent": "ccrate-prebuilt-updater/1"})
    digest = hashlib.sha256()
    total = 0
    try:
        with opener(request, timeout=60) as response:
            headers = getattr(response, "headers", {})
            raw_length = headers.get("Content-Length") if hasattr(headers, "get") else None
            if raw_length is not None:
                if int(raw_length) != expected or int(raw_length) > limit:
                    raise UpdateError("release archive size differs from its trusted descriptor")
            final_url = response.geturl() if hasattr(response, "geturl") else ""
            if not _trusted_asset_response(final_url):
                raise UpdateError("release archive redirected outside GitHub's HTTPS asset service")
            with path.open("xb") as output:
                while True:
                    chunk = response.read(min(1024 * 1024, limit - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit or total > expected:
                        raise UpdateError("release archive exceeds its trusted size bound")
                    digest.update(chunk)
                    output.write(chunk)
    except UpdateError:
        raise
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError("trusted release archive could not be downloaded") from exc
    if total != expected:
        raise UpdateError("release archive download is truncated")
    return digest.hexdigest()


def _safe_member_name(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise UpdateError("release archive contains an unsafe path")
    trimmed = name[:-1] if name.endswith("/") else name
    raw_parts = trimmed.split("/")
    path = PurePosixPath(trimmed)
    if path.is_absolute() or not raw_parts or any(part in ("", ".", "..") for part in raw_parts):
        raise UpdateError("release archive contains an unsafe path")
    if re.match(r"^[A-Za-z]:", name):
        raise UpdateError("release archive contains an absolute path")
    if path.parts[0] != "candidate":
        raise UpdateError("release archive must contain one candidate tree")
    return path.parts


def _archive_members(archive_path, descriptor):
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise UpdateError("release archive is corrupt or not gzip-compressed tar") from exc
    with archive:
        try:
            members = archive.getmembers()
        except (OSError, tarfile.TarError) as exc:
            raise UpdateError("release archive member table is invalid") from exc
        if not members or len(members) > MAX_MEMBERS:
            raise UpdateError("release archive has an unsupported number of members")
        names = set()
        expanded = 0
        top = set()
        for member in members:
            parts = _safe_member_name(member.name)
            normalized = "/".join(parts)
            if normalized in names:
                raise UpdateError("release archive contains duplicate paths")
            names.add(normalized)
            top.add(parts[0])
            if member.issym() or member.islnk() or member.isdev() or member.isfifo() or member.sparse:
                raise UpdateError("release archive contains a link, device or sparse file")
            if not (member.isdir() or member.isfile()):
                raise UpdateError("release archive contains an unsupported member type")
            if member.size < 0:
                raise UpdateError("release archive contains an invalid member size")
            if member.isfile():
                expanded += member.size
                if expanded > MAX_EXPANDED_BYTES:
                    raise UpdateError("release archive exceeds the expanded-size limit")
        if top != {"candidate"} or expanded != descriptor["expanded_bytes"]:
            raise UpdateError("release archive tree or expanded size differs from descriptor")
        return members


def _require_candidate_writer(manifest):
    provenance = manifest.get("provenance") if isinstance(manifest, dict) else None
    capability = provenance.get("workshop_capability") if isinstance(provenance, dict) else None
    names = ["workshop_read_v1", "workshop_read_v2", "workshop_write_v2"]
    receipt = provenance.get("test_receipt", {}).get("workshop_compatibility") if isinstance(provenance, dict) else None
    rows = receipt.get("tests") if isinstance(receipt, dict) else None
    if (not isinstance(capability, dict) or capability.get("read_versions") != [1, 2]
            or capability.get("write_mode") != "v2" or capability.get("test_names") != names
            or not isinstance(capability.get("closure_sha256"), str)
            or not SHA_RE.fullmatch(capability["closure_sha256"])
            or not isinstance(receipt, dict)
            or receipt.get("closure_sha256") != capability.get("closure_sha256")
            or not isinstance(rows, list)
            or rows != [{"name": name, "result": "passed"} for name in names]):
        raise UpdateError("candidate lacks artifact-matched Workshop v1/v2 read and v2 write capability")


def _validate_candidate(candidate, expected_manifest_sha, expected_identity=None, *, require_writer=True):
    manifest_path = candidate / "manifest.json"
    try:
        if _sha256(manifest_path) != expected_manifest_sha:
            raise UpdateError("candidate manifest digest differs from trusted descriptor")
        if validate_bundle is None:
            raise UpdateError("trusted sealed-bundle validator is unavailable")
        manifest = validate_bundle(candidate)
    except UpdateError:
        raise
    except (OSError, ValueError, BundleError) as exc:
        raise UpdateError("candidate sealed bundle failed trusted validation") from exc
    if manifest.get("format") != 2:
        raise UpdateError("candidate is not a sealed format-2 package")
    if require_writer:
        _require_candidate_writer(manifest)
    metadata_path = candidate / "public" / "ccrate-release.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise UpdateError("candidate public release identity is invalid") from exc
    if (not isinstance(metadata, dict) or metadata.get("format") != 1
            or metadata.get("application") != "ccrate"
            or not isinstance(metadata.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", metadata["commit"])
            or metadata.get("upstream_pin") != UPSTREAM_PIN):
        raise UpdateError("candidate public release identity does not match the trusted application")
    if expected_identity and (metadata["commit"] != expected_identity.get("commit")
                              or metadata.get("upstream_pin") != expected_identity.get("upstream_pin")):
        raise UpdateError("candidate public release identity differs from the trusted descriptor")
    return manifest


def stage_download(root: Path, release: dict, *, opener=urllib.request.urlopen) -> Path:
    """Download and extract one digest-bound package without touching active releases."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise UpdateError("installation root must be an existing real directory")
    _validate_release_object(release)
    descriptor = release["descriptor"]
    work = root / "work"
    work.mkdir(mode=0o700, exist_ok=True)
    downloads = work / "update-downloads"
    downloads.mkdir(mode=0o700, exist_ok=True)
    final = downloads / (release["tag"] + "-" + descriptor["sha256"][:16])
    candidate = final / "candidate"
    if final.exists():
        try:
            _validate_candidate(candidate, descriptor["manifest_sha256"], descriptor)
            return candidate
        except UpdateError as exc:
            raise UpdateError("an existing staged release is invalid; it was left unchanged") from exc
    temp = Path(tempfile.mkdtemp(prefix=".partial-", dir=downloads))
    try:
        if shutil.disk_usage(root).free < descriptor["compressed_bytes"] + descriptor["expanded_bytes"] + FREE_SPACE_RESERVE:
            raise UpdateError("insufficient free space for bounded release staging")
        archive_path = temp / descriptor["archive"]
        archive_sha = _download_file(release["archive_asset_url"], archive_path, opener=opener,
                                     limit=MAX_ARCHIVE_BYTES, expected=descriptor["compressed_bytes"])
        if archive_sha != descriptor["sha256"]:
            raise UpdateError("release archive SHA-256 differs from trusted GitHub metadata")
        members = _archive_members(archive_path, descriptor)
        package = temp / "candidate"
        package.mkdir(mode=0o700)
        modes = {}
        with tarfile.open(archive_path, mode="r:gz") as archive:
            for member in members:
                parts = _safe_member_name(member.name)
                relative = parts[1:]
                if not relative:
                    if not member.isdir():
                        raise UpdateError("release archive candidate root is not a directory")
                    modes[package] = stat.S_IMODE(member.mode) or 0o555
                    continue
                target = package.joinpath(*relative)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    modes[target] = (member.mode & 0o777) or 0o755
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise UpdateError("release archive file is unreadable")
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as output, source:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    if target.stat().st_size != member.size:
                        raise UpdateError("release archive file is truncated")
                    target.chmod(stat.S_IMODE(member.mode) & 0o777)
            for directory, mode in sorted(modes.items(), key=lambda row: len(row[0].parts), reverse=True):
                directory.chmod(mode)
        _validate_candidate(package, descriptor["manifest_sha256"], descriptor)
        (temp / "release.json").write_text(json.dumps(descriptor, sort_keys=True, indent=2) + "\n")
        os.replace(temp, final)
        return candidate
    except UpdateError:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        shutil.rmtree(temp, ignore_errors=True)
        raise UpdateError("release could not be safely staged") from exc


def _current_release(root):
    selector = root / "work" / "application-current"
    try:
        info = selector.lstat()
        if not stat.S_ISLNK(info.st_mode):
            return None, "application selector is not a symlink"
        previous = selector.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
        if not previous.is_relative_to(resolved_root / "work" / "releases"):
            return None, "application selector points outside the managed releases directory"
        manifest = _validate_candidate(previous, _sha256(previous / "manifest.json"), require_writer=False)
        if manifest.get("format") != 2:
            return None, "selected package is not a sealed format-2 release"
        return previous, None
    except (OSError, RuntimeError, UpdateError):
        return None, "application selector is missing, legacy or invalid"


def _runtime_issues(root):
    issues = []
    python = Path(sys.executable)
    node_paths = (root / "work/toolchains/node/bin/node", root / "work/toolchains/node/bin/nodejs")
    if not (python.is_file() and (python.name.startswith("python") or python.suffix.lower() == ".exe")):
        issues.append("Python runtime is unavailable")
    if not any(path.is_file() and os.access(path, os.X_OK) for path in node_paths) and not shutil.which("node"):
        issues.append("Node.js runtime is unavailable")
    if not shutil.which("chromium"):
        issues.append("Chromium runtime is unavailable")
    hardware = root / "work/hardware/python"
    if not hardware.is_dir():
        issues.append("installed hardware Python dependencies are missing")
    else:
        try:
            installed = {re.sub(r"[-_.]+", "-", distribution.metadata.get("Name", "")).lower()
                         for distribution in importlib.metadata.distributions(path=[str(hardware)])}
        except (OSError, ValueError):
            installed = set()
        required = {"pillow", "zxing-cpp", "qrcode"}
        if not required <= installed:
            issues.append("one or more installed Python application dependencies are missing")
    for path in (root / "work/baseline/data/homebox.db", root / "work/baseline/pepper",
                 root / "work/baseline/test-account.json", root / "work/ops/ledger.db"):
        if not path.is_file():
            issues.append("required existing application data is missing")
            break
    return issues


def _directory_bytes(path):
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            raise UpdateError("installation sizes could not be measured safely")
    return total


def _space_needed(root, candidate, previous):
    candidate_bytes = _directory_bytes(candidate)
    previous_bytes = _directory_bytes(previous)
    def kiosk_static(path):
        directory = path / "kiosk"
        return sum(item.stat().st_size for item in directory.rglob("*")
                   if item.is_file() and item.suffix != ".py") if directory.is_dir() else 0
    fallback_bytes = max(0, candidate_bytes - _directory_bytes(candidate / "public") - kiosk_static(candidate))
    fallback_bytes += _directory_bytes(previous / "public") + kiosk_static(previous)
    backup_bytes = sum(_directory_bytes(root / name) for name in (
        "work/baseline/data", "work/baseline/pepper", "work/baseline/test-account.json",
        "work/ops", "work/homebox-bin/homebox", "work/hardware/python",
        "work/supvan-cups/target/release/examples/kiosk-label", "work/label-ui-build")) + previous_bytes
    descriptor_path = candidate.parent / "release.json"
    try:
        download_bytes = json.loads(descriptor_path.read_text()).get("compressed_bytes", 0)
    except (OSError, ValueError, TypeError):
        download_bytes = 0
    return download_bytes + candidate_bytes + fallback_bytes + backup_bytes + FREE_SPACE_RESERVE


def preflight(root: Path, candidate: Path) -> dict:
    """Report readiness without touching services, the selector or user data."""
    root, candidate = Path(root), Path(candidate)
    result = {"status": "ready", "candidate_path": str(candidate), "previous_path": None, "reasons": []}
    try:
        if not root.is_dir() or root.is_symlink():
            return {**result, "status": "runtime_missing", "reasons": ["installation root is unavailable"]}
        previous, selector_issue = _current_release(root)
        if selector_issue:
            return {**result, "status": "migration_required", "reasons": [selector_issue]}
        result["previous_path"] = str(previous)
        try:
            descriptor_path = candidate.parent / "release.json"
            if descriptor_path.is_file():
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                commit = descriptor.get("commit") if isinstance(descriptor, dict) else None
                if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                    raise UpdateError("staged release descriptor identity is invalid")
                _validate_descriptor("ccrate-" + commit[:12], descriptor,
                                      {"name": descriptor.get("archive"),
                                       "size": descriptor.get("compressed_bytes"),
                                       "digest": "sha256:" + str(descriptor.get("sha256", ""))})
                expected_manifest = descriptor.get("manifest_sha256")
            else:
                descriptor = None
                expected_manifest = _sha256(candidate / "manifest.json")
            _validate_candidate(candidate, expected_manifest, descriptor)
        except (OSError, UpdateError):
            return {**result, "status": "runtime_missing", "reasons": ["staged sealed candidate is unavailable or invalid"]}
        if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
            return {**result, "status": "unsupported_arch", "reasons": ["updates require Linux ARM64"]}
        runtime = _runtime_issues(root)
        if runtime:
            return {**result, "status": "runtime_missing", "reasons": runtime}
        free = shutil.disk_usage(root).free
        needed = _space_needed(root, candidate, previous)
        descriptor_path = candidate.parent / "release.json"
        try:
            staged = json.loads(descriptor_path.read_text(encoding="utf-8"))
            already_used = staged["compressed_bytes"] + _directory_bytes(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            already_used = _directory_bytes(candidate)
        if free + already_used < needed:
            return {**result, "status": "insufficient_space",
                    "reasons": [f"update requires {needed} bytes free; available space is insufficient"]}
        return result
    except (OSError, RuntimeError, ValueError, TypeError, UpdateError):
        return {**result, "status": "runtime_missing", "reasons": ["installation could not be inspected safely"]}


def apply_update(root: Path, candidate: Path, *, run_services=None, verify=None):
    """Filled by the durable activation task; refuse until that transaction is available."""
    raise UpdateError("durable update activation is unavailable in this updater build")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        release = fetch_release(args.version)
        candidate = stage_download(args.root, release)
        result = preflight(args.root, candidate)
        if args.apply and result["status"] == "ready":
            result = apply_update(args.root, candidate)
        print(json.dumps(result, sort_keys=True))
        successful = result.get("status") == "ready" if args.check else result.get("status") in ("completed", "recovered")
        return 0 if successful else 2
    except UpdateError as exc:
        print(json.dumps({"status": "refused", "reasons": [str(exc)]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
