import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from deploy import ccrate_manager as manager


class ManagerTests(unittest.TestCase):
    def statuses(self, active):
        return {
            name: {"active": name in active, "state": "active" if name in active else "inactive",
                   "pid": str(100 + index) if name in active else "0", "owned": True}
            for index, name in enumerate(manager.START_ORDER)
        }

    def candidate(self, root):
        old = root / "work/application-releases/old"
        new = root / "work/application-releases/new"
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        (root / "work/application-current").symlink_to(old)
        for path in (new / "kiosk/index.html", new / "public/index.html",
                     new / "public/ccrate-release.json"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        return old, new

    def run_install(self, root, old, new, *, statuses, systemctl=None, reuse=False):
        commit = "a" * 40
        events = []
        class Response:
            status = 200
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return self.body
        class Opener:
            def open(self, url, timeout=0):
                expected = {
                    "http://127.0.0.1:17747/api/v1/status": b"{}",
                    "http://127.0.0.1:17749/": (new / "kiosk/index.html").read_bytes(),
                    "http://127.0.0.1:17745/": (new / "public/index.html").read_bytes(),
                    "http://127.0.0.1:17745/ccrate-release.json":
                        (new / "public/ccrate-release.json").read_bytes(),
                }
                return Response(expected[url])
        def record(*args):
            events.append(args)
            if systemctl:
                systemctl(*args)
        with mock.patch("deploy.release_bundle._transaction_lock", return_value=nullcontext()), \
             mock.patch("deploy.release_bundle.validate_bundle", return_value={}), \
             mock.patch.object(manager, "_selected_release", return_value=(old, {})), \
             mock.patch.object(manager, "get_service_statuses", side_effect=statuses), \
             mock.patch.object(manager, "_systemctl", side_effect=record), \
             mock.patch.object(manager.urllib.request, "build_opener", return_value=Opener()), \
             mock.patch("deploy.ccrate_update._prepare_candidate_locked",
                        return_value={"candidate": new}) as prepare:
            result = manager.install_update(root, commit=commit, reuse_existing_builds=reuse)
        return result, events, prepare

    def test_install_build_activates_atomically_and_preserves_service_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            old, new = self.candidate(root)
            result, events, _ = self.run_install(
                root, old, new,
                statuses=[self.statuses(manager.START_ORDER), self.statuses(()),
                          self.statuses(manager.START_ORDER)])
            self.assertEqual(result, new)
            self.assertEqual((root / "work/application-current").resolve(), new)
            self.assertEqual(events, [
                ("stop", manager.SERVICES["gateway"]),
                ("stop", manager.SERVICES["companion"]),
                ("stop", manager.SERVICES["native"]),
                ("start", manager.SERVICES["native"]),
                ("start", manager.SERVICES["companion"]),
                ("start", manager.SERVICES["gateway"]),
            ])
            status = manager._update_status(root)
            self.assertEqual(status["outcome"], "success")

    def test_reuse_path_passes_reuse_flag_without_running_source_builders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            old, new = self.candidate(root)
            with mock.patch("deploy.release_bundle._transaction_lock", return_value=nullcontext()), \
                 mock.patch("deploy.release_bundle.validate_bundle", return_value={}), \
                 mock.patch.object(manager, "_selected_release", return_value=(old, {})), \
                 mock.patch.object(manager, "get_service_statuses", side_effect=[
                     self.statuses(()), self.statuses(()), self.statuses(())]), \
                 mock.patch("deploy.ccrate_update._git", return_value="b" * 40), \
                 mock.patch("deploy.ccrate_update._build_and_stage",
                            return_value={"candidate": new}) as build, \
                 mock.patch("deploy.ccrate_update._prepare_candidate_locked") as prepare:
                def prepare_candidate(_root, *, builder, **_kwargs):
                    builder(_root, root / "source-stage", "a" * 40)
                    return {"candidate": new}
                prepare.side_effect = prepare_candidate
                manager.install_update(root, commit="a" * 40, reuse_existing_builds=True)
                build.assert_called_once()
                self.assertTrue(build.call_args.kwargs["reuse_existing"])

    def test_build_failure_does_not_stop_services(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            old, new = self.candidate(root)
            with mock.patch("deploy.ccrate_update._prepare_candidate_locked",
                            side_effect=RuntimeError("build failed")), \
                 mock.patch.object(manager, "_systemctl") as systemctl:
                with self.assertRaisesRegex(RuntimeError, "build failed"):
                    manager.install_update(root, commit="a" * 40)
            systemctl.assert_not_called()
            self.assertEqual((root / "work/application-current").resolve(), old)
            self.assertEqual(manager._update_status(root)["outcome"], "failed")

    def test_restart_failure_keeps_truthful_selected_candidate_and_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            old, new = self.candidate(root)
            def fail_start(*args):
                if args[0] == "start" and args[1] == manager.SERVICES["companion"]:
                    raise RuntimeError("start failed")
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                self.run_install(root, old, new,
                    statuses=[self.statuses(manager.START_ORDER), self.statuses(() )],
                    systemctl=fail_start)
            self.assertEqual((root / "work/application-current").resolve(), new)
            status = manager._update_status(root)
            self.assertEqual(status["stage"], "failed-after-selection")
            self.assertEqual(status["outcome"], "failed")

    def test_status_does_not_leave_a_dead_installer_as_running(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            path = root / "work/manager-update-status.json"
            path.write_text(json.dumps({"schema": 1, "pid": 99999999,
                                        "outcome": "running", "stage": "building"}))
            path.chmod(0o600)
            status = manager._update_status(root)
            self.assertEqual(status["outcome"], "abandoned")
            self.assertEqual(status["stage"], "abandoned")


if __name__ == "__main__":
    unittest.main()
