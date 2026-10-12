"""Rediscover the workshop's devices and open fresh read-only connections."""
import os
import pathlib
import subprocess
from labels import probe

CAMERA = pathlib.Path('/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_09C75CAF-video-index0')


def failure(device, error):
    detail = str(error).lower()
    if isinstance(error, subprocess.CalledProcessError):
        detail += str(error.stderr).lower()
    if isinstance(error, PermissionError) or 'permission' in detail or 'access denied' in detail:
        reason = 'permission'
        message = 'The Pi can see the device but cannot open it.'
        steps = ['Reconnect its USB cable, then try again.', 'Ask an administrator to check the device permissions on the Pi.']
    elif isinstance(error, subprocess.TimeoutExpired):
        reason = 'timeout'
        message = 'The device did not respond in time.'
        steps = ['Unplug its USB cable, wait five seconds, then reconnect it.', 'Check its power and try Reconnect again.']
    elif 'busy' in detail:
        reason = 'busy'
        message = 'Another application is using the device.'
        steps = ['Close other camera previews or printer applications.', 'Try Reconnect again. Your draft remains available.']
    elif isinstance(error, FileNotFoundError) or 'connect exactly' in detail or 'not found' in detail:
        reason = 'disconnected'
        message = 'The workshop device was not found.'
        steps = ['Connect the original C920 webcam to the Pi.' if device == 'camera' else 'Turn on the SUPVAN printer and connect its USB cable to the Pi.', 'Check the USB cable and power; wait five seconds, then try Reconnect.']
    else:
        reason = 'not_ready'
        message = 'The device was found but is not ready.'
        steps = (['Close other camera previews.', 'Reconnect the webcam USB cable and try again.'] if device == 'camera' else ['Check the printer power, close its cover and load the label stock.', 'Reconnect the USB cable and try again.'])
    return {'device': device, 'connected': False, 'supported': False, 'reason': reason, 'message': message, 'steps': steps}


def camera_status():
    try:
        if not CAMERA.exists():
            raise FileNotFoundError('Original C920 not found')
        if not os.access(CAMERA, os.R_OK | os.W_OK):
            raise PermissionError('Camera permissions')
        result = subprocess.run(['v4l2-ctl', '-d', str(CAMERA), '--get-ctrl=focus_absolute,focus_automatic_continuous'], check=True, capture_output=True, text=True, timeout=5)
        values = {line.split(':')[0].strip(): int(line.split(':')[1]) for line in result.stdout.splitlines() if ':' in line}
        return {'device': str(CAMERA), 'connected': True, 'supported': True, 'value': values['focus_absolute'], 'mode': 'auto' if values['focus_automatic_continuous'] else 'manual', 'reason': 'ready', 'message': 'The Pi C920 webcam responded.', 'steps': ['Use Reconnect webcam in the scan or photo preview to reopen the browser camera.']}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return failure('camera', error)


def reconnect(device):
    if device == 'camera':
        return camera_status()
    if device != 'printer':
        raise ValueError('Choose camera or printer')
    try:
        material = probe()  # Fresh hidraw discovery and adapter open; never prints.
        return {**material, 'device': 'printer', 'connected': True, 'reason': 'ready', 'message': 'SUPVAN printer reconnected and label stock checked.', 'steps': ['Inspect any unconfirmed output in Recovery before printing another copy.']}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return failure('printer', error)
