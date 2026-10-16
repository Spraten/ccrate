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

def healthy(port, path='/'):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=3) as response:return response.status==200
    except (OSError,ValueError):return False

def ensure(name,port,path='/'):
    active=run('systemctl','--user','is-active',name).stdout.strip()=='active'
    if not active:
        print('Starting '+name+'…',flush=True)
        result=run('systemctl','--user','start',name)
        if result.returncode:
            print('Could not start '+name+'. Check Admin system status or ask the maintainer.')
            return False
    for _ in range(4):
        if healthy(port,path):return True
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
    native=ensure('homebox-native.service',17747,'/api/v1/status')
    gateway=ensure('homebox-workshop-gateway.service',17745)
    native=native and gateway
    companion=ensure('homebox-companion.service',17749,'/api/session')
    print('C-Crate: '+('READY' if native else 'NOT RESPONDING'))
    print('Companion API: '+('READY' if companion else 'NOT RESPONDING'))
    if native:
        print('\nOn this Pi, you can connect via:\n  http://127.0.0.1:17745\n  Sign in with your C-Crate email and password.')
    if native and network:
        print('\nFrom a laptop, phone, or tablet on the same network:')
        for interface,address in network:
            label='Direct Ethernet cable' if address=='10.77.0.1' else 'Same Wi-Fi/network'
            print(f'  {label}: http://{address}:17745')
        print('  Open the matching URL in your browser. No script or SSH tunnel is needed.')
        print('  Sign in with your own C-Crate email and password.')
        print('  Use Refresh in your browser after edits to see current inventory.')
        print('\nIf the page does not load, check that both devices are on the same')
        print('network. Guest Wi-Fi may block device-to-device connections.')
        print('\nIn C-Crate, use Collection → Members for badges or the Workshop sidebar for tools.')
    if not native or not companion:
        print('\nA service is not ready. Refresh once; if it still fails, ask the')
        print('maintainer to inspect the service. Do not repeat uncertain transactions.')
    print('\nLocal C-Crate does not require internet. Codex remote access does.')
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
