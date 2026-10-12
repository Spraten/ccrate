"""Isolated authoritative label rendering through the staged PrintDesignPro build."""
import base64
import hashlib
import http.server
import io
import json
import math
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading
import time
import ctypes
from urllib.parse import unquote, urlparse

ROOT = pathlib.Path(os.environ.get('WORKSHOP_ROOT', '/home/user/Desktop/inventory-system'))
CODE_ROOT = pathlib.Path(os.environ.get('WORKSHOP_CODE_ROOT', str(pathlib.Path(__file__).resolve().parents[1])))
DEFAULT_ASSET_ROOT = (CODE_ROOT / 'label-ui' if os.environ.get('WORKSHOP_CODE_ROOT')
                      else ROOT / 'work/label-ui-build')
NODE = pathlib.Path(os.environ.get('WORKSHOP_NODE', str(ROOT / 'work/toolchains/node-v24.21.0-linux-arm64/bin/node')))
PLAYWRIGHT_PYTHON = str(ROOT / 'work/hardware/python')
MAX_INPUT = 1024 * 1024
MAX_TRUSTED_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_DIMENSION = 16384
SUPVAN = {'label_mm': [40, 28], 'dpi': 203.2}
LETTER = {'label_mm': [60, 40], 'dpi': 300}


def _check_manifest(root):
    try:
        root = pathlib.Path(root).resolve(strict=True)
        manifest_path = root / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError, TypeError):
        raise ValueError('The staged label renderer build is missing or invalid; rebuild the offline label assets') from None
    if not isinstance(manifest,dict) or not isinstance(manifest.get('runtime_assets'),dict):
        raise ValueError('The staged label renderer manifest is invalid; rebuild the offline label assets')
    for name, expected in manifest.get('runtime_assets', {}).items():
        try:
            path = (root / name).resolve(strict=True)
            path.relative_to(root)
            data=path.read_bytes()
        except (OSError, ValueError):
            raise ValueError('A staged label renderer asset is missing or outside its build root: '+str(name)) from None
        if not path.is_file() or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Renderer asset hash mismatch: ' + name)
    for name in ('render.html', 'fonts/DejaVuSans.ttf'):
        if name not in manifest.get('runtime_assets', {}):
            raise ValueError('Renderer manifest is missing ' + name)
    return root


class _Handler(http.server.BaseHTTPRequestHandler):
    root = None
    assets = frozenset()

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        prefix = '/workshop-api/label-assets/'
        if not path.startswith(prefix):
            self.send_error(404)
            return
        name = path[len(prefix):]
        try:
            file = (self.root / name).resolve(strict=True)
            file.relative_to(self.root)
            if not file.is_file() or name not in self.assets: raise ValueError()
            data = file.read_bytes()
        except Exception:
            self.send_error(404)
            return
        mime = 'text/html; charset=utf-8' if name == 'render.html' else 'font/ttf' if name.endswith('.ttf') else 'application/javascript' if name.endswith('.js') else 'text/css' if name.endswith('.css') else 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src data: blob:; connect-src 'none'; frame-src 'self'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_): pass


