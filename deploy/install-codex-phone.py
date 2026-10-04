from pathlib import Path
import shutil
root=Path('/home/user/Desktop/inventory-system')
units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
shutil.copyfile(root/'deploy/codex-remote.service',units/'codex-remote.service')
(root/'deploy/setup-codex-phone.sh').chmod(0o755)
launcher=Path.home()/'Desktop/Codex Phone Setup.desktop'
launcher.write_text('[Desktop Entry]\nType=Application\nName=Codex Phone Setup\nComment=Sign in and prepare experimental Codex remote pairing\nExec=lxterminal --title=Codex-Phone --command=/home/user/Desktop/inventory-system/deploy/setup-codex-phone.sh\nIcon=utilities-terminal\nTerminal=false\n')
launcher.chmod(0o755)
