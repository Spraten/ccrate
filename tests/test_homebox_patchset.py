import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from deploy.homebox_patchset import apply_patchset, load_patchset, materialize


ROOT = pathlib.Path(__file__).resolve().parents[1]


class HomeboxPatchsetTests(unittest.TestCase):
    def test_camera_error_mapping_distinguishes_missing_device(self):
        patch = (ROOT / "deploy/homebox-patches/0020-Fix-item-camera-save-and-OCR-races.patch").read_text()

        self.assertIn('name === "NotFoundError" || name === "DevicesNotFoundError" ? "unavailable" : "permission_error"', patch)
        self.assertIn('cameraErrorMessageKey(error)', patch)
        self.assertIn('maps missing devices to unavailable and permission failures', patch)

    def test_regular_upload_keeps_camera_attachments_after_save(self):
        patch = (ROOT / "deploy/homebox-patches/0020-Fix-item-camera-save-and-OCR-races.patch").read_text()
        upload_hunk = patch.split("@@ -500,18 +534,18 @@", 1)[1].split("@@ -747,7 +781,7 @@", 1)[0]

        self.assertLess(upload_hunk.index("+    item.value.attachments = data.attachments"), upload_hunk.index("await saveItem(false)"))

    def test_docker_build_stage_copies_homebox_patchset_inputs(self):
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertIn("COPY deploy/homebox_patchset.py deploy/homebox-patchset.json /src/deploy/", dockerfile)
        self.assertIn("COPY deploy/homebox-patches/ /src/deploy/homebox-patches/", dockerfile)

    def test_manifest_lists_ordered_patches_from_public_base(self):
        base, patches, digest = load_patchset(ROOT)

        self.assertEqual(base, "e01dd737238a3fa7e1a6454b37de6c6fc88c86e4")
        self.assertEqual(len(patches), 25)
        self.assertTrue(all(path.is_file() for path in patches))
        self.assertEqual(len(digest), 64)

    def test_patch_series_applies_to_clean_source_in_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = root / "source"
            patch_dir = root / "patches"
            source.mkdir()
            patch_dir.mkdir()
            (source / "value.txt").write_text("base\n")
            first = patch_dir / "0001-first.patch"
            first.write_text(
                "--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-base\n+first\n"
            )
            second = patch_dir / "0002-second.patch"
            second.write_text(
                "--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-first\n+second\n"
            )

            apply_patchset(source, [first, second])

            self.assertEqual((source / "value.txt").read_text(), "second\n")

    def test_snapshot_digest_uses_portable_case_sensitive_path_order(self):
        from deploy.homebox_patchset import source_tree_digest
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = pathlib.Path(temporary)
            (root / "backend").mkdir()
            (root / "README").write_bytes(b"readme")
            (root / "backend" / "value.go").write_bytes(b"source")
            digest = hashlib.sha256()
            for relative, content in (("README", b"readme"), ("backend/value.go", b"source")):
                digest.update(relative.encode("utf-8") + b"\0" + len(content).to_bytes(8, "big") + content)
            self.assertEqual(source_tree_digest(root), digest.hexdigest())

    def test_manifest_rejects_patch_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "deploy" / "homebox-patches").mkdir(parents=True)
            (root / "deploy" / "homebox-patchset.json").write_text(
                json.dumps({"base": "a" * 40, "patches": ["../outside.patch"]})
            )

            with self.assertRaisesRegex(ValueError, "plain filenames"):
                load_patchset(root)

    def _write_patchset(self, root, base, patch_body):
        patch_dir = root / "deploy" / "homebox-patches"
        patch_dir.mkdir(parents=True)
        (root / "deploy" / "homebox-patchset.json").write_text(
            json.dumps({"base": base, "patches": ["0001-fixture.patch"]})
        )
        (patch_dir / "0001-fixture.patch").write_text(patch_body)

    def test_materialize_rebuilds_instead_of_reusing_modified_cache(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = pathlib.Path(temporary)
            upstream = root / "upstream" / "homebox"
            (upstream / "frontend").mkdir(parents=True)
            source_file = upstream / "frontend" / "package.json"
            source_file.write_text("base\n")
            subprocess.run(["git", "init", "-q", str(upstream)], check=True)
            subprocess.run(["git", "-C", str(upstream), "config", "user.email", "fixture@example.test"], check=True)
            subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Fixture"], check=True)
            subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
            subprocess.run(["git", "-C", str(upstream), "commit", "-qm", "fixture"], check=True)
            base = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
            self._write_patchset(root, base, "--- a/frontend/package.json\n+++ b/frontend/package.json\n@@ -1 +1 @@\n-base\n+patched\n")

            destination = materialize(root)
            with mock.patch.object(pathlib.Path, "replace", side_effect=AssertionError("intact cache should not be replaced")):
                self.assertEqual(materialize(root), destination)
            (destination / "frontend" / "package.json").write_text("corrupted\n")
            rebuilt = materialize(root)

            self.assertEqual(rebuilt, destination)
            self.assertEqual((rebuilt / "frontend" / "package.json").read_text(), "patched\n")

    def test_materialize_uses_staged_snapshot_when_source_has_no_git_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = pathlib.Path(temporary)
            upstream = root / "upstream" / "homebox"
            (upstream / "frontend").mkdir(parents=True)
            (upstream / "frontend" / "package.json").write_text("base\n")
            base = "e" * 40
            from deploy.homebox_patchset import source_tree_digest
            (upstream / ".ccrate-homebox-source.json").write_text(json.dumps({"commit": base, "tree_sha256": source_tree_digest(upstream)}))
            self._write_patchset(root, base, "--- a/frontend/package.json\n+++ b/frontend/package.json\n@@ -1 +1 @@\n-base\n+patched\n")

            destination = materialize(root)

            self.assertEqual((destination / "frontend" / "package.json").read_text(), "patched\n")
            self.assertFalse((destination / ".ccrate-homebox-source.json").exists())

            (upstream / "frontend" / "package.json").write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "does not match its commit marker"):
                materialize(root)


if __name__ == "__main__":
    unittest.main()
