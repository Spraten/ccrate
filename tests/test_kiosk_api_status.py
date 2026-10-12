import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class KioskApiStatusTests(unittest.TestCase):
    def test_api_errors_preserve_http_status(self):
        source = (ROOT / 'kiosk/workflow-ui.js').read_text()
        api = re.search(r'^api=async function\([^\n]+', source, re.MULTILINE).group(0)
        html = f'''<!doctype html><body>pending</body><script>
        {api}
        fetch = async path => path === '/html-error'
          ? ({{ok:false, status:403, json:async()=>{{throw new SyntaxError('Unexpected token <')}}}})
          : path === '/success-malformed'
            ? ({{ok:true, status:200, json:async()=>{{throw new SyntaxError('Unexpected token <')}}}})
            : ({{ok:false, status:403, json:async()=>({{error:'management revoked'}})}});
        (async () => {{
          const result=[];
          for (const path of ['/html-error', '/json-error', '/success-malformed']) {{
            try {{ await api(path, {{}}); result.push({{message:'unexpected success'}}); }}
            catch (error) {{ result.push({{message:error.message,status:error.status}}); }}
          }}
          document.body.textContent=JSON.stringify(result);
        }})();
        </script>'''
        with tempfile.TemporaryDirectory() as profile:
            fixture = pathlib.Path(profile) / 'fixture.html'
            fixture.write_text(html)
            result = subprocess.run(
                ['/usr/bin/chromium', '--headless', '--no-sandbox', '--disable-gpu',
                 '--disable-dev-shm-usage', '--disable-background-networking',
                 '--disable-extensions', '--virtual-time-budget=1000', '--user-data-dir=' + profile,
                 '--dump-dom', fixture.as_uri()],
                check=True, capture_output=True, text=True, timeout=45)

        self.assertIn('[{"message":"The service did not return a readable result. Check recovery before retrying a write.","status":403},{"message":"management revoked","status":403},{"message":"The service did not return a readable result. Check recovery before retrying a write."}]',
                      result.stdout)


if __name__ == '__main__':
    unittest.main()
