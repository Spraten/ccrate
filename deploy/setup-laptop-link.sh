#!/bin/sh
set -eu
# Run with sudo. Never change wlan0 or replace the existing Ethernet profile.
if ! command -v dnsmasq >/dev/null 2>&1; then
  apt-get update
  apt-get install -y dnsmasq-base
fi
if ! nmcli -t -f NAME connection show | grep -qx 'Homebox laptop cable'; then
  nmcli connection add type ethernet ifname eth0 con-name 'Homebox laptop cable' ipv4.method shared ipv4.addresses 10.77.0.1/24 ipv6.method disabled
fi
nmcli connection modify 'Homebox laptop cable' connection.autoconnect yes connection.autoconnect-priority 50 ipv4.never-default yes
nmcli connection up 'Homebox laptop cable'
printf '%s\n' 'Direct laptop connection enabled at 10.77.0.1. Wi-Fi stays available.'
