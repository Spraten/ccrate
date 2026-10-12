import importlib.util
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('verify_workshop_rooms', ROOT / 'deploy/verify-workshop-rooms.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class CanonicalBuildReceiptTests(unittest.TestCase):
    def test_runtime_closure_reads_nested_source_and_excludes_private_cache(self):
        paths = {path.relative_to(ROOT).as_posix() for path in verifier.tracked_public(ROOT)}
        self.assertIn('kiosk/workshop-ui.js', paths)
        self.assertIn('ops/workshop.py', paths)
        self.assertIn('label-ui/src/starter-documents.json', paths)
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp)
            for name in ('ops/workshop.py', 'kiosk/workshop-ui.js', 'kiosk/private/secret.js',
                         'kiosk/cache/generated.js', 'label-ui/src/starter-documents.json'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            included = {path.relative_to(source).as_posix() for path in verifier.tracked_public(source)}
            self.assertEqual(included, {'ops/workshop.py', 'kiosk/workshop-ui.js',
                                        'label-ui/src/starter-documents.json'})

    def test_runtime_closure_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / 'source'
            (source / 'ops').mkdir(parents=True)
            outside = pathlib.Path(temp) / 'outside.py'
            outside.write_text('private')
            (source / 'ops/escape.py').symlink_to(outside)
            with self.assertRaises(ValueError):
                verifier.tracked_public(source)
            (source / 'ops/escape.py').unlink()
            (source / 'ops/workshop.py').write_text('fixture')
            (source / 'kiosk').mkdir()
            (source / 'label-ui/src').mkdir(parents=True)
            (source / 'label-ui/src/starter-documents.json').symlink_to(outside)
            with self.assertRaises(ValueError):
                verifier.tracked_public(source)

    def test_current_companion_anchors_are_bound_to_fixture_roots(self):
        self.assertTrue(hasattr(verifier, 'rewrite_companion_for_fixture'))
        source = (ROOT / 'deploy/kiosk-server.py').read_text()
        candidate = ROOT / 'fixture-candidate'
        data_root = pathlib.Path('/tmp/workshop-fixture-owned')
        rewritten = verifier.rewrite_companion_for_fixture(
            source, candidate, data_root, 'http://127.0.0.1:45123', 'http://127.0.0.1:45124',
            ROOT / 'program-files/runtime/hardware/python')
        compile(rewritten, '<rooms-companion-fixture>', 'exec')
        self.assertIn(f"CODE_ROOT=pathlib.Path({str(candidate)!r}).resolve(strict=True)", rewritten)
        self.assertIn(f"ROOT=pathlib.Path({str(data_root)!r}).resolve(strict=True)", rewritten)
        self.assertIn("BASE='http://127.0.0.1:45123'", rewritten)
        self.assertIn("self.headers.get('Origin') != 'http://127.0.0.1:45124'", rewritten)
        self.assertIn("sys.path.insert(0,'" + str(candidate / 'ops') + "')", rewritten)
        self.assertIn("_fixture_refuse(*_a,**_k)", rewritten)
        self.assertIn('printer_probe=_fixture_refuse', rewritten)
        self.assertIn('_fixture_expected=pathlib.Path(', rewritten)
        self.assertIn('not pathlib.Path(_m.__file__).resolve(strict=True).is_relative_to(_fixture_expected)', rewritten)
        self.assertNotIn("ThreadingHTTPServer((_fixture_host,_fixture_port),Handler)", rewritten)
        self.assertNotIn("0.0.0.0',17749", rewritten)

    def test_accepted_receipt_validates_its_embedded_source_and_output_manifests(self):
        receipt = ROOT / 'work/queue-coordinator/shelf-checks-canonical-build-receipt.json'
        public = ROOT / 'work/homebox-ui-build/.output/public'
        provenance, _, _, outputs = verifier.canonical_build_provenance(ROOT, public, receipt)
        self.assertEqual(provenance, 'accepted-canonical-build')
        self.assertEqual(len(outputs), 181)

    def _small_source_copy(self, parent):
        source = parent / 'source'
        receipt = ROOT / 'work/queue-coordinator/shelf-checks-canonical-build-receipt.json'
        names = ['deploy/build-homebox-ui.py', 'homebox-ui/pnpm-lock.yaml',
                 'homebox-ui/upstream-typecheck.json', 'kiosk/member-avatar.js', 'kiosk/label-editor.js']
        for name in names:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        shutil.copytree(ROOT / 'homebox-ui/overlay', source / 'homebox-ui/overlay')
        target = source / 'work/queue-coordinator/shelf-checks-canonical-build-receipt.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(receipt, target)
        return source, target

    def test_changed_source_input_is_rejected(self):
        public = ROOT / 'work/homebox-ui-build/.output/public'
        with tempfile.TemporaryDirectory() as temp:
            source, receipt = self._small_source_copy(pathlib.Path(temp))
            with (source / 'kiosk/member-avatar.js').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaises(ValueError):
                verifier.canonical_build_provenance(source, public, receipt)

    def test_symlinked_source_input_is_rejected(self):
        public = ROOT / 'work/homebox-ui-build/.output/public'
        with tempfile.TemporaryDirectory() as temp:
            source, receipt = self._small_source_copy(pathlib.Path(temp))
            changed = source / 'kiosk/member-avatar.js'
            changed.unlink()
            changed.symlink_to(source / 'kiosk/label-editor.js')
            with self.assertRaises(ValueError):
                verifier.canonical_build_provenance(source, public, receipt)

    def test_changed_output_and_symlink_are_rejected(self):
        original = ROOT / 'work/homebox-ui-build/.output/public'
        receipt = ROOT / 'work/queue-coordinator/shelf-checks-canonical-build-receipt.json'
        with tempfile.TemporaryDirectory() as temp:
            source, local_receipt = self._small_source_copy(pathlib.Path(temp))
            changed = pathlib.Path(temp) / 'changed-public'
            shutil.copytree(original, changed)
            (changed / 'index.html').chmod(0o644)
            with (changed / 'index.html').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaises(ValueError):
                verifier.canonical_build_provenance(source, changed, local_receipt)
            linked = pathlib.Path(temp) / 'linked-public'
            shutil.copytree(original, linked)
            linked.chmod(0o755)
            (linked / 'escape').symlink_to(original / 'index.html')
            with self.assertRaises(ValueError):
                verifier.canonical_build_provenance(source, linked, local_receipt)


if __name__ == '__main__':
    unittest.main()
