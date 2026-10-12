#!/usr/bin/env python3
"""Rasterize the project's own SVG with the existing browser and Pillow."""
import io
import pathlib
import sys
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'work/hardware/python'))
from PIL import Image
from playwright.sync_api import sync_playwright
folder = root/'kiosk/branding'
logo = (folder/'caci-create.svg').read_text()
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width':512,'height':512}, device_scale_factor=1)
    page.set_content('<style>body{margin:0;width:512px;height:512px;display:grid;place-items:center;background:#f1f5f9;color:#22557d}svg{width:360px}</style>'+logo)
    image = Image.open(io.BytesIO(page.screenshot())).convert('RGBA')
    for name, size in [('pwa-192x192.png',192),('pwa-512x512.png',512),('apple-touch-icon.png',180)]:
        image.resize((size,size),Image.Resampling.LANCZOS).save(folder/name)
    image.resize((48,48),Image.Resampling.LANCZOS).save(folder/'favicon.ico',sizes=[(16,16),(32,32),(48,48)])
    browser.close()
# The standalone mark remains transparent; browser icons have a safe mask margin.
body = logo[logo.index('>')+1:logo.rindex('</svg>')]
(folder/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" fill="currentColor" style="color:#22557d"><rect width="128" height="128" rx="24" fill="#f1f5f9"/><g transform="translate(18 18) scale(.72)">'+body+'</g></svg>\n')
(folder/'mask-icon.svg').write_text(logo)
print('Rendered C-Crate browser icons from the original drone/crate SVG.')
