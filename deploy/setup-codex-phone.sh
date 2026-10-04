#!/bin/sh
set -eu
cd /home/user/Desktop/inventory-system
CODEX_BIN=/home/user/.local/bin/codex
if ! "$CODEX_BIN" login status >/dev/null 2>&1; then
    printf '%s\n' 'Sign in to your own account using the link and code below.'
    "$CODEX_BIN" login --device-auth
fi
systemctl --user enable codex-remote.service
systemctl --user restart codex-remote.service
printf '%s\n' 'Remote daemon started. Pairing is experimental; use the code only in your own trusted client.'
"$CODEX_BIN" remote-control pair
printf '%s\n' 'Project: /home/user/Desktop/inventory-system' 'Read docs/CONTINUE_TOMORROW.md when starting a new project chat.' 'Press Enter to close this window; the daemon remains running.'
read answer
