#!/usr/bin/env python3
"""Stage an allowlisted matched public label release under work/."""
import hashlib
import importlib.metadata
import json
import os
import pathlib
import shutil
import stat
import sys


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(source_root, output_root, source, destination=None):
    source_path = source_root / source
    destination_path = output_root / (destination or source)
    if not source_path.is_file(): raise FileNotFoundError(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)


def copy_tree(source_root, output_root, source, destination=None):
    source_path = source_root / source
    destination_path = output_root / (destination or source)
    if not source_path.is_dir(): raise FileNotFoundError(source_path)
    shutil.copytree(source_path, destination_path, symlinks=False, ignore=shutil.ignore_patterns('__pycache__','.git','node_modules','.nuxt'))


def make_owned_candidate_removable(output):
    """Restore owner directory permissions only within a verified candidate."""
    if output.is_symlink(): raise ValueError('Candidate root must not be a symlink')
    for current, directories, files in os.walk(output, topdown=True, followlinks=False):
        current_path = pathlib.Path(current)
        for name in directories + files:
            if (current_path/name).is_symlink(): raise ValueError('Candidate contains a symlink; refusing replacement')
        mode = current_path.stat(follow_symlinks=False).st_mode
        current_path.chmod(mode | stat.S_IWUSR | stat.S_IXUSR)


def validate_editor_bundle(source_root, bundle_root):
    manifest=json.loads((bundle_root/'manifest.json').read_text())
    if manifest.get('upstream_commit')!='eb118cc05b169c554066d823c44dc179aa3b96bb':raise ValueError('Editor upstream pin mismatch')
    package=pathlib.Path(source_root)/'label-ui'
    expected_roots=('package.json','pnpm-lock.yaml','vite.config.ts','editor.html','render.html','vendor-manifest.json','src','public','patches')
    expected=set()
    for entry in expected_roots:
        path=package/entry
        expected.add(entry) if path.is_file() else expected.update(item.relative_to(package).as_posix() for item in path.rglob('*') if item.is_file())
    if set(manifest.get('build_inputs',{}))!=expected:raise ValueError('Editor build input manifest is incomplete')
    for relative,digest in manifest['build_inputs'].items():
        if not (package/relative).is_file() or sha(package/relative)!=digest:raise ValueError('Built editor input differs from source: '+relative)
    runtime={path.relative_to(bundle_root).as_posix() for path in bundle_root.rglob('*') if path.is_file() and path.name!='manifest.json'}
    if runtime!=set(manifest.get('runtime_assets',{})):raise ValueError('Editor runtime asset set differs from its manifest')
    for relative,digest in manifest['runtime_assets'].items():
        if sha(bundle_root/relative)!=digest:raise ValueError('Editor runtime asset hash mismatch: '+relative)
    if sha(package/'pnpm-lock.yaml')!=manifest.get('dependencies_lock_sha256') or sha(package/'patches/0001-offline-fonts.patch')!=manifest.get('patch_sha256') or sha(package/'public/fonts/DejaVuSans.ttf')!=manifest.get('font_sha256'):
        raise ValueError('Editor lock, patch or font hash differs from the build manifest')
    vendor=package/'vendor/print-design-pro'
    vendor_hash=hashlib.sha256(b''.join(item.relative_to(vendor).as_posix().encode()+b'\0'+item.read_bytes() for item in sorted(vendor.rglob('*')) if item.is_file())).hexdigest()
    if vendor_hash!=manifest.get('vendor_source_sha256'):raise ValueError('Pinned editor source hash differs from its manifest')
    if sha(package/'public/fonts/DejaVu-Fonts-Copyright.txt')!=manifest.get('font_license_sha256') or sha(package/'vendor/print-design-pro/LICENSE')!=manifest.get('upstream_license_sha256'):
        raise ValueError('Editor license hash differs from the build manifest')
    return manifest


