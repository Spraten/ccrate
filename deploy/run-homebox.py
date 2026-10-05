#!/usr/bin/env python3
"""Foreground native Homebox for the user service; refuse an empty deployment."""
import os,pathlib
ROOT=pathlib.Path('/home/user/Desktop/inventory-system');RUN=ROOT/'work/baseline';binary=ROOT/'work/homebox-bin/homebox'
for path in [binary,RUN/'data/homebox.db',RUN/'pepper',RUN/'test-account.json']:
    if not path.is_file():raise RuntimeError('Existing deployment is incomplete; refusing to create a new database')
os.chdir(RUN)
os.environ.update(HBOX_WEB_HOST='0.0.0.0',HBOX_WEB_PORT='17745',HBOX_WEB_WRITE_TIMEOUT='60s',HBOX_STORAGE_PREFIX_PATH='data',HBOX_DATABASE_SQLITE_PATH=str(RUN/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',HBOX_AUTH_API_KEY_PEPPER=(RUN/'pepper').read_text(),HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
os.execv(str(binary),[str(binary)])
