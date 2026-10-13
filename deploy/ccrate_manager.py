#!/usr/bin/env python3
"""Small, guarded terminal manager for this C-Crate checkout."""
import curses
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SERVICES = {
    "native": "homebox-native.service",
    "companion": "homebox-companion.service",
    "gateway": "homebox-workshop-gateway.service",
}
START_ORDER = tuple(SERVICES)
STOP_ORDER = tuple(reversed(START_ORDER))
DBS = ("work/baseline/data/homebox.db", "work/ops/ledger.db", "work/ops/workshop.db",
       "work/ops/imports.db", "work/ops/label-layouts.db")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_STATUS_RELEASE_CACHE = {}


def parse_properties(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def format_uptime(seconds):
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def active_set_is_ordered(active):
    active = set(active)
    return all(name not in active or set(START_ORDER[:index]) <= active
               for index, name in enumerate(START_ORDER))


def unit_belongs_to_root(component, properties, root, *, home=None):
    root = Path(root).resolve()
    home = Path.home() if home is None else Path(home)
    name = SERVICES[component]
    fragment = Path(properties.get("FragmentPath", ""))
    expected_fragment = home / ".config/systemd/user" / name
    command = properties.get("ExecStart", "")
    argv_match = re.search(r"argv\[\]=(.+?)(?:\s+;|\s*})", command)
    try:
        argv = shlex.split(argv_match.group(1)) if argv_match else []
    except ValueError:
        return False
    try:
        environment = shlex.split(properties.get("Environment", ""))
    except ValueError:
        return False
    launcher = str(root / "work/application-current/deploy/run-release.py")
    return (fragment == expected_fragment
            and any(argv[index:index + 2] == [launcher, component]
                    for index in range(max(0, len(argv) - 1)))
            and f"WORKSHOP_ROOT={root}" in environment)


def _run(args, *, cwd=None, check=False, capture=True):
    return subprocess.run(args, cwd=cwd, check=check, text=True,
                          capture_output=capture)


def _systemctl(*args):
    return _run(["systemctl", "--user", *args], check=True)


def _linger():
    result = _run(["loginctl", "show-user", str(os.getuid()), "--property=Linger", "--value"])
    return result.stdout.strip() == "yes" if result.returncode == 0 else None


def get_service_statuses(root=ROOT):
    statuses = {}
    now = time.monotonic() * 1_000_000
    for component, unit in SERVICES.items():
        result = _run(["systemctl", "--user", "show", unit,
                       "--property=ActiveState,MainPID,UnitFileState,ActiveEnterTimestampMonotonic,FragmentPath,ExecStart,Environment"])
        props = parse_properties(result.stdout) if result.returncode == 0 else {}
        entered = props.get("ActiveEnterTimestampMonotonic", "")
        uptime = None
        try:
            if props.get("ActiveState") == "active" and int(entered) > 0:
                uptime = int((now - int(entered)) / 1_000_000)
        except ValueError:
            pass
        statuses[component] = {
            "active": props.get("ActiveState") == "active",
            "state": props.get("ActiveState", "unknown"),
            "pid": props.get("MainPID", "0"),
            "uptime": uptime,
            "enabled": props.get("UnitFileState", "unknown"),
            "owned": unit_belongs_to_root(component, props, root),
        }
    return statuses


def compare_versions(installed, remote):
    if not isinstance(installed, str) or not COMMIT_RE.fullmatch(installed):
        return {"state": "unknown", "installed": installed, "remote": remote}
    if not isinstance(remote, str) or not COMMIT_RE.fullmatch(remote):
        return {"state": "unknown", "installed": installed, "remote": remote}
    return {"state": "current" if installed == remote else "pending",
            "installed": installed, "remote": remote}


def installed_commit(manifest):
    provenance = manifest.get("provenance", {}) if isinstance(manifest, dict) else {}
    build = provenance.get("build_receipt", {})
    for key in ("project_commit", "source_commit"):
        for record in (provenance, build):
            value = record.get(key) if isinstance(record, dict) else None
            if isinstance(value, str) and COMMIT_RE.fullmatch(value):
                return value
    return None


def release_hint(release, manifest):
    commit = installed_commit(manifest)
    if commit:
        return commit[:12]
    match = re.match(r"^([0-9a-f]{7,40})-", Path(release).name)
    return f"{match.group(1)} (release name hint)" if match else "unknown"


def _update_status(root):
    path = Path(root) / "work/manager-update-status.json"
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != 1:
            return None
        if value.get("outcome") == "running":
            try:
                os.kill(int(value.get("pid", 0)), 0)
            except (OSError, ValueError, TypeError):
                value = dict(value, outcome="abandoned", stage="abandoned")
        return value
    except (OSError, ValueError):
        return None


def _assert_no_pending_manager_transaction(root, *, allow_running_build=False):
    status = _update_status(root)
    if status and status.get("stage") in ("activation-stopping", "activation-selected"):
        raise RuntimeError("An interrupted activation needs inspection before another update")
    if (not allow_running_build and status and status.get("outcome") == "running"):
        raise RuntimeError("A source update is already running")


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_inventory(path, arcname):
    path = Path(path)
    _check_source_tree(path)
    if path.is_symlink() or not path.exists():
        raise RuntimeError(f"Backup source is missing or linked: {path}")
    rows = {}
    if path.is_file():
        sources = [(path, arcname)]
    elif path.is_dir():
        sources = []
        for base, directories, files in os.walk(path, followlinks=False):
            base_path = Path(base)
            for name in directories + files:
                child = base_path / name
                info = child.lstat()
                if (child.is_symlink() or not (child.is_dir() or child.is_file())
                        or (child.is_file() and info.st_nlink != 1)):
                    raise RuntimeError(f"Backup tree contains a linked or special file: {child}")
                if child.is_file():
                    sources.append((child, f"{arcname}/{child.relative_to(path).as_posix()}"))
    else:
        raise RuntimeError(f"Backup source is not a regular file or directory: {path}")
    for source, name in sources:
        info = source.lstat()
        if not os.path.isfile(source) or source.is_symlink() or info.st_nlink != 1:
            raise RuntimeError(f"Backup file changed or is linked: {source}")
        rows[name] = {"sha256": _file_hash(source), "size": info.st_size}
    return rows


def _check_source_tree(path):
    path = Path(path)
    if path.is_symlink() or not path.exists() or not (path.is_file() or path.is_dir()):
        raise RuntimeError(f"Backup source is missing, linked, or special: {path}")
    if path.is_file():
        if path.lstat().st_nlink != 1:
            raise RuntimeError(f"Backup file has unexpected hard links: {path}")
        return
    for base, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            child = Path(base) / name
            info = child.lstat()
            if (child.is_symlink() or not (child.is_dir() or child.is_file())
                    or (child.is_file() and info.st_nlink != 1)):
                raise RuntimeError(f"Backup tree contains a linked or special file: {child}")


def _archive_member(archive, path, name):
    path, name = Path(path), str(name)
    archive.add(path, arcname=name, recursive=True,
                filter=lambda member: _private_tar_info(member))


def _private_tar_info(member):
    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
        raise RuntimeError(f"Refusing unsafe backup archive member: {member.name}")
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    member.mode &= 0o777
    return member


def _tar_bytes(archive, name, body):
    import io
    info = tarfile.TarInfo(name)
    info.size = len(body)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(body))


