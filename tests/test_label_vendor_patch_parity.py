"""Ensure the cumulative vendor patch reverses and rebuilds the maintained tree."""
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "label-ui/vendor/print-design-pro/src"
OFFLINE_PATCH = ROOT / "label-ui/patches/0001-offline-fonts.patch"
PATCH = ROOT / "label-ui/patches/0002-label-editor-controls.patch"
PATCH_DIR = "label-ui/vendor/print-design-pro/src"


def tree_hash(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class LabelVendorPatchParityTests(unittest.TestCase):
    def test_offline_fonts_patch_hunk_counts_match_their_contents(self):
        lines = OFFLINE_PATCH.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                continue
            expected_old = int(match.group(2) or 1)
            expected_new = int(match.group(4) or 1)
            actual_old = actual_new = 0
            for item in lines[index + 1:]:
                if item.startswith(("@@ ", "diff --git ")):
                    break
                if item.startswith(" "):
                    actual_old += 1
                    actual_new += 1
                elif item.startswith("+") and not item.startswith("+++"):
                    actual_new += 1
                elif item.startswith("-") and not item.startswith("---"):
                    actual_old += 1
            self.assertEqual((actual_old, actual_new), (expected_old, expected_new), f"patch hunk at line {index + 1}")

    def test_vendor_patches_reverse_and_recreate_vendor_source(self):
        self.assertTrue(VENDOR.is_dir(), "vendored editor source is required")
        self.assertTrue(OFFLINE_PATCH.is_file(), "offline fonts vendor patch is required")
        self.assertTrue(PATCH.is_file(), "cumulative vendor patch is required")
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            checkout = pathlib.Path(temporary)
            target = checkout / PATCH_DIR
            target.parent.mkdir(parents=True)
            shutil.copytree(VENDOR, target)
            before = tree_hash(target)
            args = ["git", "apply", "-p4", f"--directory={PATCH_DIR}"]
            env = os.environ.copy()
            env["GIT_CEILING_DIRECTORIES"] = str(ROOT)
            patches = [OFFLINE_PATCH, PATCH]
            for patch in reversed(patches):
                subprocess.run(args + ["--unidiff-zero", "--reverse", "--check", str(patch)], cwd=checkout, env=env, check=True)
                subprocess.run(args + ["--unidiff-zero", "--reverse", str(patch)], cwd=checkout, env=env, check=True)
            self.assertNotEqual(tree_hash(target), before, "reversing the vendor patches must change the copied source tree")
            for patch in patches:
                subprocess.run(args + ["--unidiff-zero", "--check", str(patch)], cwd=checkout, env=env, check=True)
                subprocess.run(args + ["--unidiff-zero", str(patch)], cwd=checkout, env=env, check=True)
            after = tree_hash(target)
            differences = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
            self.assertEqual(differences, [], f"vendor files differ after patch round-trip: {differences}")


if __name__ == "__main__":
    unittest.main()
