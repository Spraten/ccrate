import os
import unittest
from unittest.mock import patch
from network_access import same_origin, trusted_native_origins, valid_native_host
class NetworkAccess(unittest.TestCase):
    def test_local_and_network(self):
        for host in ['127.0.0.1:17749','192.168.1.62:17749','pi-Homebox.local:17749','[::1]:17749']:
            self.assertTrue(same_origin('http://'+host,host))
    def test_reject_cross_origin_and_malformed(self):
        for origin in [None,'null','http://evil.test:17749','http://192.168.1.62:17745','https://192.168.1.62:17749','http://192.168.1.62:17749/path','http://user@192.168.1.62:17749','http://192.168.1.62:bad']:
            self.assertFalse(same_origin(origin,'192.168.1.62:17749'))

    def test_fixture_loopback_origin_uses_ephemeral_listener_port_only_in_fixture_mode(self):
        host = '127.0.0.1:40017'
        with patch.dict(os.environ, {'WORKSHOP_FIXTURE_PROCESS': '1'}):
            self.assertTrue(same_origin('http://' + host, host))
            self.assertFalse(same_origin('http://127.0.0.1:40018', host))
            self.assertFalse(same_origin('http://evil.test:40017', host))
        self.assertFalse(same_origin('http://' + host, host))

    def test_native_origins_use_configured_port_and_explicit_host_set(self):
        self.assertEqual(trusted_native_origins('19333', {'pi.local', '127.0.0.1'}),
                         ('http://127.0.0.1:19333', 'http://pi.local:19333'))
        self.assertTrue(valid_native_host('pi.local:19333', 19333, {'pi.local'}))
        for value in ('evil.example:19333', 'pi.local:17749', 'pi.local:19333/path', 'user@pi.local:19333'):
            self.assertFalse(valid_native_host(value, 19333, {'pi.local'}), value)

    def test_native_origins_bracket_trusted_ipv6_aliases(self):
        hosts = {'::1', '2001:db8::42'}
        self.assertEqual(trusted_native_origins(19333, hosts),
                         ('http://[2001:db8::42]:19333', 'http://[::1]:19333'))
        self.assertTrue(valid_native_host('[::1]:19333', 19333, hosts))
        self.assertTrue(valid_native_host('[2001:db8::42]:19333', 19333, hosts))
        for value in ('[2001:db8::99]:19333', '[::1]:17749', '[::1]:19333/path'):
            self.assertFalse(valid_native_host(value, 19333, hosts), value)
