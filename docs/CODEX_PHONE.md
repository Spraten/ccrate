# Codex from your phone

Codex CLI 0.160.0 is installed at /home/user/.local/bin/codex. Personal account authentication is required. On the Pi desktop, open **Codex Phone Setup**. It opens device-code sign-in if needed, enables the user remote service, and requests a short-lived pairing code. Do not store or share codes. The companion kiosk is independent of this service.

The installed CLI exposes experimental `remote-control start`, `stop`, and `pair` commands. Direct phone pairing is not considered verified until your actual mobile client connects. Current official mobile setup documentation instead describes pairing the mobile ChatGPT app with an awake Windows/Mac desktop host, then connecting that host to the Pi by SSH. Use that documented route if the phone has no compatible manual-code pairing control.

Official references:
- https://learn.chatgpt.com/docs/remote-connections
- https://learn.chatgpt.com/docs/developer-commands?surface=cli

For the documented desktop route: desktop Settings → Connections → Control this PC/Mac → Set up/Add; scan its QR using the phone and complete account verification. Add an SSH connection to `user@192.168.1.61` on the desktop and open `/home/user/Desktop/inventory-system`. The Windows/Mac host must remain awake, online, and signed in.

For CLI access from an SSH terminal already authorized on the phone, connect to the Pi on the same LAN and run:
```
cd ~/Desktop/inventory-system
~/.local/bin/codex
```
Use `~/.local/bin/codex resume` to resume a saved Pi conversation. Do not expose SSH to the internet or copy somebody else's private key. Away-from-home SSH needs a separately configured private network.

The user service `codex-remote.service` starts the remote daemon at boot only after authentication exists. Internet access and a valid account are required. It retains normal Codex approval behavior. No public inbound browser endpoint is opened by this setup.

To check or stop it:
```
systemctl --user status codex-remote.service
systemctl --user restart codex-remote.service
systemctl --user disable --now codex-remote.service
```

Tomorrow, start a project chat with: “Read AGENTS.md and docs/CONTINUE_TOMORROW.md, inspect git status, and continue the equipment project.”
