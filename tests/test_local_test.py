import importlib.util
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.request
from unittest.mock import patch


REPO = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_test", REPO / "deploy" / "local-test.py")
local_test = None
if (REPO / "deploy" / "local-test.py").is_file() and SPEC is not None and SPEC.loader is not None:
    local_test = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(local_test)


class LocalTestBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(local_test, "deploy/local-test.py must implement the local test supervisor")

    def make_store(self, root):
        root.mkdir(exist_ok=True)
        return local_test.BootstrapStore(
            root,
            expected_root=root,
            mount_check=lambda _path: True,
        )

    def test_root_must_be_the_dedicated_mounted_data_path(self):
        with self.assertRaises(local_test.BootstrapError):
            local_test.validate_data_root("/tmp/ordinary", expected_root="/data", mount_check=lambda _p: True)
        with self.assertRaises(local_test.BootstrapError):
            local_test.validate_data_root("/data", expected_root="/data", mount_check=lambda _p: False)

    def test_existing_unrecognized_database_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "data"
            database = root / "work" / "baseline" / "data" / "homebox.db"
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
            store = self.make_store(root)
            with self.assertRaises(local_test.BootstrapError):
                store.prepare_volume()

    def test_damaged_database_blocks_recognized_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            store.ensure_account(
                lambda _account: None,
                lambda account: {"id": "user-1", "email": account["email"]},
            )
            database = store.database_path
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(b"not a sqlite database")
            with self.assertRaises(local_test.BootstrapError):
                store.validate_database()

    def test_incomplete_bootstrap_artifacts_block_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            store.state_path.parent.mkdir(parents=True, exist_ok=True)
            store.state_path.write_text(json.dumps({"format": 1, "status": "prepared"}), encoding="utf-8")
            with self.assertRaises(local_test.BootstrapError):
                store.validate_bootstrap_files()

    def test_uncertain_registration_is_reconciled_without_a_second_post(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            post_count = 0

            def register(_account):
                nonlocal post_count
                post_count += 1
                database = store.database_path
                database.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(database) as connection:
                    connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                raise OSError("response lost after request")

            with self.assertRaises(OSError):
                store.ensure_account(register, lambda _account: (_ for _ in ()).throw(OSError("not available")))
            self.assertEqual(store.load_state()["status"], "registration_started")

            def should_not_register(_account):
                nonlocal post_count
                post_count += 1
                raise AssertionError("registration must never be replayed")

            with self.assertRaises(local_test.BootstrapRecoveryRequired):
                store.ensure_account(
                    should_not_register,
                    lambda _account: (_ for _ in ()).throw(local_test.AuthenticationError("unknown result")),
                )
            self.assertEqual(post_count, 1)

    def test_completed_bootstrap_reuses_the_same_account(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            registrations = []
            account_ids = iter(("user-1", "user-1"))

            def register(account):
                registrations.append(account["email"])
                database = store.database_path
                database.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(database) as connection:
                    connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                    connection.execute("INSERT INTO users VALUES (?, ?)", ("user-1", account["email"]))

            def authenticate(account):
                return {"id": next(account_ids), "email": account["email"]}

            first = store.ensure_account(register, authenticate)
            second = store.ensure_account(lambda _account: self.fail("unexpected second registration"), authenticate)
            self.assertEqual(first["id"], "user-1")
            self.assertEqual(second["id"], "user-1")
            self.assertEqual(len(registrations), 1)

    def test_first_completed_bootstrap_configures_the_seed_user_as_group_manager(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            store.create_intent()
            store.database_path.parent.mkdir(parents=True)
            def register(account):
                with sqlite3.connect(store.database_path) as connection:
                    connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                    connection.execute("INSERT INTO users VALUES (?, ?)", ("user-1", account["email"]))
            identity = {"id": "user-1", "email": "local-admin@local.invalid", "defaultGroupId": "group-1",
                        "groupIds": ["group-1"]}
            store.ensure_account(register, lambda _account: identity)

            local_test.ensure_manager_config(store, identity)

            config_path = store.root / "work" / "ops" / "desktop-managers.json"
            self.assertEqual(json.loads(config_path.read_text()), {
                "owner_id": "user-1", "managers": [{"user_id": "user-1", "group_id": "group-1"}]
            })

    def test_manager_config_restart_preserves_existing_grants_and_refuses_missing_confirmed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(pathlib.Path(temporary) / "data")
            store.prepare_volume()
            store.create_intent()
            store.database_path.parent.mkdir(parents=True)
            def register(account):
                with sqlite3.connect(store.database_path) as connection:
                    connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                    connection.execute("INSERT INTO users VALUES (?, ?)", ("user-1", account["email"]))
            identity = {"id": "user-1", "email": "local-admin@local.invalid", "defaultGroupId": "group-1",
                        "groupIds": ["group-1"]}
            store.ensure_account(register, lambda _account: identity)
            local_test.ensure_manager_config(store, identity)
            path = store.root / "work" / "ops" / "desktop-managers.json"
            extra = {"owner_id": "user-1", "managers": [
                {"user_id": "user-1", "group_id": "group-1"}, {"user_id": "other", "group_id": "group-1"}
            ]}
            path.write_text(json.dumps(extra))
            local_test.ensure_manager_config(store, identity)
            self.assertEqual(json.loads(path.read_text()), extra)
            path.unlink()
            with self.assertRaises(local_test.BootstrapError):
                local_test.ensure_manager_config(store, identity)

    def test_manager_config_migration_rejects_foreign_or_corrupt_existing_file(self):
        for contents in (
            json.dumps({"owner_id": "other", "managers": [{"user_id": "other", "group_id": "group-1"}]}),
            "{broken",
        ):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as temporary:
                store = self.make_store(pathlib.Path(temporary) / "data")
                store.prepare_volume()
                store.create_intent()
                store.database_path.parent.mkdir(parents=True)
                def register(account):
                    with sqlite3.connect(store.database_path) as connection:
                        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                        connection.execute("INSERT INTO users VALUES (?, ?)", ("user-1", account["email"]))
                identity = {"id": "user-1", "email": "local-admin@local.invalid", "defaultGroupId": "group-1",
                            "groupIds": ["group-1"]}
                store.ensure_account(register, lambda _account: identity)
                path = store.root / "work" / "ops" / "desktop-managers.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
                with self.assertRaises(local_test.BootstrapError):
                    local_test.ensure_manager_config(store, identity)

    def test_shutdown_terminates_and_reaps_child_processes(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        local_test.stop_children([child], grace_seconds=0.2)
        self.assertIsNotNone(child.poll())

    def test_label_builder_accepts_a_generated_toolchain_root(self):
        result = subprocess.run(
            [sys.executable, str(REPO / "deploy" / "build-label-ui.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--toolchain-root", result.stdout)

    def test_renderer_child_keeps_its_code_and_asset_roots(self):
        spec = importlib.util.spec_from_file_location("local_test_label_render", REPO / "ops" / "label_render.py")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)

        class Completed:
            returncode = 0

            def communicate(self, *_args, **_kwargs):
                return b'{"results":[],"sheet_result":null}', b""

        environment = {
            "WORKSHOP_ROOT": "/data",
            "WORKSHOP_CODE_ROOT": "/app",
            "WORKSHOP_LABEL_ASSET_ROOT": "/app/label-ui",
            "WORKSHOP_NODE": "/usr/bin/node",
        }
        with patch.dict(os.environ, environment), patch.object(renderer.subprocess, "Popen", return_value=Completed()) as popen:
            renderer._run({"asset_root": "/app/label-ui"}, 2)
        child_env = popen.call_args.kwargs["env"]
        self.assertEqual(child_env.get("WORKSHOP_CODE_ROOT"), "/app")
        self.assertEqual(child_env.get("WORKSHOP_LABEL_ASSET_ROOT"), "/app/label-ui")

    def test_local_backup_rejects_before_creating_journal_state(self):
        fake_ledger = types.ModuleType("ledger")
        fake_ledger.uuid = lambda value: value
        fake_ledger.Conflict = RuntimeError
        fake_hardware = types.ModuleType("hardware")
        fake_hardware.reconnect = lambda *_args: self.fail("local status must not inspect host hardware")
        fake_hardware.camera_status = lambda: self.fail("local status must not inspect host hardware")
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"WORKSHOP_LOCAL_TEST": "1", "WORKSHOP_ROOT": temporary},
        ), patch.dict(sys.modules, {"ledger": fake_ledger, "hardware": fake_hardware}):
            (pathlib.Path(temporary) / "work").mkdir()
            spec = importlib.util.spec_from_file_location(
                "local_test_system_status", REPO / "ops" / "system_status.py"
            )
            status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(status)
            with self.assertRaisesRegex(ValueError, "local test"):
                status.start_backup("request-1")
            self.assertFalse(status.STATE.exists())

    def test_local_status_reports_read_only_container_health_without_systemd(self):
        fake_ledger = types.ModuleType("ledger")
        fake_ledger.uuid = lambda value: value
        fake_ledger.Conflict = RuntimeError
        fake_hardware = types.ModuleType("hardware")
        fake_hardware.reconnect = lambda *_args: self.fail("local status must not inspect host hardware")
        fake_hardware.camera_status = lambda: self.fail("local status must not inspect host hardware")
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"WORKSHOP_LOCAL_TEST": "1", "WORKSHOP_ROOT": temporary},
        ), patch.dict(sys.modules, {"ledger": fake_ledger, "hardware": fake_hardware}):
            spec = importlib.util.spec_from_file_location(
                "local_test_system_status", REPO / "ops" / "system_status.py"
            )
            status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(status)
            response = types.SimpleNamespace(status=200)
            with patch.object(urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value = response
                try:
                    result = status.status()
                except Exception as error:
                    self.fail(f"local status must not depend on systemd or host hardware: {error}")
            self.assertEqual(result["homebox"], "active")
            self.assertEqual(result["companion"], "active")
            self.assertEqual(result["printer"], "unavailable in local test")


if __name__ == "__main__":
    unittest.main()
