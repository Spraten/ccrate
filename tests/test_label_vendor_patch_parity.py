"""Ensure the cumulative vendor patch reverses and rebuilds the maintained tree."""
import hashlib
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "label-ui/vendor/print-design-pro/src"
PATCH = ROOT / "label-ui/patches/0002-label-editor-controls.patch"
PATCH_DIR = "label-ui/vendor/print-design-pro/src"


def tree_hash(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class LabelVendorPatchParityTests(unittest.TestCase):
    def test_cumulative_patch_reverses_and_recreates_vendor_source(self):
        self.assertTrue(VENDOR.is_dir(), "vendored editor source is required")
        self.assertTrue(PATCH.is_file(), "cumulative vendor patch is required")
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            checkout = pathlib.Path(temporary)
            target = checkout / PATCH_DIR
            target.parent.mkdir(parents=True)
            shutil.copytree(VENDOR, target)
            before = tree_hash(target)
            args = ["git", "apply", "-p4", f"--directory={PATCH_DIR}"]
            subprocess.run(args + ["--reverse", "--check", str(PATCH)], cwd=checkout, check=True)
            subprocess.run(args + ["--reverse", str(PATCH)], cwd=checkout, check=True)
            subprocess.run(args + ["--check", str(PATCH)], cwd=checkout, check=True)
            subprocess.run(args + [str(PATCH)], cwd=checkout, check=True)
            self.assertEqual(tree_hash(target), before)


if __name__ == "__main__":
    unittest.main()
