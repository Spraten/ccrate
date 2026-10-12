import unittest
from types import SimpleNamespace
from unittest.mock import patch
import system_status
class SystemStatusTests(unittest.TestCase):
    def disk(self,free,total=64*1024**3):return SimpleNamespace(free=free,total=total)
    def test_low_absolute_storage_warns(self):
        self.assertEqual(system_status.storage_health(self.disk(1024**3,4*1024**3))['level'],'warning')
    def test_low_percentage_warns(self):
        self.assertEqual(system_status.storage_health(self.disk(5*1024**3))['level'],'warning')
    def test_critical_storage_preserves_data(self):
        result=system_status.storage_health(self.disk(200*1024**2))
        self.assertEqual(result['level'],'critical');self.assertIn('Preserve inventory',result['message'])
    def test_healthy_storage(self):
        self.assertEqual(system_status.storage_health(self.disk(30*1024**3)),{'level':'ok','message':None})
    def test_disconnected_printer_keeps_diagnostics_available(self):
        with patch('hardware.probe',side_effect=OSError('Disconnected')),patch.object(system_status,'camera_status',return_value={'connected':False}),patch.object(system_status,'unit',return_value='active'),patch.object(system_status,'read_state',return_value=None),patch.object(system_status.shutil,'disk_usage',return_value=self.disk(30*1024**3)):
            result=system_status.status()
        self.assertFalse(result['printer']['connected']);self.assertEqual(result['storage']['level'],'ok')
