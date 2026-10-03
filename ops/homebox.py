"""Supported native Homebox API access; credentials stay on the Pi."""
import json
import pathlib
import urllib.request
from uuid import UUID


class Homebox:
    def __init__(self, root, base='http://127.0.0.1:17745'):
        self.base = base
        self.token = None
        account = json.loads((pathlib.Path(root)/'work/baseline/test-account.json').read_text())
        self.token = self.call('/api/v1/users/login', 'POST', {
            'username': account['email'], 'password': account['password']
        })['token'].removeprefix('Bearer ')

    def call(self, path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        request = urllib.request.Request(self.base+path, method=method,
            headers=headers, data=json.dumps(data).encode() if data is not None else None)
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read()
            return json.loads(body) if body else None

    def entity(self, entity_id):
        return self.call('/api/v1/entities/'+str(UUID(str(entity_id))))

    def entities(self,locations=False):
        items=[];page=1
        while True:
            result=self.call('/api/v1/entities?page='+str(page)+'&pageSize=100&includeArchived=true&isLocation='+str(locations).lower())
            items.extend(result['items'])
            if len(items)>=result['total'] or not result['items']:return items
            page+=1
