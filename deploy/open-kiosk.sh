#!/bin/sh
set -eu
ROOT=/home/user/Desktop/inventory-system
if ! curl --silent --fail --max-time 2 http://127.0.0.1:17749/ >/dev/null; then
    nohup python3 "$ROOT/deploy/kiosk-server.py" >"$ROOT/work/kiosk-server.log" 2>&1 </dev/null &
    for attempt in 1 2 3 4 5; do
        if curl --silent --fail --max-time 2 http://127.0.0.1:17749/ >/dev/null; then break; fi
        sleep 1
    done
fi
exec chromium --user-data-dir="$ROOT/work/kiosk-browser" --no-first-run --force-device-scale-factor=1 --start-fullscreen --app=http://127.0.0.1:17749/
