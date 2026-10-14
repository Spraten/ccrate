import importlib.util
import json
import pathlib
import sqlite3
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location('fixture_' + name.replace('-', '_'), ROOT/'deploy'/name)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class LabelReleaseHelperTests(unittest.TestCase):
    def test_disposable_archive_includes_checkpointed_label_db_and_matching_public_editor(self):
        backup = load_script('backup-deployment.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root/'work/ops').mkdir(parents=True)
            db = root/'work/ops/label-layouts.db'
            connection = sqlite3.connect(db)
            try:
                connection.execute('create table templates(id text primary key)')
                connection.execute("insert into templates values ('fixture-template')")
                connection.execute('create table print_intents(id text primary key,status text not null)')
                connection.executemany('insert into print_intents values (?,?)', [('intent-open','unresolved'),('intent-done','completed')])
                connection.commit()
            finally: connection.close()
            (root/'label-ui/src').mkdir(parents=True)
            (root/'label-ui/src/editor.ts').write_text('frozen editor source')
            (root/'work/label-ui-build').mkdir(parents=True)
            (root/'work/label-ui-build/manifest.json').write_text('{"runtime_assets":{}}\n')
            (root/'work/label-ui-build/editor.html').write_text('built editor')
            members = ['work/ops/label-layouts.db', 'label-ui/src', 'work/label-ui-build']
            databases = ['work/ops/label-layouts.db']
            backup.checkpoint_databases(root, databases)
            manifest = backup.build_backup_manifest(root, created_at='fixture', commit='source-pin', homebox_pin='native-pin', members=members, databases=databases)
            target = backup.create_archive(root, root/'fixture.tar.gz', members, manifest)
            with tarfile.open(target) as archive:
                names = set(archive.getnames())
                archived_manifest = json.load(archive.extractfile('deployment-manifest.json'))
                archived_db = archive.extractfile('work/ops/label-layouts.db').read()
                self.assertIn('label-ui/src/editor.ts', names)
                self.assertIn('work/label-ui-build/manifest.json', names)
                self.assertEqual(archived_manifest['sha256']['work/ops/label-layouts.db'], __import__('hashlib').sha256(archived_db).hexdigest())
                copy = sqlite3.connect(':memory:')
                try:
                    copy.deserialize(archived_db)
                    self.assertEqual(copy.execute('select id from templates').fetchone()[0], 'fixture-template')
                    self.assertEqual(copy.execute('select id,status from print_intents order by id').fetchall(), [('intent-done','completed'),('intent-open','unresolved')])
                finally: copy.close()

    def test_runtime_manifest_and_installer_helpers_accept_explicit_fixtures(self):
        runtime = load_script('runtime-manifest.py')
        installer = load_script('install-shared-tools.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            result = runtime.build_runtime_manifest(root, run=lambda args, **kwargs: 'fixture\n', python_version='fixture-python', sqlite_version='fixture-sqlite', platform_name='fixture-platform')
            self.assertEqual(result['homebox_pin'], 'fixture')
            self.assertEqual(result['python'], 'fixture-python')
            service_source, target, snapshot = root/'source', root/'services', root/'snapshot'
            service_source.mkdir(); target.mkdir()
            for name in installer.SERVICE_NAMES:
                (service_source/name).write_text('new '+name)
            (target/installer.SERVICE_NAMES[0]).write_text('old service')
            previous = installer.snapshot_services(service_source, target, snapshot)
            installer.install_service_files(service_source, target)
            self.assertEqual((target/installer.SERVICE_NAMES[0]).read_text(), 'new '+installer.SERVICE_NAMES[0])
            installer.restore_services(target, previous)
            self.assertEqual((target/installer.SERVICE_NAMES[0]).read_text(), 'old service')
            self.assertFalse((target/installer.SERVICE_NAMES[1]).exists())

    def test_staging_helper_links_complete_public_inputs_by_hash(self):
        stage = load_script('stage-label-release.py')
        import hashlib, subprocess
        with tempfile.TemporaryDirectory() as temporary:
            base=pathlib.Path(temporary); public=base/'public'; source=base/'source'; output=source/'work/candidate'
            for name in ('homebox-backend','ops','kiosk','work/hardware/python','homebox-ui/overlay','deploy/homebox-patches','label-ui/src','label-ui/vendor/print-design-pro','label-ui/public/fonts','label-ui/public/licenses','label-ui/patches','work/label-ui-build','work/homebox-ui-build/.output/public','work/homebox-ui-current','work/homebox-backend-build','work/homebox-bin','work/supvan-cups/target/release/examples','docs',):
                (source/name).mkdir(parents=True,exist_ok=True)
            for name in ('upstream/homebox','work/homebox-bin','work/supvan-cups/target/release/examples','work/hardware/python'):(public/name).mkdir(parents=True,exist_ok=True)
            native=public/'upstream/homebox'; subprocess.run(['git','init','-q',str(native)],check=True)
            subprocess.run(['git','-C',str(native),'config','user.email','fixture@example.test'],check=True);subprocess.run(['git','-C',str(native),'config','user.name','Fixture'],check=True)
            (native/'README').write_text('pinned native\n');subprocess.run(['git','-C',str(native),'add','.'],check=True);subprocess.run(['git','-C',str(native),'commit','-qm','fixture'],check=True)
            pin=subprocess.check_output(['git','-C',str(native),'rev-parse','HEAD'],text=True).strip()
            (native/'README').write_text('dirty working tree must not ship\n')
            def put(root,relative,body):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body);return path
            for name in ('README.md','pnpm-lock.yaml','upstream-typecheck.json'):
                put(source,'homebox-ui/'+name,name)
            package=source/'label-ui'
            for name in ('package.json','pnpm-lock.yaml','vite.config.ts','editor.html','render.html','vendor-manifest.json'):
                put(package,name,name)
            put(package,'src/editor.ts','source editor');put(package,'public/fonts/DejaVuSans.ttf','font');put(package,'public/fonts/DejaVu-Fonts-Copyright.txt','font license');put(package,'patches/0001-offline-fonts.patch','patch');put(package,'vendor/print-design-pro/LICENSE','upstream license');put(package,'vendor/print-design-pro/src/index.ts','vendor source')
            for name in ('kiosk-server.py','workshop-gateway.py','run-homebox.py','backup-deployment.py','build-homebox-ui.py','build-homebox-backend.py','homebox_patchset.py','homebox-patchset.json','build-label-ui.py','install-shared-tools.py','runtime-manifest.py','stage-label-release.py','verify-label-layouts.py','homebox-native.service','homebox-companion.service','homebox-workshop-gateway.service','Equipment Terminal.desktop','Open-Workshop.ps1'):
                put(source,'deploy/'+name,name)
            put(source,'deploy/homebox-patchset.json',json.dumps({'base':pin,'patches':['0001-fixture.patch']})+'\n')
            put(source,'deploy/homebox-patches/0001-fixture.patch','--- a/README\n+++ b/README\n@@ -1 +1 @@\n-pinned native\n+patched native\n')
            put(source,'work/homebox-ui-build/.output/public/index.html','selected static frontend')
            put(source,'work/homebox-ui-current/index.html','selected static frontend')
            backend=put(source,'work/homebox-backend-build/homebox','new patched backend')
            for name in ('LABEL_LAYOUTS.md','LABEL_LAYOUTS_TASK5_REPORT.md','runtime-manifest.json','DECISIONS.md'):
                put(source,'docs/'+name,name)
            for tree in ('homebox-backend','ops','kiosk','work/hardware/python','homebox-ui/overlay','label-ui/src','label-ui/vendor','label-ui/public','label-ui/patches'):
                put(source,tree+'/source.txt',tree)
            put(source,'work/homebox-ui-build/.output/public/index.html','selected static frontend')
            from deploy.homebox_patchset import load_patchset, source_tree_digest
            receipt={'upstream':pin,'patchset_sha256':load_patchset(source)[2],'backend_overlay_sha256':source_tree_digest(source/'homebox-backend'),'backend_builder_sha256':hashlib.sha256((source/'deploy/build-homebox-backend.py').read_bytes()).hexdigest(),'frontend_sha256':source_tree_digest(source/'work/homebox-ui-current'),'binary_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),'version':'0.26.2-caci.2-shortcodes'}
            put(source,'work/homebox-backend-build/build-receipt.json',json.dumps(receipt)+'\n')
            for rel in ('work/homebox-bin/homebox','work/supvan-cups/target/release/examples/kiosk-label'):
                put(source,rel,'local placeholder')
                target=public/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('accepted binary')
            editor=source/'work/label-ui-build';put(editor,'editor.html','built editor')
            runtime_assets={'editor.html':hashlib.sha256((editor/'editor.html').read_bytes()).hexdigest()}
            build_inputs={}
            for item in ('package.json','pnpm-lock.yaml','vite.config.ts','editor.html','render.html','vendor-manifest.json','src','public','patches'):
                selected=package/item
                files=[selected] if selected.is_file() else sorted(path for path in selected.rglob('*') if path.is_file())
                build_inputs.update({path.relative_to(package).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
            def treehash(root):return hashlib.sha256(b''.join(p.relative_to(root).as_posix().encode()+b'\0'+p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file())).hexdigest()
            manifest={'upstream_commit':'eb118cc05b169c554066d823c44dc179aa3b96bb','build_inputs':build_inputs,'runtime_assets':runtime_assets,'dependencies_lock_sha256':stage.sha(package/'pnpm-lock.yaml'),'patch_sha256':stage.sha(package/'patches/0001-offline-fonts.patch'),'font_sha256':stage.sha(package/'public/fonts/DejaVuSans.ttf'),'font_license_sha256':stage.sha(package/'public/fonts/DejaVu-Fonts-Copyright.txt'),'upstream_license_sha256':stage.sha(package/'vendor/print-design-pro/LICENSE'),'vendor_source_sha256':treehash(package/'vendor/print-design-pro')}
            put(editor,'manifest.json',json.dumps(manifest)+'\n')
            put(editor,'manifest.json','')
            (editor/'manifest.json').write_text(json.dumps(manifest)+'\n')
            with self.assertRaisesRegex(ValueError,'Accepted native source pin mismatch'):
                stage.stage_release(source,public,source/'work/wrong-pin',expected_native_pin='0'*40)
            result=stage.stage_release(source,public,output,expected_native_pin=pin)
            self.assertEqual(result['editor_upstream_commit'],manifest['upstream_commit'])
            self.assertEqual(result['native_source_pin'],pin)
            self.assertEqual((output/'native/homebox').read_text(),'new patched backend')
            self.assertEqual(json.loads((output/'native/homebox-build-receipt.json').read_text()),receipt)
            self.assertEqual(result['backend_build_receipt_sha256'],hashlib.sha256((output/'native/homebox-build-receipt.json').read_bytes()).hexdigest())
            backend.write_text('tampered backend')
            with self.assertRaisesRegex(ValueError,'binary does not match its build receipt'):
                stage.stage_release(source,public,source/'work/tampered-backend',expected_native_pin=pin)
            backend.write_text('new patched backend')
            (source/'homebox-backend/source.txt').write_text('changed backend overlay')
            with self.assertRaisesRegex(ValueError,'different C-Crate backend sources'):
                stage.stage_release(source,public,source/'work/stale-overlay',expected_native_pin=pin)
            (source/'homebox-backend/source.txt').write_text('homebox-backend')
            put(source,'work/homebox-ui-current/index.html','different selected frontend')
            with self.assertRaisesRegex(ValueError,'Backend embedded frontend does not match'):
                stage.stage_release(source,public,source/'work/mismatched-frontend',expected_native_pin=pin)
            put(source,'work/homebox-ui-current/index.html','selected static frontend')
            self.assertEqual((output/'deploy/homebox-patchset.json').read_bytes(),(source/'deploy/homebox-patchset.json').read_bytes())
            self.assertIn(b'+patched native', (output/'deploy/homebox-patches/0001-fixture.patch').read_bytes())
            self.assertEqual((output/'upstream/homebox/README').read_text(),'pinned native\n')
            source_marker=json.loads((output/'upstream/homebox/.ccrate-homebox-source.json').read_text())
            self.assertEqual(source_marker['commit'],pin)
            self.assertEqual((output/'upstream/homebox/README').read_text(),'pinned native\n')
            from deploy.homebox_patchset import materialize
            self.assertEqual((materialize(output)/'README').read_text(),'patched native\n')
            self.assertEqual((output/'native/static/label-assets/manifest.json').read_bytes(),(editor/'manifest.json').read_bytes())
            self.assertEqual((output/'work/kiosk-ui-current/label-assets/manifest.json').read_bytes(),(editor/'manifest.json').read_bytes())
            self.assertFalse(result['private_runtime_data_included'])
            for path,digest in result['hashes'].items():self.assertEqual(hashlib.sha256((output/path).read_bytes()).hexdigest(),digest)
            for directory in (output, *[path for path in output.rglob('*') if path.is_dir()]):
                directory.chmod(directory.stat().st_mode & ~0o222)
            replaced=stage.stage_release(source,public,output,expected_native_pin=pin)
            self.assertEqual(replaced['native_source_pin'],pin)
            unowned=source/'work/unowned'
            unowned.mkdir()
            (unowned/'user-data').write_text('keep')
            with self.assertRaisesRegex(ValueError,'Refusing to replace an unowned candidate directory'):
                stage.stage_release(source,public,unowned,expected_native_pin=pin)
            self.assertEqual((unowned/'user-data').read_text(),'keep')
            (editor/'editor.html').write_text('tampered runtime asset')
            with self.assertRaisesRegex(ValueError,'runtime asset hash mismatch'):
                stage.stage_release(source,public,source/'work/tampered',expected_native_pin=pin)


if __name__ == '__main__':
    unittest.main()