def _verify_archive(path, expected):
    with tarfile.open(path, "r:gz") as archive:
        seen = {}
        for member in archive.getmembers():
            name = member.name.rstrip("/")
            if not name or name.startswith("/") or ".." in Path(name).parts or name in seen:
                raise RuntimeError("Backup archive contains an unsafe or duplicate member")
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError("Backup archive contains a non-regular file")
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError("Backup archive file could not be read")
            digest = hashlib.sha256()
            size = 0
            with stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            seen[name] = {"sha256": digest.hexdigest(), "size": size}
    manifest_member = seen.get("backup-manifest.json")
    if seen != expected or manifest_member is None:
        raise RuntimeError("Backup archive membership or hashes do not match the source inventory")
    return manifest_member


def _checkpoint_databases(root):
    for relative in DBS:
        path = Path(root) / relative
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Refusing unsafe database path: {path}")
        with sqlite3.connect(path) as connection:
            if connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
                raise RuntimeError(f"Database checkpoint was busy: {relative}")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError(f"Database integrity check failed: {relative}")


def _atomic_private_text(path, text):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _create_snapshot(root, release, *, active, enabled, linger):
    root, release = Path(root).resolve(), Path(release).resolve(strict=True)
    backup_root = root / "work/backups"
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup_root.is_symlink() or not backup_root.is_dir():
        raise RuntimeError("Backup destination is unsafe")
    os.chmod(backup_root, 0o700)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f"{time.time_ns() % 1_000_000_000:09d}Z"
    destination = backup_root / f"manager-{stamp}.tar.gz"
    sources = [(root / "work/baseline", "baseline"), (root / "work/ops", "ops"),
               (release, "application-release")]
    login = root.parent / "C-Crate Login.txt"
    if login.exists() or login.is_symlink():
        sources.append((login, "private/C-Crate Login.txt"))
    expected = {}
    for source, name in sources:
        expected.update(_safe_inventory(source, name))
    selector = root / "work/application-current"
    if not selector.is_symlink():
        raise RuntimeError("Application selector is not a symlink")
    selector_info = {
        "selector_target": os.readlink(selector),
        "selected_release": str(release),
        "release_manifest_sha256": _file_hash(release / "manifest.json"),
        "active_services": list(active), "enabled_services": list(enabled),
        "linger": linger,
    }
    selector_raw = (json.dumps(selector_info, sort_keys=True, indent=2) + "\n").encode()
    expected["selector.json"] = {"sha256": hashlib.sha256(selector_raw).hexdigest(), "size": len(selector_raw)}
    manifest = {"format": 1, "created_at": stamp, "project_root": str(root),
                "members": expected, "selector": selector_info}
    manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    expected["backup-manifest.json"] = {"sha256": hashlib.sha256(manifest_raw).hexdigest(),
                                         "size": len(manifest_raw)}
    fd, temporary = tempfile.mkstemp(prefix=".manager-backup-", suffix=".partial", dir=backup_root)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz", compresslevel=1) as archive:
                for source, name in sources:
                    _archive_member(archive, source, name)
                _tar_bytes(archive, "selector.json", selector_raw)
                _tar_bytes(archive, "backup-manifest.json", manifest_raw)
            stream.flush()
            os.fsync(stream.fileno())
        _verify_archive(temporary, expected)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        checksum = _file_hash(destination)
        _atomic_private_text(destination.with_suffix(".sha256"), f"{checksum}  {destination.name}\n")
        return destination
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install_update(root=ROOT, *, commit, reuse_existing_builds=False):
    """Prepare the approved commit, then atomically select its sealed bundle."""
    import fcntl
    from deploy.ccrate_update import _prepare_candidate_locked, _write_status
    from deploy.release_bundle import _transaction_lock, validate_bundle

    root = Path(root).resolve(strict=True)
    if not COMMIT_RE.fullmatch(str(commit)):
        raise ValueError("Install requires the full approved source commit")
    lock_path = root / "work/.manager-update.lock"
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    started = time.time()
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another source update is already running") from exc
        _write_status(root, stage="preparing", started_at=started, commit=commit)
        if reuse_existing_builds:
            from deploy.ccrate_update import _build_and_stage, _git
            builder = lambda project, candidate, pinned: _build_and_stage(
                project, candidate, pinned,
                _git(candidate / "upstream/homebox", "rev-parse", "HEAD"), reuse_existing=True)
        else:
            builder = None
        prepared = _prepare_candidate_locked(root, commit=commit, builder=builder, started=started)
        candidate = Path(prepared["candidate"] if isinstance(prepared, dict) else prepared).resolve(strict=True)
        validate_bundle(candidate)
        with _transaction_lock(root):
            _selected_release(root)
            selector = root / "work/application-current"
            statuses = get_service_statuses(root)
            if not _known_service_state(statuses):
                raise RuntimeError("C-Crate service ownership or state is unknown")
            active = [name for name in START_ORDER if statuses[name]["active"]]
            if not active_set_is_ordered(active):
                raise RuntimeError("C-Crate services are not active in dependency order")
            _write_status(root, stage="activation-stopping", started_at=started, commit=commit,
                          log_path=candidate)
            selected = False
            try:
                for component in STOP_ORDER:
                    if component in active:
                        _systemctl("stop", SERVICES[component])
                if not _all_stopped(get_service_statuses(root)):
                    raise RuntimeError("C-Crate services did not stop cleanly")
                temporary = selector.with_name(f".application-current.{uuid.uuid4().hex}.next")
                os.symlink(os.path.relpath(candidate, selector.parent), temporary, target_is_directory=True)
                os.replace(temporary, selector)
                selected = True
                directory_fd = os.open(selector.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                _write_status(root, stage="activation-selected", started_at=started,
                              commit=commit, log_path=candidate)
                for component in START_ORDER:
                    if component in active:
                        _systemctl("start", SERVICES[component])
                deadline, last_error = time.monotonic() + 45, None
                while time.monotonic() < deadline:
                    try:
                        current = get_service_statuses(root)
                        if {name for name in START_ORDER if current[name]["active"]} != set(active):
                            raise RuntimeError("Started service set differs from the previous active set")
                        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        checks = (("native", "http://127.0.0.1:17747/api/v1/status", None),
                                  ("companion", "http://127.0.0.1:17749/", candidate / "kiosk/index.html"),
                                  ("gateway", "http://127.0.0.1:17745/", candidate / "public/index.html"),
                                  ("metadata", "http://127.0.0.1:17745/ccrate-release.json",
                                   candidate / "public/ccrate-release.json"))
                        for name, url, expected in checks:
                            if name != "metadata" and name != "native" and name not in active:
                                continue
                            if name == "native" and name not in active:
                                continue
                            if name == "metadata" and "gateway" not in active:
                                continue
                            with opener.open(url, timeout=3) as response:
                                body = response.read()
                                if response.status != 200:
                                    raise RuntimeError(f"{name} readiness returned HTTP {response.status}")
                            if expected is not None and body != expected.read_bytes():
                                raise RuntimeError(f"{name} served content from a different release")
                            if name == "native" and not isinstance(json.loads(body), dict):
                                raise RuntimeError("Native readiness response is not a JSON object")
                        break
                    except Exception as exc:
                        last_error = exc
                        time.sleep(0.5)
                else:
                    raise RuntimeError(f"Selected release health check failed: {last_error}")
            except BaseException as exc:
                if not selected:
                    restore_errors = []
                    for component in START_ORDER:
                        if component in active:
                            try:
                                _systemctl("start", SERVICES[component])
                            except Exception as restore_error:
                                restore_errors.append(str(restore_error))
                    if restore_errors:
                        exc = RuntimeError(f"{exc}; previous services could not all be restored: {restore_errors}")
                _write_status(root, stage="failed-after-selection" if selected else "failed-before-selection",
                              started_at=started, outcome="failed", commit=commit,
                              error=str(exc)[:500], log_path=candidate)
                raise exc
        _write_status(root, stage="installed", started_at=started, outcome="success",
                      commit=commit, log_path=candidate)
        return candidate
    except BaseException as exc:
        status = _update_status(root)
        if status and status.get("pid") == os.getpid() and status.get("outcome") == "running" and status.get("stage") not in (
                "failed-before-selection", "failed-after-selection"):
            _write_status(root, stage="failed", started_at=started, outcome="failed",
                          commit=commit, error=str(exc)[:500])
        raise
    finally:
        os.close(fd)


def _selected_release(root):
    from deploy.release_bundle import validate_bundle
    selector = Path(root) / "work/application-current"
    release = selector.resolve(strict=True)
    allowed = (Path(root) / "work/application-releases").resolve(strict=True)
    release.relative_to(allowed)
    manifest = validate_bundle(release)
    if manifest.get("format") != 2:
        raise RuntimeError("Selected release is not launcher-capable format 2")
    return release, manifest


def _preflight_backup_trees(root, release):
    root = Path(root)
    _check_source_tree(root / "work/baseline")
    _check_source_tree(root / "work/ops")
    _check_source_tree(release)
    login = root.parent / "C-Crate Login.txt"
    if login.exists() or login.is_symlink():
        _check_source_tree(login)


def _read_selected_manifest(root):
    selector = Path(root) / "work/application-current"
    release = selector.resolve(strict=True)
    manifest_path = release / "manifest.json"
    info = manifest_path.stat()
    key = (str(release), info.st_mtime_ns, info.st_size)
    manifest = _STATUS_RELEASE_CACHE.get(key)
    if manifest is None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _STATUS_RELEASE_CACHE.clear()
        _STATUS_RELEASE_CACHE[key] = manifest
    return release, manifest


def _known_service_state(statuses):
    for component, row in statuses.items():
        if not row.get("owned") or row.get("state") not in ("active", "inactive", "failed"):
            return False
        try:
            pid = int(row.get("pid", "0"))
        except (TypeError, ValueError):
            return False
        if (row["state"] == "active") != (pid > 0):
            return False
    return True


def _all_stopped(statuses):
    return all(row.get("owned") and row.get("state") in ("inactive", "failed")
               and str(row.get("pid", "0")) == "0" for row in statuses.values())


def _enabled_services(statuses):
    return [component for component in START_ORDER if statuses[component].get("enabled") in
            ("enabled", "enabled-runtime", "linked", "linked-runtime")]


def cold_backup(root=ROOT):
    from deploy.release_bundle import _transaction_lock
    root = Path(root).resolve(strict=True)
    with _transaction_lock(root):
        _assert_no_pending_manager_transaction(root)
        release, _manifest = _selected_release(root)
        _preflight_backup_trees(root, release)
        initial = get_service_statuses(root)
        if not _known_service_state(initial):
            raise RuntimeError("C-Crate service state or unit identity is unknown; backup refused")
        active = [name for name in START_ORDER if initial[name]["active"]]
        if not active_set_is_ordered(active):
            raise RuntimeError("Service state is not dependency-closed; backup refused")
        enabled = _enabled_services(initial)
        linger = _linger()
        failure = None
        try:
            for component in STOP_ORDER:
                if component in active:
                    _systemctl("stop", SERVICES[component])
            stopped = get_service_statuses(root)
            if not _all_stopped(stopped):
                raise RuntimeError("C-Crate services did not all stop; backup aborted")
            _checkpoint_databases(root)
            return _create_snapshot(root, release, active=active, enabled=enabled, linger=linger)
        except BaseException as exc:
            failure = exc
        finally:
            restore_errors = []
            try:
                before_restore = get_service_statuses(root)
            except Exception as exc:
                before_restore = {}
                restore_errors.append(f"status before restore: {exc}")
            for component in START_ORDER:
                if component in active:
                    if not before_restore.get(component, {}).get("owned"):
                        restore_errors.append(f"{component} unit identity changed; start skipped")
                        continue
                    try:
                        _systemctl("start", SERVICES[component])
                    except Exception as exc:
                        restore_errors.append(f"{component} start failed: {exc}")
            try:
                restored = get_service_statuses(root)
                active_after = {name for name in START_ORDER if restored[name]["active"]}
                if active_after != set(active):
                    restore_errors.append(f"active set is {sorted(active_after)}, expected {active}")
            except Exception as exc:
                restore_errors.append(f"final status check: {exc}")
            if restore_errors:
                raise RuntimeError("Could not restore the original C-Crate service set: " +
                                   "; ".join(restore_errors)) from failure
        if failure is not None:
            raise failure


def check_updates(root=ROOT):
    _run(["git", "fetch", "--quiet", "origin", "main"], cwd=root, check=True)
    remote = _run(["git", "rev-parse", "FETCH_HEAD"], cwd=root, check=True).stdout.strip()
    manifest = _selected_release(root)[1]
    result = compare_versions(installed_commit(manifest), remote)
    result["release_hint"] = release_hint((Path(root) / "work/application-current").resolve(), manifest)
    result["installable"] = True
    return result


def _status_lines(root=ROOT, statuses=None, update=None):
    root = Path(root)
    statuses = statuses if statuses is not None else get_service_statuses(root)
    linger = _linger()
    lines = ["C-CRATE MANAGER", "",
             f"{'Service':<23} {'Status':<9} {'PID':<7} {'Uptime':<10} Startup"]
    for component, label in (("native", "Inventory"), ("companion", "Equipment Terminal"),
                             ("gateway", "Web interface")):
        row = statuses[component]
        state = row.get("state", "unknown")
        if not row.get("owned") and state != "unknown":
            state = "foreign unit"
        pid = row.get("pid", "0") if row.get("owned") else "—"
        uptime = format_uptime(row.get("uptime")) if row.get("active") else "—"
        enabled_state = row.get("enabled", "unknown")
        enabled = (("boot" if linger else "login")
                   if enabled_state in ("enabled", "enabled-runtime", "linked", "linked-runtime") and linger is not None
                   else "on" if enabled_state in ("enabled", "enabled-runtime", "linked", "linked-runtime")
                   else "off" if enabled_state in ("disabled", "static", "indirect", "masked") else "?")
        lines.append(f"{label:<23} {state:<9} {pid:<7} {uptime:<10} {enabled}")
    lines.append(f"User lingering: {'enabled (can start at boot)' if linger else 'disabled (starts after login)' if linger is False else 'unknown'}")
    try:
        release, manifest = _read_selected_manifest(root)
        lines.append(f"Installed release: {release_hint(release, manifest)}")
        if update is None:
            lines.append("Main update check: not checked")
        elif update["state"] == "current":
            lines.append(f"Main update check: up to date ({update['remote'][:12]})")
        elif update["state"] == "pending":
            lines.append(f"Main update check: update pending ({update['remote'][:12]})")
        else:
            remote = str(update.get("remote") or "")
            lines.append(f"Main update check: installed identity unknown; origin/main {remote[:12]}")
        install_status = _update_status(root)
        if install_status and install_status.get("outcome") == "abandoned":
            lines.append(f"Update installer: stopped at {install_status.get('stage', 'unknown')}")
        elif install_status and install_status.get("outcome") == "running":
            lines.append(f"Update installer: {install_status.get('stage', 'working')} (PID {install_status.get('pid', '?')})")
            if install_status.get("log_path"):
                lines.append(f"Update log: {install_status['log_path']}")
            elapsed = max(0, int(time.time() - float(install_status.get("started_at", time.time()))))
            lines.append(f"Update elapsed: {format_uptime(elapsed)}")
        elif install_status and install_status.get("outcome") == "failed":
            lines.append(f"Update installer: failed at {install_status.get('stage', 'unknown')}")
            if install_status.get("error"):
                lines.append(f"Update error: {install_status['error']}")
            if install_status.get("log_path"):
                lines.append(f"Update log: {install_status['log_path']}")
        elif install_status and install_status.get("outcome") == "success":
            label = "installed" if install_status.get("stage") == "installed" else "candidate prepared"
            lines.append(f"Update installer: {label} {str(install_status.get('commit') or '')[:12]}")
        else:
            lines.append("Update installer: ready")
    except (OSError, ValueError, TypeError) as exc:
        lines.append(f"Installed release: unavailable ({exc})")
    lines.extend(["", "1 Start all   2 Stop all   3 Restart all",
                  "4 Enable login   5 Disable login   6 Start at boot",
                  "7 Recent logs   8 Check updates",
                  "B Back up data   I Build and install   U Reuse builds   R Refresh   Q Quit",
                  "Boot startup may start all enabled services for this user."])
    return lines


def _confirm(screen, prompt, expected):
    height, width = screen.getmaxyx()
    screen.timeout(-1)
    screen.addnstr(height - 1, 0, (prompt + f" Type {expected}: ")[:width - 1], width - 1)
    screen.clrtoeol()
    screen.refresh()
    curses.echo()
    try:
        answer = screen.getstr(height - 1, min(len(prompt) + len(expected) + 8, width - 2), 32)
    finally:
        curses.noecho()
        screen.timeout(1000)
    return answer.decode(errors="replace") == expected


def _show_logs(screen):
    result = _run(["journalctl", "--user", *sum((["-u", unit] for unit in SERVICES.values()), []),
                   "-n", "70", "--no-pager"])
    rows = result.stdout.splitlines() or [result.stderr.strip() or "No service logs are available."]
    screen.erase()
    height, width = screen.getmaxyx()
    screen.addnstr(0, 0, "Recent C-Crate service logs — any key returns", width - 1)
    for index, line in enumerate(rows[-max(1, height - 2):], 1):
        screen.addnstr(index, 0, line, width - 1)
    screen.refresh()
    screen.timeout(-1)
    screen.getch()
    screen.timeout(1000)


def _control_services(action, root=ROOT):
    from deploy.release_bundle import _transaction_lock
    with _transaction_lock(Path(root).resolve(strict=True)):
        if action in ("start", "restart"):
            _assert_no_pending_manager_transaction(root)
        _assert_owned(get_service_statuses(root))
        if action == "start":
            _systemctl("start", *(SERVICES[item] for item in START_ORDER))
        elif action == "stop":
            _systemctl("stop", *(SERVICES[item] for item in STOP_ORDER))
        elif action == "restart":
            _systemctl("stop", *(SERVICES[item] for item in STOP_ORDER))
            _systemctl("start", *(SERVICES[item] for item in START_ORDER))
        else:
            raise ValueError("Unknown service action")


def _control_login(action, root=ROOT):
    from deploy.release_bundle import _transaction_lock
    with _transaction_lock(Path(root).resolve(strict=True)):
        if action == "enable":
            _assert_no_pending_manager_transaction(root)
        _assert_owned(get_service_statuses(root))
        _systemctl(action, *(SERVICES[item] for item in START_ORDER))


def _control_boot_start(root=ROOT):
    from deploy.release_bundle import _transaction_lock
    with _transaction_lock(Path(root).resolve(strict=True)):
        _assert_no_pending_manager_transaction(root)
        _assert_owned(get_service_statuses(root))
        lingering = _linger()
        if lingering is None:
            raise RuntimeError("Could not verify this user's boot startup setting")
        if not lingering:
            _run(["loginctl", "enable-linger", str(os.getuid())], check=True)
        try:
            _systemctl("enable", *(SERVICES[item] for item in START_ORDER))
        except Exception as exc:
            if not lingering:
                try:
                    _run(["loginctl", "disable-linger", str(os.getuid())], check=True)
                except Exception as rollback:
                    raise RuntimeError(f"Could not enable services ({exc}); linger rollback failed ({rollback})") from exc
            raise


def _assert_owned(statuses):
    if any(not row.get("owned") for row in statuses.values()):
        raise RuntimeError("Service unit identity check failed; no action taken")


def _show_message(screen, message):
    import textwrap
    screen.erase()
    height, width = screen.getmaxyx()
    screen.addnstr(0, 0, "C-Crate Manager", width - 1)
    for index, line in enumerate(textwrap.wrap(message, max(10, width - 2))[:max(1, height - 3)], 2):
        screen.addnstr(index, 0, line, width - 1)
    screen.addnstr(height - 1, 0, "Press any key to return", width - 1)
    screen.refresh()
    screen.timeout(-1)
    screen.getch()
    screen.timeout(1000)


def _progress(screen, message):
    height, width = screen.getmaxyx()
    screen.addnstr(height - 2, 0, message, width - 1)
    screen.clrtoeol()
    screen.refresh()


def _run_install_from_menu(screen, commit, root=ROOT, *, reuse_existing_builds=False):
    root = Path(root)
    log_path = root / "work" / f"manager-update-{commit[:12]}.log"
    fd = os.open(log_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as log:
        args = [sys.executable, str(Path(__file__).resolve()), "--install-commit", commit]
        if reuse_existing_builds:
            args.append("--reuse-existing-builds")
        process = subprocess.Popen(args,
                                   cwd=root, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            status = _update_status(root) or {}
            elapsed = max(0, int(time.time() - float(status.get("started_at", time.time()))))
            height, width = screen.getmaxyx()
            screen.erase()
            lines = ["C-Crate update", f"Stage: {status.get('stage', 'starting')}  PID: {status.get('pid', '?')}",
                     f"Elapsed: {format_uptime(elapsed)}",
                     f"Log: {status.get('log_path') or log_path}",
                     "Status is also available with --status."]
            for index, line in enumerate(lines[:max(1, height - 1)]):
                screen.addnstr(index, 0, line, max(1, width - 1))
            screen.refresh()
            time.sleep(0.7)
    if process.returncode:
        raise RuntimeError(f"Installer exited {process.returncode}; log: {log_path}")


def _menu(screen):
    curses.curs_set(0)
    screen.timeout(1000)
    use_color = not os.environ.get("NO_COLOR") and curses.has_colors()
    if use_color:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
    message = ""
    update = None
    last_refresh = 0.0
    while True:
        if time.monotonic() - last_refresh >= 3:
            try:
                statuses = get_service_statuses(ROOT)
            except Exception as exc:
                statuses = {key: {"state": str(exc), "owned": False, "active": False} for key in SERVICES}
            last_refresh = time.monotonic()
        screen.erase()
        height, width = screen.getmaxyx()
        lines = _status_lines(ROOT, statuses, update)
        for index, line in enumerate(lines[:max(1, height - 2)]):
            color = 0
            if use_color:
                if index == 0:
                    color = 1
                elif 3 <= index <= 5:
                    component = START_ORDER[index - 3]
                    row = statuses.get(component, {})
                    color = 2 if row.get("state") == "active" and row.get("owned") else 3 if row.get("state") in ("failed", "unknown") or not row.get("owned") else 0
                elif "pending" in line or "unknown" in line or "unavailable" in line:
                    color = 3
            screen.addnstr(index, 0, line, max(1, width - 1),
                           curses.color_pair(color) if use_color and color else 0)
        if message:
            screen.addnstr(height - 2, 0, message, max(1, width - 1))
        screen.refresh()
        key = screen.getch()
        if key in (ord("q"), ord("Q")):
            return
        try:
            if key in (ord("r"), ord("R")):
                last_refresh = 0
                message = "Status refreshed."
            elif key in map(ord, "123"):
                action = {ord("1"): "start", ord("2"): "stop", ord("3"): "restart"}[key]
                if _confirm(screen, f"{action.title()} all C-Crate services?", action.upper()):
                    _progress(screen, {"start": "Starting services…", "stop": "Stopping services…",
                                       "restart": "Restarting services…"}[action])
                    _control_services(action)
                    message = f"Requested {action} of C-Crate services."
                    last_refresh = 0
            elif key in (ord("4"), ord("5")):
                action = "enable" if key == ord("4") else "disable"
                if _confirm(screen, f"{action.title()} C-Crate services at user login?", action.upper()):
                    _progress(screen, "Updating login startup…")
                    _control_login(action)
                    message = f"Services {action}d at login."
                    last_refresh = 0
            elif key == ord("6"):
                prompt = "Enable boot? Linger affects all user services."
                if _confirm(screen, prompt, "BOOT"):
                    _progress(screen, "Updating boot startup…")
                    _control_boot_start(ROOT)
                    message = "C-Crate services enabled for boot startup."
                    last_refresh = 0
            elif key == ord("7"):
                _show_logs(screen)
            elif key == ord("8"):
                try:
                    _progress(screen, "Checking origin/main…")
                    update = check_updates(ROOT)
                    if update["state"] == "current":
                        message = "Installed release matches origin/main."
                    elif update["state"] == "pending":
                        message = "Update pending. Press I to review and install the pinned commit."
                    else:
                        message = "Update status unknown; installed release identity could not be verified."
                except Exception as exc:
                    update = {"state": "unknown", "remote": None}
                    message = f"Update check failed; status unknown: {exc}"
            elif key in (ord("b"), ord("B")):
                if _confirm(screen, "Cold backup briefly stops active services.", "BACKUP"):
                    _progress(screen, "Creating private backup; services will be restored…")
                    backup = cold_backup(ROOT)
                    message = f"Verified private backup: {backup.name}"
                    last_refresh = 0
            elif key in (ord("i"), ord("I"), ord("u"), ord("U")):
                try:
                    update = update or check_updates(ROOT)
                    if not update.get("remote"):
                        _show_message(screen, "Check updates first to pin the exact origin/main commit.")
                    elif _confirm(screen, f"Install origin/main commit {update['remote'][:12]}?",
                                  "INSTALL-" + update["remote"][:12]):
                        reuse = key in (ord("u"), ord("U"))
                        _run_install_from_menu(screen, update["remote"], ROOT,
                                               reuse_existing_builds=reuse)
                        update = None
                        message = "Installer finished; review the selected release and status."
                        last_refresh = 0
                except Exception as exc:
                    message = f"Install failed: {exc}"
        except Exception as exc:
            message = f"Action failed: {exc}"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Manage this user's C-Crate services and private backups.")
    parser.add_argument("--status", action="store_true", help="print read-only status and exit")
    parser.add_argument("--install-commit", help="install this exact approved full origin/main commit")
    parser.add_argument("--reuse-existing-builds", action="store_true",
                        help="validate and seal existing private UI, label, and backend build outputs")
    args = parser.parse_args(argv)
    if args.status:
        try:
            print("\n".join(_status_lines(ROOT)))
        except Exception as exc:
            print(f"C-Crate status unavailable: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.install_commit:
        try:
            install_update(ROOT, commit=args.install_commit,
                           reuse_existing_builds=args.reuse_existing_builds)
            return 0
        except Exception as exc:
            print(f"C-Crate install failed: {exc}", file=sys.stderr)
            return 1
    curses.wrapper(_menu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
