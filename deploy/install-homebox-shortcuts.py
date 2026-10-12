from pathlib import Path
import shutil,stat,urllib.request
root=Path('/home/user/Desktop/inventory-system');desktop=Path.home()/'Desktop'
browser=shutil.which('chromium') or shutil.which('chromium-browser')
assert browser,'Chromium is required'
def desktop_entry_exec(text):
    in_entry=False
    commands=[]
    for line in text.splitlines():
        if line.startswith('['): in_entry=line=='[Desktop Entry]'
        elif in_entry and line.startswith('Exec='): commands.append(line[5:])
    return commands
def regular_or_missing(path):
    try: mode=path.lstat().st_mode
    except FileNotFoundError: return False
    if not stat.S_ISREG(mode): raise OSError(f'Refusing non-regular shortcut entry: {path}')
    return True
def install_shortcut(path,legacy_name,content,exec_command):
    legacy=desktop/legacy_name
    legacy_exists=regular_or_missing(legacy)
    path_exists=regular_or_missing(path)
    if legacy_exists and desktop_entry_exec(legacy.read_text())==[exec_command] and not path_exists:
        legacy.rename(path)
        path_exists=True
    if path_exists and desktop_entry_exec(path.read_text())!=[exec_command]:
        raise OSError(f'Refusing to overwrite an unrelated shortcut: {path}')
    path.write_text(content)
    path.chmod(0o755)
launcher=desktop/'C-Crate.desktop'
install_shortcut(launcher,'Homebox.desktop',f'[Desktop Entry]\nType=Application\nName=C-Crate\nComment=Open C-Crate inventory\nExec={browser} --user-data-dir=/home/user/.config/homebox-browser --new-window http://127.0.0.1:17745\nIcon={root}/kiosk/branding/pwa-512x512.png\nTerminal=false\n',f'{browser} --user-data-dir=/home/user/.config/homebox-browser --new-window http://127.0.0.1:17745')
guide=root/'docs/homebox-access.html'
assert guide.is_file(), 'The current connection guide is required'
help_launcher=desktop/'C-Crate Connection Guide.desktop'
install_shortcut(help_launcher,'Homebox Connection Guide.desktop','[Desktop Entry]\nType=Application\nName=C-Crate Connection Guide\nComment=How to open C-Crate on the Pi or another device\nExec=xdg-open /home/user/Desktop/inventory-system/docs/homebox-access.html\nIcon=help-browser\nTerminal=false\n','xdg-open /home/user/Desktop/inventory-system/docs/homebox-access.html')
assert urllib.request.urlopen('http://127.0.0.1:17745',timeout=8).status==200
print('C-Crate responds; desktop application and connection-guide shortcuts installed.')
