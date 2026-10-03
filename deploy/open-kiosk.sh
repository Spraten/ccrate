#!/bin/sh
set -eu
ROOT=/home/user/Desktop/inventory-system
systemctl --user start homebox-native.service homebox-companion.service
for attempt in 1 2 3 4 5; do
  if curl --silent --fail --max-time 2 http://127.0.0.1:17749/ >/dev/null; then break; fi
  sleep 1
done
exec chromium --user-data-dir="$ROOT/work/kiosk-browser" --no-first-run --force-device-scale-factor=1 --start-fullscreen --app=http://127.0.0.1:17749/
