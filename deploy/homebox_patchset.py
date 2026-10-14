"""Materialize the pinned public Homebox source plus C-Crate's patch series."""
from __future__ import annotations

import hashlib
import json
import io
import contextlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import tarfile
import time


MARKER = ".ccrate-homebox-patchset.json"
SOURCE_MARKER = ".ccrate-homebox-source.json"


def load_patchset(root: pathlib.Path) -> tuple[str, list[pathlib.Path], str]:
    patch_dir = root / "deploy" / "homebox-patches"
    manifest = json.loads((root / "deploy" / "homebox-patchset.json").read_text())
    base = manifest.get("base")
    names = manifest.get("patches")
    if not isinstance(base, str) or len(base) != 40 or not isinstance(names, list) or not names:
        raise ValueError("Invalid Homebox patchset manifest")
    paths = []
    digest = hashlib.sha256()
    for name in names:
        if not isinstance(name, str) or pathlib.Path(name).name != name:
            raise ValueError("Homebox patch names must be plain filenames")
        patch = patch_dir / name
        content = patch.read_bytes()
        paths.append(patch)
        digest.update(name.encode("utf-8") + b"\0" + content)
    return base, paths, digest.hexdigest()


def apply_patchset(source: pathlib.Path, patches: list[pathlib.Path]) -> None:
    environment = os.environ.copy()
    environment["GIT_CEILING_DIRECTORIES"] = str(source.parent.resolve())
    for patch in patches:
        for command in (["git", "apply", "--check", str(patch)], ["git", "apply", str(patch)]):
            try:
                subprocess.run(
                    command,
                    cwd=source,
                    check=True,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError as error:
                detail = error.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Could not apply Homebox patch {patch.name}: {detail}") from error


def source_commit(upstream: pathlib.Path) -> str:
    upstream = upstream.resolve()
    probe = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
    )
    if probe.returncode == 0 and pathlib.Path(probe.stdout.strip()).resolve() == upstream:
        return subprocess.check_output(
            ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
        ).strip()

    marker = upstream / SOURCE_MARKER
    if not marker.is_file():
        raise ValueError("Homebox source snapshot has no verified commit marker")
    snapshot = json.loads(marker.read_text(encoding="utf-8"))
    commit = snapshot.get("commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid Homebox source snapshot commit marker")
    expected_digest = snapshot.get("tree_sha256")
    if not isinstance(expected_digest, str) or source_tree_digest(upstream) != expected_digest:
        raise ValueError("Homebox source snapshot does not match its commit marker")
    return commit


def source_tree_digest(root: pathlib.Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path in (root / SOURCE_MARKER, root / MARKER):
            continue
        if path.is_symlink():
            raise ValueError("Homebox source snapshot contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative + b"\0" + len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def export_source_snapshot(upstream: pathlib.Path, destination: pathlib.Path, commit: str) -> None:
    upstream = upstream.resolve()
    if source_commit(upstream) != commit:
        raise ValueError("Homebox source pin mismatch while exporting release snapshot")
    probe = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
    )
    if probe.returncode != 0 or pathlib.Path(probe.stdout.strip()).resolve() != upstream:
        raise ValueError("Release source snapshot must come from the pinned Homebox checkout")
    archive = subprocess.check_output(["git", "-C", str(upstream), "archive", "--format=tar", commit])
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        root_path = destination.resolve()
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(root_path) or member.issym() or member.islnk():
                raise ValueError("Homebox source archive contains an unsafe path")
        source.extractall(destination)
    (destination / SOURCE_MARKER).write_text(
        json.dumps({"commit": commit, "tree_sha256": source_tree_digest(destination)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_snapshot(upstream: pathlib.Path, destination: pathlib.Path) -> None:
    for current, directories, files in os.walk(upstream, followlinks=False):
        for name in directories + files:
            if (pathlib.Path(current) / name).is_symlink():
                raise ValueError("Homebox source snapshot contains a symlink")
    shutil.copytree(
        upstream,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", SOURCE_MARKER),
    )


@contextlib.contextmanager
def _source_lock(path: pathlib.Path):
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def materialize(root: pathlib.Path) -> pathlib.Path:
    root = root.resolve()
    upstream = root / "upstream" / "homebox"
    base, patches, digest = load_patchset(root)
    pin = source_commit(upstream)
    if pin != base:
        raise ValueError(f"Homebox source pin mismatch: expected {base}, got {pin}")

    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    with _source_lock(work / ".homebox-source-patchset.lock"):
        return _materialize_locked(upstream, base, patches, digest, work)


def _materialize_locked(
    upstream: pathlib.Path,
    base: str,
    patches: list[pathlib.Path],
    digest: str,
    work: pathlib.Path,
) -> pathlib.Path:
    destination = work / "homebox-source-patched"
    replace_existing = destination.exists()
    if replace_existing:
        marker = destination / MARKER
        if not marker.is_file():
            raise ValueError(f"Refusing to replace unowned source tree: {destination}")
        old = json.loads(marker.read_text())
        if old.get("builder") != "deploy/homebox_patchset.py":
            raise ValueError(f"Refusing to replace unowned source tree: {destination}")
        # Reuse only an intact, content-verified build. This keeps concurrent
        # UI/backend builds from replacing a source tree another build reads.
        if (
            old.get("materializer_version") == 4
            and old.get("base") == base
            and old.get("patchset_sha256") == digest
            and old.get("tree_sha256") == source_tree_digest(destination)
        ):
            return destination

    temp = pathlib.Path(tempfile.mkdtemp(prefix="homebox-source-", dir=work))
    previous = None
    try:
        if (upstream / ".git").exists():
            archive = subprocess.check_output(
                ["git", "-C", str(upstream), "archive", "--format=tar", base]
            )
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
                root_path = temp.resolve()
                for member in source.getmembers():
                    target = (temp / member.name).resolve()
                    if not target.is_relative_to(root_path) or member.issym() or member.islnk():
                        raise ValueError("Homebox source archive contains an unsafe path")
                source.extractall(temp)
        else:
            _copy_snapshot(upstream, temp)
        apply_patchset(temp, patches)
        (temp / MARKER).write_text(
            json.dumps(
                {
                    "builder": "deploy/homebox_patchset.py",
                    "materializer_version": 4,
                    "base": base,
                    "patchset_sha256": digest,
                    "tree_sha256": source_tree_digest(temp),
                },
                indent=2,
            )
            + "\n"
        )
        if replace_existing:
            previous = work / f"{temp.name}-previous"
            destination.replace(previous)
        temp.replace(destination)
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        if previous is not None and previous.exists() and not destination.exists():
            previous.replace(destination)
        raise
    return destination
