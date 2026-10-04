#!/usr/bin/env python3
"""Local, credential-free network and service readiness screen."""
import argparse,json,subprocess,time,urllib.request

def run(*args):
    return subprocess.run(args,capture_output=True,text=True,timeout=12)

def addresses():
    result=run('ip','-j','-4','address','show','scope','global')
    if result.returncode:raise RuntimeError('Could not read network addresses')
    found=[]
    for interface in json.loads(result.stdout):
        name=interface['ifname']
        if name=='lo' or name.startswith(('docker','br-','veth','virbr')):continue
        if 'UP' not in interface.get('flags',[]):continue
        for address in interface.get('addr_info',[]):
            if address.get('family')=='inet':found.append((name,address['local']))
    return found

def healthy(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=3) as response:return response.status==200
    except (OSError,ValueError):return False

def ensure(name,port):
    active=run('systemctl','--user','is-active',name).stdout.strip()=='active'
    if not active:
        print('Starting '+name+'…',flush=True)
        result=run('systemctl','--user','start',name)
        if result.returncode:
            print('Could not start '+name+'. Check Admin system status or ask the maintainer.')
            return False
    for _ in range(4):
        if healthy(port):return True
        time.sleep(.5)
    return False

def show():
    print('\nEquipment connection check\n'+'='*48,flush=True)
    try:network=addresses()
    except (RuntimeError,ValueError,subprocess.SubprocessError):network=[];print('Network check failed. Check the Pi network menu.')
    if network:
        print('Network connected:')
        for interface,address in network:
            label='Direct laptop cable' if address=='10.77.0.1' else 'Wi-Fi' if interface.startswith(('wl','wlan')) else 'Network'
            print(f'  {label}: {address} ({interface})')
    else:print('No usable network address. Join Wi-Fi using the Pi network menu, then press Enter here.')
    print('\nChecking applications…',flush=True)
    native=ensure('homebox-native.service',17745)
    companion=ensure('homebox-companion.service',17749)
    print('Homebox: '+('READY' if native else 'NOT RESPONDING'))
    print('Equipment Terminal: '+('READY' if companion else 'NOT RESPONDING'))
    if native:
        print('\nOn this Pi, you can connect via:\n  http://127.0.0.1:17745\n  Sign in with your Homebox email and password.')
    if native and network:
        print('\nOn your configured Windows laptop:')
        print('  1. Join the same Wi-Fi or connect the direct laptop cable.')
        print('  2. Open Workshop Editor; keep its connection window open.')
        print('  3. Open http://127.0.0.1:17745 in the laptop browser.')
        print('  If the shortcut cannot find this Pi, run its script with:')
        for _,address in network:print(f'    .\\Open-Workshop.ps1 -PiAddress {address}')
        print('\nOther computers with authorized SSH access can connect via:')
        address=next((a for _,a in network if a!='10.77.0.1'),network[0][1])
        print(f'  ssh -N -L 127.0.0.1:17745:127.0.0.1:17745 user@{address}')
        print('  Keep that terminal open; browse to http://127.0.0.1:17745.')
        print('\nThe laptop must have authorized SSH access. Homebox is not directly')
        print('available at the Pi IP:17745; the tunnel supplies the laptop address.')
    if not native or not companion:
        print('\nA service is not ready. Refresh once; if it still fails, ask the')
        print('maintainer to inspect the service. Do not repeat uncertain transactions.')
    print('\nLocal Homebox does not require internet. Codex remote access does.')
    print('Connection from outside this network needs separate remote access.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    while True:
        try:show()
        except (OSError,subprocess.SubprocessError) as error:print('Could not complete the check: '+str(error))
        if args.once:break
        try:
            if input('\nEnter = check again | q + Enter = close: ').strip().lower()=='q':break
        except (EOFError,KeyboardInterrupt):break