def _child(payload):
    sys.path.insert(0, PLAYWRIGHT_PYTHON)
    from playwright.sync_api import sync_playwright
    root = _check_manifest(payload['asset_root'])
    _Handler.root = root
    _Handler.assets = frozenset(json.loads((root/'manifest.json').read_text()).get('runtime_assets',{}))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    deadline = time.monotonic() + payload['remaining']
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context()
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
            page = context.new_page()
            # `load` is sufficient: the render module is bundled into the page and
            # the explicit readiness loop below covers its public entry points.
            # Waiting for network-idle adds a costly Chromium quiescence window.
            page.goto(origin + '/workshop-api/label-assets/render.html', wait_until='load', timeout=max(1000, int((deadline-time.monotonic())*1000)))
            while not page.evaluate('typeof window.renderLabelDocument === "function" && typeof window.composePaperSheet === "function"'):
                if time.monotonic()>=deadline:raise TimeoutError('Label renderer did not become ready within the request budget')
                page.wait_for_timeout(20)
            batch_start=page.evaluate('performance.now()')
            remaining_ms=max(1,int((deadline-time.monotonic())*1000))
            rendered=page.evaluate('''async ({documents, start, budget}) => {
              const output=[];
              for (const [doc, profile] of documents) {
                if (performance.now()-start>=budget) throw new Error('Label rendering exceeded the request budget');
                output.push(await window.renderLabelDocument(doc, {dpi: profile.dpi, profile: profile.id, background: '#ffffff'}));
              }
              return output;
            }''', {'documents':payload.get('documents',[]),'start':batch_start,'budget':remaining_ms})
            # Keep the browser's exact PNG data. Decoding/re-encoding every
            # base64 payload here adds no validation and is costly for batches.
            results=[{'png':result['png_base64'], 'width':result['width'], 'height':result['height'],'warnings':result.get('warnings',[])} for result in rendered]
            if 'sheet' in payload:
                sheet_result = page.evaluate('async ({reviews, geometry}) => window.composePaperSheet(reviews, geometry)', payload['sheet'])
                payload['sheet_result']=sheet_result
            context.close()
            browser.close()
        output={'results':results, 'sheet_result':payload.get('sheet_result')}
        encoded=json.dumps(output,separators=(',',':')).encode()
        if len(encoded)>MAX_OUTPUT: raise ValueError('Renderer output exceeds 16 MiB')
        sys.stdout.buffer.write(encoded)
    finally:
        server.shutdown()


def _run(payload, timeout):
    payload['remaining']=max(.1, timeout)
    raw=json.dumps(payload,separators=(',',':')).encode()
    cap=MAX_TRUSTED_INPUT if payload.get('trusted_sheet') else MAX_INPUT
    if len(raw)>cap: raise ValueError('Renderer input exceeds its byte limit')
    started=time.monotonic()
    child_env={'PATH':os.environ.get('PATH',''), 'HOME':'/tmp', 'LANG':'C.UTF-8', 'WORKSHOP_ROOT':str(ROOT)}
    for key in ('WORKSHOP_CODE_ROOT','WORKSHOP_LABEL_ASSET_ROOT','WORKSHOP_NODE','PLAYWRIGHT_BROWSERS_PATH'):
        if key in os.environ:child_env[key]=os.environ[key]
    process=subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), '--child'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env, start_new_session=True)
    try:stdout,stderr=process.communicate(raw,timeout=timeout)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except Exception:pass
        process.communicate()
        raise TimeoutError('Label rendering exceeded the 20-second request budget') from None
    if process.returncode:
        message=stderr.decode('utf-8','replace')[-2000:] or 'Renderer subprocess failed'
        raise ValueError(message)
    if len(stdout)>MAX_OUTPUT: raise ValueError('Renderer output exceeds 16 MiB')
    if time.monotonic()-started>timeout: raise TimeoutError('Label rendering exceeded the 20-second request budget')
    return json.loads(stdout)


def _decode_qr_l(image):
    """Decode the final L raster with the system zbar scanner before freezing it."""
    library=ctypes.CDLL('libzbar.so.0')
    library.zbar_image_scanner_create.restype=ctypes.c_void_p
    library.zbar_image_create.restype=ctypes.c_void_p
    library.zbar_symbol_get_data.restype=ctypes.c_char_p
    library.zbar_image_first_symbol.restype=ctypes.c_void_p
    scanner=library.zbar_image_scanner_create(); native_image=library.zbar_image_create()
    data=image.tobytes(); buffer=ctypes.create_string_buffer(data)
    try:
        library.zbar_image_scanner_set_config.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int]
        library.zbar_image_scanner_set_config(scanner,64,0,1)
        library.zbar_image_set_format.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        library.zbar_image_set_size.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        library.zbar_image_set_data.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p]
        library.zbar_image_set_format(native_image,ord('Y')|(ord('8')<<8)|(ord('0')<<16)|(ord('0')<<24))
        library.zbar_image_set_size(native_image,image.width,image.height)
        library.zbar_image_set_data(native_image,buffer,len(data),None)
        library.zbar_scan_image.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        library.zbar_image_first_symbol.argtypes=[ctypes.c_void_p]
        if library.zbar_scan_image(scanner,native_image)<=0:raise ValueError('Final label QR failed decoding')
        symbol=library.zbar_image_first_symbol(native_image)
        if not symbol:raise ValueError('Final label QR failed decoding')
        library.zbar_symbol_get_data.argtypes=[ctypes.c_void_p]
        decoded=library.zbar_symbol_get_data(symbol)
        return decoded.decode('utf-8') if decoded else ''
    finally:
        library.zbar_image_destroy.argtypes=[ctypes.c_void_p];library.zbar_image_destroy(native_image)
        library.zbar_image_scanner_destroy.argtypes=[ctypes.c_void_p];library.zbar_image_scanner_destroy(scanner)


