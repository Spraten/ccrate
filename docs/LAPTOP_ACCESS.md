# Laptop editing

Open **http://PI_ADDRESS:17745** from a laptop or desktop on the Pi’s network and sign in to CACI-Create. The workshop actions use CACI-Create’s sidebar, collection selection and theme.

- **Collection → Members:** each row shows **User, Email, Kiosk Badge and Items**, with a saved profile picture or an automatically generated avatar that stays the same for that person in both interfaces. Choose **Manage badges → Issue badge**, confirm issuance, then **Print one badge**. **Reprint badge** prints another copy of an existing active badge. Older badges whose QR was not saved offer an explicit replacement first; replacing disables the old badge. **Manage badges** also contains revocation and **Allow management**. Revoke lost badges promptly.
- **Members → X items checked out:** expand a person’s count to see item photos, the checkout date and how long each item has been out. Open an item or its loan history from the dropdown. Counts refresh automatically while visible and through **Refresh members & items**.
- **Collection → Members → Manage users → New user:** create a person by name alone. Email is optional; no password or PIN is required. Manage their name, picture and optional details through **Manage profile**. Equipment Terminal offers the same profiles under **Admin → Manage users**. Duplicate names have distinct user IDs, and editing preserves badges and loans. **Collection → Invites** still supports existing web-account registration.
- **Home → Checked-out items:** see the count, items and borrowers for the selected collection. Choose **View loan** for an item's history or **View all loans** for the full list. The section refreshes automatically while visible; its refresh button updates it immediately.
- **Item details:** see borrowing status, then use **Loans & return notes** for history, condition reviews and administrative returns.
- **Nested storage:** use **Add inside** on an item or location, or select **Inside (optional)** in its creation/edit form. Locations and items can contain other locations and items at any depth. Leave the parent empty for a top-level record; self and descendant parents are excluded. For example: Storage Room → the Cage → shelf → bin, or a vacuum directly inside an office.
- **Item or location → Labels → Print from Browser:** the existing label dialog also offers **Print one label on Pi** for managers.
- **Reconnect devices:** choose **Workshop → System → Reconnect printer / Reconnect webcam**, or **Equipment Terminal → Admin → System status & backup**. The result explains cable, power, permission, stock or busy-device steps. Scan and photo previews also have **Reconnect webcam**, preserving the draft and photos. Printer dialogs offer **Reconnect printer** without repeating the print. Finish any uncertain print in Recovery before printing another copy.
- **Workshop** in the CACI-Create sidebar: open loans, storage drawing, imports, label queue, recovery and system status. Managers see the management pages; other members can view loans and storage.
- **Equipment Terminal** in the sidebar opens the terminal on port 17749. Its desktop header links back to CACI-Create. Both interfaces share inventory, members, badges, loans, storage and the Pi printer.

A personal badge identifies a kiosk user. Existing desktop web accounts keep their CACI-Create sign-in. A new name-only person is badge-only; optional web passwords and QR-plus-PIN verification are planned for later. See [Manage users](USER_MANAGEMENT.md).

The existing **Workshop Editor** desktop launcher is still available. Keep its SSH connection window open while editing; press Enter there to disconnect after saving. It uses the laptop's authorized SSH key and verified Pi host identity.

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

At 1100px or wider, Workshop shows the map and properties beside each other. Click **Edit layout**, select or drag objects, type into forms, then **Save layout**. Geometry edits stay unsaved until confirmed. Storage and inventory actions use the same native CACI-Create data as the touchscreen. Use **Manual** for codes when no camera is available. Laptop camera scanning uses the laptop camera, not the Pi webcam.

## Another Windows laptop

Copy deploy/Open-Workshop.ps1 to it and install an individually authorized SSH key at ~/.ssh/id_rsa. First connect normally to user@192.168.1.61 and verify the Pi host key. The launcher uses that saved host identity for the direct address too. Run the script with PowerShell. Do not copy private keys between people. Windows OpenSSH Client is required.

## Verification

Browser tests cover wide-screen panel placement, physical keyboard entry, unchanged saved layout, and the existing 800x480 touch gestures. A physical laptop-to-Pi cable check is still required. Access through SSH inherits the user's existing temporarily open Admin permissions; a separate web login is unnecessary for this tunnel-only setup.
