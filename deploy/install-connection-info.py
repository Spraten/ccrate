from pathlib import Path
desktop=Path.home()/'Desktop';root=desktop/'inventory-system'
for name in ('Homebox.desktop','Homebox Connection Guide.desktop'):
    (desktop/name).unlink(missing_ok=True)
launcher=desktop/'Connection Info.desktop'
launcher.write_text('[Desktop Entry]\nType=Application\nName=Connection Info\nComment=Check network and Homebox, then show laptop connection instructions\nExec=lxterminal --title=Connection-Info --command="python3 /home/user/Desktop/inventory-system/deploy/connection-info.py"\nIcon=network-workgroup\nTerminal=false\n')
launcher.chmod(0o755)
print('Removed the two Homebox shortcuts; installed Connection Info.')
