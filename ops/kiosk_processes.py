"""Identify only this user's main Chromium process for the kiosk profile."""
import os,pathlib,shlex

def is_kiosk_process(raw,profile):
    args=[part.decode('utf-8',errors='replace') for part in raw.split(b'\0') if part]
    # Chromium can rewrite argv into one space-separated process title.
    if len(args)==1:
        try:args=shlex.split(args[0])
        except ValueError:return False
    return bool(args and pathlib.Path(args[0]).name in ('chromium','chromium-browser') and '--user-data-dir='+str(profile) in args and not any(arg.startswith('--type=') for arg in args))

def kiosk_pids(profile,proc=pathlib.Path('/proc')):
    targets=[]
    for entry in proc.iterdir():
        if not entry.name.isdigit():continue
        try:
            if entry.stat().st_uid==os.getuid() and is_kiosk_process((entry/'cmdline').read_bytes(),profile):targets.append(int(entry.name))
        except OSError:continue
    return targets
