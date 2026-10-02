#!/bin/sh
set -eu
# Temporary access for the hardware proof; expires on unplug/reboot.
# Refuse unrelated hidraw devices.
found=0
for device in /dev/hidraw*; do
  [ -e "$device" ] || continue
  name=$(basename "$device")
  if grep -q '^HID_ID=0003:00001820:0000207F$' "/sys/class/hidraw/$name/device/uevent"; then
    sudo setfacl -m u:user:rw "$device"
    printf 'Temporary printer access granted: %s\n' "$device"
    found=1
  fi
done
[ "$found" -eq 1 ] || { echo 'Matching SUPVAN printer not found; no permissions changed.' >&2; exit 1; }
