import unittest,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ops'))
from kiosk_processes import is_kiosk_process

class KioskProcessTests(unittest.TestCase):
    def test_normal_and_rewritten_argv(self):
        profile='/home/user/Desktop/inventory-system/work/kiosk-browser'
        args=['/usr/lib/chromium/chromium','--user-data-dir='+profile,'--app=http://127.0.0.1:17749/']
        self.assertTrue(is_kiosk_process(('\0'.join(args)+'\0').encode(),profile))
        self.assertTrue(is_kiosk_process((' '.join(args)+'\0').encode(),profile))
        self.assertFalse(is_kiosk_process((' '.join(args+['--type=renderer'])+'\0').encode(),profile))
        self.assertFalse(is_kiosk_process((' '.join(args)+'\0').encode(),'/another-profile'))
        self.assertFalse(is_kiosk_process(b'/usr/bin/python --user-data-dir=/test\0','/test'))
        self.assertFalse(is_kiosk_process(b'',profile))

if __name__=='__main__':unittest.main()
