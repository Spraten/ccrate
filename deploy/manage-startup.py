from pathlib import Path
root=Path('/home/user/Desktop/inventory-system')
p=root/'deploy/verify-scanning.py';s=p.read_text();start=s.index('for entry in pathlib.Path');end=s.index("base='http://127.0.0.1:17749'")
s=s[:start]+"subprocess.run(['systemctl','--user','restart','homebox-companion.service'],check=True)\nfor attempt in range(40):\n    try:\n        urllib.request.urlopen('http://127.0.0.1:17749/',timeout=1).close();break\n    except OSError:time.sleep(.25)\n"+s[end:];p.write_text(s)
p=root/'deploy/open-kiosk.sh';s=p.read_text();start=s.index('# Keep the UI');end=s.index('exec chromium');s=s[:start]+"systemctl --user start homebox-native.service homebox-companion.service\nfor attempt in 1 2 3 4 5; do\n  if curl --silent --fail --max-time 2 http://127.0.0.1:17749/ >/dev/null; then break; fi\n  sleep 1\ndone\n"+s[end:];p.write_text(s)
folder=Path.home()/'.config/autostart';folder.mkdir(parents=True,exist_ok=True)
(folder/'homebox-kiosk.desktop').write_text('[Desktop Entry]\nType=Application\nName=Equipment Terminal\nExec=/home/user/Desktop/inventory-system/deploy/open-kiosk.sh\nTerminal=false\nX-GNOME-Autostart-enabled=true\n')
print('Managed startup and desktop autostart configured')