def stage_release(source_root, public_root, output, *, expected_native_pin='e01dd737238a3fa7e1a6454b37de6c6fc88c86e4'):
    source_root, public_root, output = map(pathlib.Path, (source_root, public_root, output))
    work_root = source_root / 'work'
    if not output.resolve().is_relative_to(work_root.resolve()): raise ValueError('Release candidate must stay under source-root work/')
    if output.exists():
        old = output / 'release-manifest.json'
        if output.is_symlink() or old.is_symlink() or not old.is_file() or json.loads(old.read_text()).get('builder') != 'deploy/stage-label-release.py':
            raise ValueError('Refusing to replace an unowned candidate directory')
        make_owned_candidate_removable(output)
        shutil.rmtree(output)
    output.mkdir(parents=True)
    import subprocess
    accepted_pin=expected_native_pin
    native_commit=subprocess.check_output(['git','-C',str(public_root/'upstream/homebox'),'rev-parse','HEAD'],text=True).strip()
    if native_commit!=accepted_pin:raise ValueError('Accepted native source pin mismatch: '+native_commit)
    copy_tree(public_root,output,'upstream/homebox')
    for tree in ('homebox-backend','ops','kiosk'):
        copy_tree(source_root,output,tree)
    copy_tree(public_root,output,'work/hardware/python')
    copy_tree(source_root,output,'homebox-ui/overlay')
    for name in ('README.md','pnpm-lock.yaml','upstream-typecheck.json'):
        copy_file(source_root,output,'homebox-ui/'+name)
    copy_tree(source_root,output,'work/homebox-ui-build/.output/public','native/static')
    copy_tree(source_root,output,'work/homebox-ui-build/.output/public','work/homebox-ui-current')
    copy_tree(source_root,output,'kiosk','work/kiosk-ui-current')
    copy_file(public_root,output,'work/homebox-bin/homebox','native/homebox')
    copy_file(public_root,output,'work/supvan-cups/target/release/examples/kiosk-label','native/kiosk-label')
    for name in ('deploy/kiosk-server.py','deploy/workshop-gateway.py','deploy/run-homebox.py','deploy/backup-deployment.py','deploy/build-homebox-ui.py','deploy/build-label-ui.py','deploy/install-shared-tools.py','deploy/runtime-manifest.py','deploy/stage-label-release.py','deploy/verify-label-layouts.py','deploy/homebox-native.service','deploy/homebox-companion.service','deploy/homebox-workshop-gateway.service','deploy/Equipment Terminal.desktop','deploy/Open-Workshop.ps1'):
        copy_file(source_root,output,name)
    for tree in ('src','vendor','public','patches'):
        copy_tree(source_root,output,'label-ui/'+tree)
    for name in ('package.json','pnpm-lock.yaml','vite.config.ts','editor.html','render.html','vendor-manifest.json'):
        copy_file(source_root,output,'label-ui/'+name)
    copy_tree(source_root,output,'work/label-ui-build')
    copy_tree(source_root,output,'work/label-ui-build','native/static/label-assets')
    copy_tree(source_root,output,'work/label-ui-build','work/kiosk-ui-current/label-assets')
    validate_editor_bundle(source_root,output/'work/label-ui-build')
    if (output/'native/static/label-assets/manifest.json').read_bytes()!=(output/'work/label-ui-build/manifest.json').read_bytes():raise ValueError('Native static label assets differ from the editor runtime')
    if (output/'work/kiosk-ui-current/label-assets/manifest.json').read_bytes()!=(output/'work/label-ui-build/manifest.json').read_bytes():raise ValueError('Terminal label assets differ from the editor runtime')
    for name in ('docs/LABEL_LAYOUTS.md','docs/LABEL_LAYOUTS_TASK5_REPORT.md','docs/runtime-manifest.json','docs/DECISIONS.md'):
        copy_file(source_root, output, name)
    receipt_root = public_root/'work/c-crate-release-preparation'
    rollback_source = receipt_root/'baseline'
    snapshot_path = rollback_source/'snapshot-manifest.json'
    rollback_provenance = {'snapshot_records': 0, 'snapshot_all_hashes_verified': False, 'receipt_count': 0, 'receipt_hashes_verified': False}
    if snapshot_path.is_file():
        snapshot = json.loads(snapshot_path.read_text())
        records = snapshot if isinstance(snapshot, list) else snapshot.get('files', [])
        for record in records:
            item = rollback_source/record['path']
            if not item.is_file() or item.stat().st_size != record['size'] or sha(item) != record['sha256']:
                raise ValueError('Previous public snapshot does not match its manifest: '+record['path'])
        copy_tree(public_root, output, 'work/c-crate-release-preparation/baseline', 'rollback-previous-public')
        acceptance_path = receipt_root/'release-acceptance.json'
        acceptance = json.loads(acceptance_path.read_text())
        receipts = acceptance.get('evidence_files', {})
        for key, record in receipts.items():
            item = pathlib.Path(record['path'])
            if not item.is_file() or sha(item) != record['sha256']:
                raise ValueError('Previous release evidence hash mismatch: '+key)
            copy_file(item.parents[2], output, str(item.relative_to(item.parents[2])), 'rollback-evidence/'+key+item.suffix)
        copy_file(receipt_root, output, 'release-acceptance.json', 'rollback-evidence/release-acceptance.json')
        candidate_manifest = receipt_root/'candidate/candidate-manifest.json'
        if not candidate_manifest.is_file() or sha(candidate_manifest)!=acceptance.get('candidate_manifest_sha256'):
            raise ValueError('Previous candidate manifest hash mismatch')
        copy_file(receipt_root, output, 'candidate/candidate-manifest.json', 'rollback-evidence/candidate-manifest.json')
        rollback_provenance = {'snapshot_records':len(records), 'snapshot_all_hashes_verified':True, 'receipt_count':len(receipts), 'receipt_hashes_verified':True, 'baseline_desktop_outcome':acceptance.get('baseline_desktop_outcome'), 'full_desktop_suite_passed':acceptance.get('full_desktop_suite_passed'),'candidate_manifest_sha256':acceptance.get('candidate_manifest_sha256')}
    files = sorted(path for path in output.rglob('*') if path.is_file() and path.name != 'release-manifest.json')
    editor_manifest = json.loads((output/'work/label-ui-build/manifest.json').read_text())
    manifest = {
        'format': 1, 'builder': 'deploy/stage-label-release.py',
        'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=source_root,text=True).strip() if (source_root/'.git').exists() else None,
        'native_source_commit': native_commit, 'native_source_pin': accepted_pin,
        'editor_upstream_commit': editor_manifest['upstream_commit'],
        'editor_manifest_sha256': sha(output/'work/label-ui-build/manifest.json'),
        'editor_build': {key:editor_manifest.get(key) for key in ('upstream_commit','vendor_source_sha256','patch_sha256','dependencies_lock_sha256','font_sha256','font_license_sha256','upstream_license_sha256')},
        'runtime_compatibility': {'chromium':None,'playwright':None,'python':sys.version},
        'rollback_provenance':rollback_provenance,
        'runtime_linkage': {'native_binary':'native/homebox','native_static':'native/static','native_selected_static':'work/homebox-ui-current','terminal_source':'kiosk','terminal_selected_static':'work/kiosk-ui-current','python_runtime':'work/hardware/python','label_source':'label-ui','label_assets':'work/label-ui-build','native_label_assets':'native/static/label-assets','terminal_label_assets':'work/kiosk-ui-current/label-assets'},
        'hashes': {path.relative_to(output).as_posix(): sha(path) for path in files},
        'file_count': len(files),
        'private_runtime_data_included': False,
        'rollback_note': 'Previous public snapshot/receipts are verified separately. Legacy recovery behavior does not prove safe code rollback while new-label intents are unresolved; preserve the label database and resolve intents before code rollback.',
    }
    try: manifest['runtime_compatibility']['chromium']=subprocess.check_output(['chromium','--version'],text=True).strip()
    except Exception: pass
    try:
        distributions=importlib.metadata.distributions(path=[str(public_root/'work/hardware/python')])
        manifest['runtime_compatibility']['playwright']=next(d.version for d in distributions if d.metadata.get('Name','').lower()=='playwright')
    except StopIteration: pass
    (output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    public_root = pathlib.Path('/home/user/Desktop/inventory-system')
    out = root/'work/label-layout-release-candidate'
    manifest = stage_release(root,public_root,out)
    print(json.dumps({'candidate':str(out),'files':manifest['file_count'],'editor_commit':manifest['editor_upstream_commit'],'manifest_sha256':sha(out/'release-manifest.json')},indent=2))


if __name__ == '__main__': main()
