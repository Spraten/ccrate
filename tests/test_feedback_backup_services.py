import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("backup_deployment", ROOT / "deploy" / "backup-deployment.py")
BACKUP = importlib.util.module_from_spec(SPEC)
try:
    import fcntl  # noqa: F401 - absent on Windows, where the backup lock is not exercised here.
except ModuleNotFoundError:
    sys.modules["fcntl"] = SimpleNamespace(flock=lambda *_args: None)
    try:
        SPEC.loader.exec_module(BACKUP)
    finally:
        del sys.modules["fcntl"]
else:
    SPEC.loader.exec_module(BACKUP)


class FakeSystemctl:
    def __init__(self, active):
        self.active = set(active)
        self.calls = []

    def run(self, args, check):
        self.calls.append(list(args))
        action, service = args[2], args[-1]
        if action == "is-active":
            return SimpleNamespace(returncode=0 if service in self.active else 3)
        if action == "stop":
            self.active.difference_update(args[3:])
        elif action == "start":
            self.active.add(service)
        return SimpleNamespace(returncode=0)


class FeedbackBackupQuiescenceTests(unittest.TestCase):
    def test_backup_quiesces_services_before_checkpoint_or_hash(self):
        source = (ROOT / "deploy" / "backup-deployment.py").read_text()
        main = source[source.index("def main():"):]
        self.assertLess(main.index("stop_backup_services(subprocess)"),
                        main.index("checkpoint_databases(root, databases)"))
        self.assertLess(main.index("checkpoint_databases(root, databases)"),
                        main.index("build_backup_manifest(root"))

    def test_gateway_stops_before_backends_and_only_prior_active_services_restart(self):
        gateway = "homebox-workshop-gateway.service"
        native = "homebox-native.service"
        companion = "homebox-companion.service"
        runner = FakeSystemctl({gateway, native})

        active = BACKUP.stop_backup_services(runner)

        self.assertEqual(runner.active, set())
        self.assertEqual(runner.calls[3], ["systemctl", "--user", "stop", gateway])
        self.assertEqual(runner.calls[4], ["systemctl", "--user", "stop", companion, native])
        BACKUP.resume_backup_services(runner, active)
        self.assertEqual(runner.active, {gateway, native})
        self.assertEqual(runner.calls[-2:], [
            ["systemctl", "--user", "start", native],
            ["systemctl", "--user", "start", gateway],
        ])


if __name__ == "__main__":
    unittest.main()