def render_documents(documents, profiles, *, asset_root=None, timeout=20):
    request_started = time.monotonic()
    if len(documents)!=len(profiles) or not documents: raise ValueError('At least one document is required')
    if len(documents)>36: raise ValueError('Render at most 36 labels at a time')
    for doc, profile in zip(documents, profiles):
        if profile not in ('supvan','letter'): raise ValueError('Unknown label profile')
        dims=SUPVAN if profile=='supvan' else LETTER
        page=doc.get('page',{})
        label_mm=[page.get('widthMm'),page.get('heightMm')]
        if profile=='supvan' and label_mm!=dims['label_mm']: raise ValueError('Document dimensions do not match the selected profile')
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in label_mm): raise ValueError('Document dimensions must be finite and positive')
        expected=round(label_mm[0]*dims['dpi']/25.4),round(label_mm[1]*dims['dpi']/25.4)
        if expected[0]>MAX_DIMENSION or expected[1]>MAX_DIMENSION or expected[0]*expected[1]>MAX_PIXELS: raise ValueError('Label canvas exceeds renderer pixel limits')
    root=_check_manifest(asset_root or DEFAULT_ASSET_ROOT)
    payload={'asset_root':str(root),'documents':[[doc, {'id':profile,'dpi':(SUPVAN if profile=='supvan' else LETTER)['dpi']}] for doc,profile in zip(documents,profiles)]}
    remaining = timeout - (time.monotonic() - request_started)
    if remaining <= 0: raise TimeoutError('Label rendering exceeded the 20-second request budget')
    result=_run(payload,remaining)['results']
    outputs=[]
    from PIL import Image
    for index,row in enumerate(result):
        if time.monotonic() - request_started >= timeout: raise TimeoutError('Label rendering exceeded the 20-second request budget')
        raw=base64.b64decode(row['png'],validate=True)
        image=Image.open(io.BytesIO(raw)); image.load()
        profile=profiles[index]; dims=SUPVAN if profile=='supvan' else LETTER
        label_mm=dims['label_mm'] if profile=='supvan' else [documents[index]['page']['widthMm'],documents[index]['page']['heightMm']]
        expected=(round(label_mm[0]*dims['dpi']/25.4),round(label_mm[1]*dims['dpi']/25.4))
        if image.size!=expected or image.width*image.height>MAX_PIXELS: raise ValueError('Renderer returned unexpected image dimensions')
        qr_content=next((e.get('content') for e in documents[index].get('elements',[]) if e.get('type')=='qr' and e.get('visible',True)),None)
        if qr_content:
            if qr_content=='{{item_path}}':qr_content=documents[index].get('variables',{}).get('item_path')
            if not isinstance(qr_content,str) or not re.fullmatch(r'/item/[0-9a-fA-F-]{36}',qr_content):raise ValueError('QR must resolve to one native item URL')
        if profile=='supvan':
            gray=image.convert('L'); gray=gray.point(lambda p: 0 if p<128 else 255, mode='L')
            stream=io.BytesIO(); gray.save(stream,format='PNG',optimize=False); raw=stream.getvalue()
        else:
            rgb=image.convert('RGB');stream=io.BytesIO();rgb.save(stream,format='PNG',optimize=False);raw=stream.getvalue()
        # Reopen the exact bytes that will be stored. SUPVAN gets one final QR decode
        # after canonical thresholding; paper output remains RGB.
        canonical=Image.open(io.BytesIO(raw));canonical.load()
        if qr_content:
            decoded=_decode_qr_l(canonical.convert('L'))
            if decoded!=qr_content:raise ValueError('Canonical label QR content did not match the bound item URL: '+repr(decoded))
        outputs.append({'png':raw,'width':image.width,'height':image.height,'sha256':hashlib.sha256(raw).hexdigest(),'warnings':row.get('warnings',[])})
    if time.monotonic() - request_started >= timeout: raise TimeoutError('Label rendering exceeded the 20-second request budget')
    return outputs


