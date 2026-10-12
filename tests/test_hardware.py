import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import hardware


class HardwareTests(unittest.TestCase):
    def test_printer_reconnect_only_probes_and_explains_failures(self):
        with patch.object(hardware, 'probe', return_value={'width_mm': 40, 'height_mm': 30}) as probe:
            self.assertTrue(hardware.reconnect('printer')['connected']); probe.assert_called_once_with()
        failures = [(FileNotFoundError(), 'disconnected'), (PermissionError(), 'permission'),
                    (OSError('resource busy'), 'busy'), (subprocess.TimeoutExpired('probe', 15), 'timeout'),
                    (subprocess.CalledProcessError(1, 'probe', stderr=b'Permission denied'), 'permission'),
                    (ValueError('Load paper'), 'not_ready')]
        for error, reason in failures:
            with self.subTest(reason=reason), patch.object(hardware, 'probe', side_effect=error):
                result = hardware.reconnect('printer')
                self.assertFalse(result['connected']); self.assertEqual(result['reason'], reason)
                self.assertTrue(result['steps'])
        with self.assertRaises(ValueError): hardware.reconnect('arbitrary-device')

    def test_camera_reconnect_uses_original_stable_path_without_changing_controls(self):
        with patch.object(hardware.pathlib.Path, 'exists', return_value=True), patch.object(hardware.os, 'access', return_value=True), patch.object(hardware.subprocess, 'run', return_value=SimpleNamespace(stdout='focus_absolute: 150\nfocus_automatic_continuous: 1\n')) as run:
            result = hardware.reconnect('camera')
            self.assertTrue(result['connected']); self.assertEqual(result['mode'], 'auto')
            command = run.call_args.args[0]
            self.assertIn(str(hardware.CAMERA), command)
            self.assertFalse(any('--set' in part for part in command))
        with patch.object(hardware.pathlib.Path, 'exists', return_value=False):
            self.assertEqual(hardware.reconnect('camera')['reason'], 'disconnected')
        with patch.object(hardware.pathlib.Path, 'exists', return_value=True), patch.object(hardware.os, 'access', return_value=False):
            self.assertEqual(hardware.reconnect('camera')['reason'], 'permission')
