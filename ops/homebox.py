"""Supported native Homebox API access; credentials stay on the Pi."""
import json
import os
import pathlib
import urllib.request
from http.cookies import SimpleCookie, CookieError
from uuid import UUID


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # An authenticated API request must never forward its cookies elsewhere.
        return None


def session_cookie(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 8192 or '\r' in raw or '\n' in raw:
        raise ValueError('C-Crate sign-in is required')
    cookies = SimpleCookie()
    try:
        cookies.load(raw)
    except CookieError:
        raise ValueError('C-Crate sign-in is required') from None
    if not all(name in cookies and cookies[name].value for name in ('hb.auth.token', 'hb.auth.remember')):
        raise ValueError('C-Crate sign-in is required')
    return '; '.join(name+'='+cookies[name].coded_value for name in ('hb.auth.token', 'hb.auth.remember'))


class Homebox:
    def __init__(self, root=None, base=None, timeout=8, *, cookie=None, tenant=None, login_timeout=None, deadline=None):
        self.base = base or os.environ.get('WORKSHOP_NATIVE_BASE', 'http://127.0.0.1:17745')
        self.timeout = timeout
        self.login_timeout = login_timeout
        self.deadline = deadline
        self.token = None
        self.cookie = session_cookie(cookie) if cookie is not None else None
        self.tenant = str(UUID(str(tenant))) if tenant else None
        self.opener = urllib.request.build_opener(NoRedirect())
        if self.cookie is not None:
            return
        if root is None:
            raise ValueError('A native session or local service account is required')
        account = json.loads((pathlib.Path(root)/'work/baseline/test-account.json').read_text())
        self.token = self.call('/api/v1/users/login', 'POST', {
            'username': account['email'], 'password': account['password']
        })['token'].removeprefix('Bearer ')

    @classmethod
    def from_cookie(cls, cookie, base=None, timeout=8):
        return cls(base=base, timeout=timeout, cookie=cookie)

    def call(self, path, method='GET', data=None):
        if not isinstance(path, str) or not path.startswith('/api/v1/') or '\r' in path or '\n' in path:
            raise ValueError('Unsupported native API path')
        headers = {'Content-Type': 'application/json'}
        if getattr(self, 'cookie', None):
            headers['Cookie'] = self.cookie
        if getattr(self, 'tenant', None):
            headers['X-Tenant'] = self.tenant
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        request = urllib.request.Request(self.base+path, method=method,
            headers=headers, data=json.dumps(data).encode() if data is not None else None)
        opener = getattr(self, 'opener', None) or urllib.request.build_opener(NoRedirect())
        timeout=self.timeout
        if self.deadline is not None:
            import time
            timeout=min(timeout,self.deadline-time.monotonic())
            if timeout<=0:raise TimeoutError('Homebox request exceeded its deadline')
        if path=='/api/v1/users/login':timeout=max(30,timeout) if self.login_timeout is None else min(timeout,self.login_timeout)
        with opener.open(request, timeout=timeout) as response:
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