def render_document(document, profile, *, asset_root=None, timeout=20):
    return render_documents([document],[profile],asset_root=asset_root,timeout=timeout)[0]


def render_paper_sheet(reviews, geometry, *, asset_root=None, timeout=20):
    request_started=time.monotonic()
    from PIL import Image
    import base64 as b64
    if not isinstance(reviews,list) or not 1<=len(reviews)<=36: raise ValueError('Select 1 to 36 reviewed labels')
    if not isinstance(geometry,dict): raise ValueError('Invalid paper geometry')
    page=geometry.get('page_mm'); labels=geometry.get('label_mm'); margin=geometry.get('margin_mm'); gap=geometry.get('gap_mm')
    numbers=(page or [])+(labels or [])+[margin,gap,geometry.get('dpi',300)]
    if len(page or [])!=2 or len(labels or [])!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in numbers): raise ValueError('Paper geometry must be finite')
    if page!=[215.9,279.4] or geometry.get('dpi',300)!=300 or any(x<=0 for x in labels) or type(geometry.get('cut_guides')) is not bool: raise ValueError('Paper slots must exactly match Letter label reviews; scaling is not allowed')
    if margin<0 or gap<0: raise ValueError('Paper margin and gap must be nonnegative')
    normalized=[]
    aggregate=0
    for review in reviews:
        if review.get('profile')!='letter' or review.get('label_mm')!=labels or review.get('dpi')!=300: raise ValueError('Review profile or dimensions do not match paper slots')
        raw=review.get('png')
        if not isinstance(raw,(bytes,bytearray)): raise ValueError('Invalid reviewed PNG')
        aggregate+=len(raw)
        if aggregate>MAX_TRUSTED_INPUT: raise ValueError('Reviewed PNG input exceeds 32 MiB')
        if review.get('sha256')!=hashlib.sha256(raw).hexdigest(): raise ValueError('Reviewed PNG hash mismatch')
        image=Image.open(io.BytesIO(raw)); image.load()
        expected=(round(labels[0]*300/25.4),round(labels[1]*300/25.4))
        if image.format!='PNG' or image.size!=expected: raise ValueError('Reviewed image dimensions do not match paper slots')
        normalized.append({'png_base64':b64.b64encode(raw).decode(),'width':image.width,'height':image.height})
    payload={'asset_root':str(_check_manifest(asset_root or DEFAULT_ASSET_ROOT)), 'trusted_sheet':True, 'sheet':{'reviews':normalized,'geometry':{**geometry,'dpi':300}}}
    remaining=timeout-(time.monotonic()-request_started)
    if remaining<=0:raise TimeoutError('Paper rendering exceeded the 20-second request budget')
    result=_run(payload,remaining)['sheet_result']
    if not isinstance(result,dict) or not 1<=len(result.get('pages',[]))<=2: raise ValueError('Paper output must contain at most two pages')
    pages=[]; total=0
    for page_result in result['pages']:
        raw=b64.b64decode(page_result['png_base64'],validate=True)
        im=Image.open(io.BytesIO(raw)); im.load()
        if im.width*im.height>MAX_PIXELS or max(im.size)>MAX_DIMENSION: raise ValueError('Paper page exceeds renderer pixel limits')
        rgb=im.convert('RGB');stream=io.BytesIO();rgb.save(stream,format='PNG',optimize=False);raw=stream.getvalue()
        encoded=b64.b64encode(raw).decode();total+=len(encoded)+22+160
        if total>MAX_OUTPUT: raise ValueError('Paper output exceeds 16 MiB')
        pages.append({'image':'data:image/png;base64,'+encoded,'width':rgb.width,'height':rgb.height,'sha256':hashlib.sha256(raw).hexdigest()})
    out_geometry={k:v for k,v in result['geometry'].items()}
    if time.monotonic()-request_started>=timeout:raise TimeoutError('Paper rendering exceeded the 20-second request budget')
    return {'pages':pages,'geometry':out_geometry}


if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='--child':
    try: _child(json.load(sys.stdin))
    except Exception as error:
        sys.stderr.write(type(error).__name__+': '+str(error))
        raise SystemExit(1)
