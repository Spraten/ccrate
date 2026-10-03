#!/usr/bin/env python3
"""Start the existing isolated Homebox demo; never seed or register accounts."""
import fcntl, json, os, pathlib, subprocess, time, urllib.request

ROOT=pathlib.Path('/home/user/Desktop/inventory-system')
RUN=ROOT/'work/baseline'
BINARY=ROOT/'work/homebox-bin/homebox'
BASE='http://127.0.0.1:17745'

def ready():
    try:
        with urllib.request.urlopen(BASE+'/api/v1/status',timeout=2) as response:
            return response.status==200 and isinstance(json.load(response),dict)
    except (OSError,ValueError):return False

def main():
    required=[BINARY,RUN/'data/homebox.db',RUN/'pepper',RUN/'test-account.json']
    if not all(p.is_file() for p in required):
        raise RuntimeError('Existing Homebox demo files are missing. Refusing to create a new database.')
    with (RUN/'startup.lock').open('a') as startup_lock:
        fcntl.flock(startup_lock,fcntl.LOCK_EX)
        if ready():return
        env=dict(os.environ,HBOX_WEB_HOST='127.0.0.1',HBOX_WEB_PORT='17745',
            HBOX_STORAGE_PREFIX_PATH='data',
            HBOX_DATABASE_SQLITE_PATH=str(RUN/'data/homebox.db')+'?_pragma=busy_timeout=999&_pragma=journal_mode=WAL&_fk=1&_time_format=sqlite',
            HBOX_AUTH_API_KEY_PEPPER=(RUN/'pepper').read_text(),
            HBOX_OPTIONS_GITHUB_RELEASE_CHECK='false',HBOX_OPTIONS_ALLOW_ANALYTICS='false')
        with (RUN/'homebox.log').open('ab') as log:
            proc=subprocess.Popen([str(BINARY)],cwd=RUN,env=env,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (RUN/'homebox.pid').write_text(str(proc.pid))
        until=time.monotonic()+20
        while time.monotonic()<until:
            if proc.poll() is not None:raise RuntimeError('Homebox could not start; inspect its local log.')
            if ready():return
            time.sleep(.25)
        proc.terminate()
        proc.wait(timeout=10)
        raise RuntimeError('Homebox startup timed out.')

if __name__=='__main__':main()
