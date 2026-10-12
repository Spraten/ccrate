"""Server-owned address trust shared by the kiosk and public gateway."""
import json
import os
import socket
import subprocess
import time
from urllib.parse import urlsplit

_addresses = (0, set())

def local_hosts():
    global _addresses
    if time.monotonic() - _addresses[0] < 15:
        return _addresses[1]
    hostname = socket.gethostname().lower()
    names = {'localhost', '127.0.0.1', '::1', hostname, hostname + '.local'}
    try:
        names.update(addr[4][0].lower() for addr in socket.getaddrinfo(hostname, None))
    except OSError:
        pass
    try:
        interfaces = json.loads(subprocess.check_output(['ip', '-j', 'addr'], timeout=2))
        for interface in interfaces:
            names.update(a['local'].lower() for a in interface.get('addr_info', []))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    _addresses = (time.monotonic(), names)
    return names

def trusted_native_origins(port, hosts=None):
    try:
        port = int(port)
        if not 1 <= port <= 65535:
            return ()
    except (TypeError, ValueError):
        return ()
    hosts = local_hosts() if hosts is None else hosts
    result = []
    for host in hosts:
        host = str(host).lower()
        bare_host = host[1:-1] if host.startswith('[') and host.endswith(']') else host
        authority = '[' + bare_host + ']' if ':' in bare_host else bare_host
        try:
            parsed = urlsplit('http://' + authority)
            if (parsed.hostname != bare_host or parsed.port is not None or parsed.path
                    or parsed.username or parsed.password):
                continue
            rendered = '[' + bare_host + ']' if ':' in bare_host else bare_host
            result.append(f'http://{rendered}:{port}')
        except ValueError:
            continue
    return tuple(sorted(set(result)))

def valid_native_host(value, port, hosts=None):
    try:
        parsed = urlsplit('http://' + value)
        hostname = (parsed.hostname or '').lower()
        trusted = trusted_native_origins(port, hosts)
        rendered = '[' + hostname + ']' if ':' in hostname else hostname
        candidate = f'http://{rendered}:{parsed.port}'
        return (candidate in trusted and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment)
    except (TypeError, ValueError):
        return False

def same_origin(origin,host):
    if not origin or not host:return False
    try:
        source=urlsplit(origin);target=urlsplit('http://'+host)
        if os.environ.get('WORKSHOP_FIXTURE_PROCESS')=='1':
            return (source.scheme=='http' and source.hostname in ('127.0.0.1','::1')
                    and source.hostname==target.hostname and source.port==target.port
                    and source.port is not None and 32768<=source.port<=60999
                    and not source.username and not source.password and not source.path
                    and not source.query and not source.fragment
                    and not target.username and not target.password and not target.path)
        return (source.scheme=='http' and source.hostname is not None
                and source.hostname==target.hostname
                and source.port==target.port==17749
                and not source.username and not source.password
                and not source.path and not source.query and not source.fragment
                and not target.username and not target.password and not target.path)
    except ValueError:return False
