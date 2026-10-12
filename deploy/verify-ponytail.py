#!/usr/bin/env python3
"""Verify the pinned Ponytail skill and persistent project activation."""
import hashlib
import json
import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
record = json.loads((root/'docs/ponytail-install.json').read_text())
skill = pathlib.Path(record['skill'])
assert hashlib.sha256(skill.read_bytes()).hexdigest() == record['sha256']
assert record['repository'] == 'https://github.com/DietrichGebert/ponytail'
assert record['mode'] == 'full'
assert str(skill) in (root/'AGENTS.md').read_text()
assert 'Ponytail never overrides' in (root/'AGENTS.md').read_text()
print('Ponytail full mode: installed skill matches the pinned source; project activation is persistent.')
