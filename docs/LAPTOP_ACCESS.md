# Laptop editing

Open **Workshop Editor** on the laptop desktop. Keep its connection window open while editing; press Enter there to disconnect after saving. The launcher uses the laptop's existing authorized SSH key, with host verification and encrypted forwarding. The companion and Homebox remain bound to loopback on the Pi.

## Direct cable

Connect an Ethernet cable between the Pi and laptop. Leave the laptop Ethernet adapter on automatic IP/DNS. The Pi provides a 10.77.0.x address; the Pi itself is 10.77.0.1. The launcher tries this address first, then the Pi's Wi-Fi address 192.168.1.61. No internet is required for editing.

The dedicated Pi Ethernet profile is intended for the laptop cable. Do not connect that port to a shared router LAN while this profile is active: it supplies DHCP. To restore ordinary router Ethernet, run on the Pi:

```sh
sudo nmcli connection modify 'Homebox laptop cable' connection.autoconnect no
sudo nmcli connection up netplan-eth0
```

To restore laptop mode:

```sh
sudo nmcli connection modify 'Homebox laptop cable' connection.autoconnect yes
sudo nmcli connection up 'Homebox laptop cable'
```

## Editing

At 1100px or wider, Workshop shows the map and properties beside each other. Click **Edit layout**, select or drag objects, type into forms, then **Save layout**. Geometry edits stay unsaved until confirmed. Storage and inventory actions use the same native Homebox data as the touchscreen. Use **Manual** for codes when no camera is available. Laptop camera scanning uses the laptop camera, not the Pi webcam.

## Another Windows laptop

Copy deploy/Open-Workshop.ps1 to it and install an individually authorized SSH key at ~/.ssh/id_rsa. First connect normally to user@192.168.1.61 and verify the Pi host key. The launcher uses that saved host identity for the direct address too. Run the script with PowerShell. Do not copy private keys between people. Windows OpenSSH Client is required.

## Verification

Browser tests cover wide-screen panel placement, physical keyboard entry, unchanged saved layout, and the existing 800x480 touch gestures. A physical laptop-to-Pi cable check is still required. Access through SSH inherits the user's existing temporarily open Admin permissions; a separate web login is unnecessary for this tunnel-only setup.
