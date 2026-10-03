# Codex CLI on the Raspberry Pi

Installed 3 October 2026 using the official standalone installer linked from https://learn.chatgpt.com/docs/codex/cli. ARM64 musl package, codex-cli 0.160.0. Installer verifies the release digest. Executable: /home/user/.local/bin/codex. Installed for user, with PATH added by installer to ~/.bashrc. Node/npm and sudo were not needed.

Tap **Codex CLI — Equipment Project** on the desktop to open LXTerminal in /home/user/Desktop/inventory-system. The launcher starts device-code sign-in if needed, then opens Codex. CLI text entry requires a keyboard or an SSH terminal; the kiosk's web touch keyboard does not extend to desktop terminal apps.

From Windows PowerShell:

```powershell
ssh -t -i C:\Users\nisse\.ssh\id_rsa -o HostKeyAlias=192.168.1.61 user@192.168.1.62 "cd ~/Desktop/inventory-system && ~/.local/bin/codex"
```

For remote sign-in: `~/.local/bin/codex login --device-auth`. Complete the displayed URL/code in a browser. Check with `~/.local/bin/codex login status`. Do not share or commit ~/.codex/auth.json. No credentials were copied from this PC to the Pi.

Codex needs internet access for OpenAI model calls. It is a development tool separate from the offline kiosk runtime. The kiosk continues to operate without internet and no kiosk services were changed by this installation. Default CLI permission prompts remain in place.

Verified: executable version/help, shell launcher syntax, terminal availability. Authenticated model invocation remains dependent on the user's account sign-in. Updates may be installed with the official standalone installer; record the resulting exact version afterward.
