#!/bin/sh
set -eu
cd /home/user/Desktop/inventory-system
CODEX_BIN=/home/user/.local/bin/codex
if ! "$CODEX_BIN" login status >/dev/null 2>&1; then
    printf '%s\n' 'Sign in using the link and code below from your phone or computer.'
    "$CODEX_BIN" login --device-auth
fi
exec "$CODEX_BIN"
