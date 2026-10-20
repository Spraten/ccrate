#!/usr/bin/env python3
"""Install the pinned pnpm CLI without Debian's large npm package tree."""
import argparse
import base64
import hashlib
import io
import json
import os
import pathlib
import shlex
import tarfile
import urllib.request

VERSION = '10.28.0'
TARBALL = f'https://registry.npmjs.org/pnpm/-/pnpm-{VERSION}.tgz'
SHA512 = 'Bd9x0UIfITmeBT/eVnzqNNRG+gLHZXFEG/wceVbpjjYwiJgtlARl/TRIDU2QoGaLwSNi+KqIAApk6D0LDke+SA=='


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True, type=pathlib.Path)
    destination = parser.parse_args().destination.resolve()
    package = destination / 'node_modules' / 'pnpm'
    binary = package / 'bin' / 'pnpm.cjs'
    wrapper = destination / 'node_modules' / '.bin' / 'pnpm'

    if binary.is_file():
        metadata = json.loads((package / 'package.json').read_text())
        if metadata.get('name') != 'pnpm' or metadata.get('version') != VERSION:
            raise SystemExit(f'Refusing to replace unexpected package at {package}')
    else:
        if package.exists():
            raise SystemExit(f'Incomplete pnpm package exists at {package}; move it aside and rerun')
        request = urllib.request.Request(TARBALL, headers={'User-Agent': 'ccrate-setup'})
        with urllib.request.urlopen(request, timeout=60) as response:
            archive_bytes = response.read()
        actual = base64.b64encode(hashlib.sha512(archive_bytes).digest()).decode('ascii')
        if actual != SHA512:
            raise SystemExit('Pinned pnpm archive failed SHA-512 verification')

        package.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            for member in archive.getmembers():
                path = pathlib.PurePosixPath(member.name)
                if (not path.parts or path.parts[0] != 'package' or '..' in path.parts
                        or path.is_absolute() or not (member.isfile() or member.isdir())):
                    raise SystemExit(f'Refusing unsafe pnpm archive member: {member.name}')
                relative = pathlib.Path(*path.parts[1:])
                if not relative.parts:
                    continue
                target = package / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise SystemExit(f'Could not read pnpm archive member: {member.name}')
                with source, target.open('wb') as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
        metadata = json.loads((package / 'package.json').read_text())
        if metadata.get('name') != 'pnpm' or metadata.get('version') != VERSION or not binary.is_file():
            raise SystemExit('Pinned pnpm archive did not contain the expected CLI')

    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\nexec /usr/bin/node ' + shlex.quote(str(binary)) + ' "$@"\n')
    wrapper.chmod(0o755)
    print(f'Installed pnpm {VERSION} with verified SHA-512 integrity.')


if __name__ == '__main__':
    main()
