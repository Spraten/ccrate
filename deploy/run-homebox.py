#!/usr/bin/env python3
"""Foreground native Homebox for the user service; refuse an empty deployment."""
import os,pathlib,stat,tempfile
ROOT=pathlib.Path(os.environ.get('WORKSHOP_ROOT','/home/user/Desktop/inventory-system'));RUN=ROOT/'work/baseline'
binary=(pathlib.Path(os.environ['WORKSHOP_CODE_ROOT'])/'native/homebox'
        if 'WORKSHOP_CODE_ROOT' in os.environ else ROOT/'work/homebox-bin/homebox')
if os.environ.get('WORKSHOP_FIXTURE_PROCESS')=='1':
    if ('..' in ROOT.parts or ROOT.is_symlink() or ROOT.absolute()!=ROOT.resolve(strict=True)):
        raise RuntimeError('Fixture native launcher refused before marker or store access')
    marker=ROOT/'.fixture-process-token'
    try:
        marker_stat=marker.lstat()
        host=os.environ.get('HOMEBOX_WEB_HOST','')
        port=int(os.environ.get('HOMEBOX_WEB_PORT','0'))
        if ('..' in ROOT.parts or ROOT.is_symlink() or ROOT.absolute()!=ROOT.resolve(strict=True)
                or not ROOT.resolve().is_relative_to(pathlib.Path(tempfile.gettempdir()).resolve())
                or ROOT.stat().st_uid!=os.getuid() or (ROOT.stat().st_mode&0o777)!=0o700
                or not stat.S_ISREG(marker_stat.st_mode) or marker_stat.st_nlink!=1
                or marker_stat.st_uid!=os.getuid() or (marker_stat.st_mode&0o777)!=0o600
                or len(os.environ.get('WORKSHOP_FIXTURE_TOKEN',''))<32
                or marker.read_text()!=os.environ['WORKSHOP_FIXTURE_TOKEN']
                or host!='127.0.0.1' or not 32768<=port<=60999
                or any(key.startswith('HBOX_') and key not in ('HBOX_WEB_HOST','HBOX_WEB_PORT')
                       and not (key == 'HBOX_OPTIONS_ALLOW_REGISTRATION' and os.environ[key] == 'true')
                       for key in os.environ)):
            raise ValueError()
    except (OSError,ValueError,KeyError) as exc:
        raise RuntimeError('Fixture native launcher refused before binary execution: disposable root and loopback endpoint required') from exc
for path in [binary,RUN/'data/homebox.db',RUN/'pepper',RUN/'test-account.json']:
    if not path.is_file():raise RuntimeError('Existing deployment is incomplete; refusing to create a new database')
os.chdir(RUN)
os.environ.update(HBOX_WEB_HOST=os.environ.get('HOMEBOX_WEB_HOST','0.0.0.0'),HBOX_WEB_PORT=os.environ.get('HOMEBOX_WEB_PORT','17745'),HBOX_WEB_WRITE_TIMEOUT='60s',HBOX_STORAGE_PREFIX_PATH='data',HBOX_DATABASE_SQLITE_PATH=str(RUN/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=(RUN/'pepper').read_text(),HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
os.execv(str(binary),[str(binary)])
