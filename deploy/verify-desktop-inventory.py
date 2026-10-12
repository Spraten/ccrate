#!/usr/bin/env python3
"""Prove cutover preserves native identities and metadata; expose counts only."""
import argparse
import hashlib
import json
import pathlib
import sys
ROOT = pathlib.Path('/home/user/Desktop/inventory-system')
sys.path.insert(0, str(ROOT/'ops'))
from homebox import Homebox
parser = argparse.ArgumentParser()
parser.add_argument('--before', action='store_true')
args = parser.parse_args()
client = Homebox(ROOT, base='http://127.0.0.1:'+('17745' if args.before else '17747'))
equipment = [client.entity(row['id']) for row in client.entities()]
locations = [client.entity(row['id']) for row in client.entities(True)]
members = client.call('/api/v1/groups/members')
def digest(rows):
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda row: row['id']), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
state = {'equipment': len(equipment), 'locations': len(locations), 'members': len(members),
         'equipment_digest': digest(equipment), 'location_digest': digest(locations),
         'member_digest': digest(members)}
path = ROOT/'work/desktop-before-inventory.json'
if args.before:
    path.write_text(json.dumps(state)); path.chmod(0o600)
    print('Native inventory baseline recorded privately on the Pi.')
else:
    assert json.loads(path.read_text()) == state, 'Native inventory or membership changed during cutover; inspect before proceeding.'
    print(json.dumps({'inventory_preserved': True, **{key: state[key] for key in ('equipment', 'locations', 'members')}}))
