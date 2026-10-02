import hashlib, os, pathlib, shutil, subprocess, tarfile, tomllib, urllib.request

root = pathlib.Path('/home/user/Desktop/inventory-system')
work = root/'work'
manifest = tomllib.loads((work/'hardware/rust-channel.toml').read_text())
runtime = work/'rust-native'
for component in ['rustc','cargo','rust-std']:
    data = manifest['pkg'][component]['target']['aarch64-unknown-linux-gnu']
    artifact = work/'hardware'/pathlib.Path(data['xz_url']).name
    if not artifact.exists() or hashlib.sha256(artifact.read_bytes()).hexdigest() != data['xz_hash']:
        print('DOWNLOAD', component, flush=True)
        partial=artifact.with_suffix(artifact.suffix+'.part')
        with urllib.request.urlopen(data['xz_url'], timeout=30) as source, partial.open('wb') as target:
            shutil.copyfileobj(source,target)
        assert hashlib.sha256(partial.read_bytes()).hexdigest() == data['xz_hash']
        partial.replace(artifact)
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == data['xz_hash']
    folder = work/'hardware/rust-components'/artifact.name.removesuffix('.tar.xz')
    if not (folder/'.extracted').exists():
        with tarfile.open(artifact) as archive:
            archive.extractall(folder.parent,filter='data')
        (folder/'.extracted').touch()
    print('INSTALL',component,flush=True)
    subprocess.run(['sh',str(folder/'install.sh'),'--prefix='+str(runtime),'--disable-ldconfig'],check=True)
deps=work/'build-deps/root'
pcdir=deps/'usr/lib/aarch64-linux-gnu/pkgconfig'
for path in pcdir.glob('*.pc'):
    data=path.read_text()
    if 'prefix=/usr' in data:
        path.write_text(data.replace('/usr',str(deps/'usr')))
env=dict(os.environ,PATH=str(runtime/'bin')+':'+os.environ['PATH'],
         CARGO_HOME=str(work/'cargo-home'),PKG_CONFIG_PATH=str(pcdir))
print('RUST',subprocess.check_output([str(runtime/'bin/rustc'),'--version'],text=True),flush=True)
subprocess.run([str(runtime/'bin/cargo'),'build','--locked','--release','-p','supvan-cli','-j','2'],
               cwd=work/'supvan-cups',env=env,check=True)
print('PRINTER_CLI_READY',flush=True)
