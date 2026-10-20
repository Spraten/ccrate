#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORK="$ROOT/work"
TOOLS="$WORK/toolchains"
DATA="$HOME/.local/share/ccrate-local-test/data"
SERVICE_DIR="$HOME/.config/systemd/user"

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "This setup path targets the Raspberry Pi aarch64 system; detected $(uname -m)." >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo "Install sudo first, then rerun this script." >&2
  exit 1
fi

DPKG_AUDIT="$(sudo dpkg --audit)"
if [[ -n "$DPKG_AUDIT" ]]; then
  printf '%s\n' "$DPKG_AUDIT" >&2
  echo "Package installation is already interrupted; refusing to start another apt run." >&2
  exit 1
fi

echo "Installing build and runtime packages (Node, Go, QR and barcode support)..."
sudo apt-get update
sudo apt-get install -y nodejs golang-go python3-pil python3-cryptography python3-qrcode python3-zxing-cpp

git -C "$ROOT" submodule update --init --recursive
mkdir -p "$TOOLS" "$WORK"
printf '/usr\n' > "$TOOLS/node-path.txt"
printf '/usr\n' > "$TOOLS/go-path.txt"

echo "Installing the pinned pnpm package manager into the project toolchain directory..."
python3 "$ROOT/deploy/install-pnpm.py" --destination "$TOOLS/pnpm"
PNPM="$TOOLS/pnpm/node_modules/.bin/pnpm"
mkdir -p "$TOOLS/oxc-wasi"
(
  cd "$TOOLS/oxc-wasi"
  "$PNPM" add --ignore-scripts @oxc-parser/binding-wasm32-wasi@0.72.3
)
# The ARM build uses this pinned WASI fallback instead of an incompatible native parser binary.

echo "Preparing and building the Homebox frontend..."
UI_BUILD="$(mktemp -d "$WORK/homebox-ui-build.XXXXXX")"
trap 'rm -rf -- "$UI_BUILD"' EXIT
PATH="/usr/bin:$PATH" python3 "$ROOT/deploy/build-homebox-ui.py" \
  --toolchain-root "$TOOLS" --upstream-root "$ROOT" --build-root "$UI_BUILD"
mkdir -p "$WORK/homebox-ui-current"
cp -a "$UI_BUILD/.output/public/." "$WORK/homebox-ui-current/"

echo "Building the native Homebox backend (Go will fetch the module-required Go 1.26 toolchain)..."
python3 "$ROOT/deploy/build-homebox-backend.py"

echo "Building the standalone label editor..."
python3 "$ROOT/deploy/build-label-ui.py" --source-root "$ROOT" \
  --output "$WORK/label-ui-build" --toolchain-root "$TOOLS"

mkdir -p "$DATA" "$SERVICE_DIR"
chmod 700 "$DATA"
echo "Installing the Python label-renderer runtime into the private app data directory..."
python3 -m pip install --no-cache-dir --disable-pip-version-check --target \
  "$WORK/hardware/python" 'playwright==1.63.0'
cat > "$SERVICE_DIR/ccrate-local-test.service" <<EOF
[Unit]
Description=C-Crate local test app
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=WORKSHOP_LOCAL_TEST=1
Environment=WORKSHOP_LOCAL_TEST_NATIVE=1
Environment=WORKSHOP_ROOT=%h/.local/share/ccrate-local-test/data
Environment=WORKSHOP_CODE_ROOT=$ROOT
Environment=WORKSHOP_NATIVE_BINARY=$WORK/homebox-backend-build/homebox
Environment=HOMEBOX_UI_ROOT=$WORK/homebox-ui-current
Environment=WORKSHOP_LABEL_ASSET_ROOT=$WORK/label-ui-build
Environment=WORKSHOP_NODE=/usr/bin/node
Environment=WORKSHOP_PLAYWRIGHT_PYTHON=$WORK/hardware/python
UMask=0077
ExecStart=/usr/bin/python3 $ROOT/deploy/local-test.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ccrate-local-test.service

echo "Waiting for the local app to become ready..."
python3 - <<'PY'
import time
import urllib.error
import urllib.request

url = 'http://127.0.0.1:17745/api/v1/status'
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                break
    except (urllib.error.URLError, TimeoutError, OSError):
        time.sleep(1)
else:
    raise SystemExit('App did not become ready. Inspect: systemctl --user status ccrate-local-test.service')
PY

ACCOUNT="$DATA/work/baseline/test-account.json"
if [[ ! -f "$ACCOUNT" ]]; then
  echo "App is ready but its generated account file is missing: $ACCOUNT" >&2
  exit 1
fi
mkdir -p "$HOME/Desktop"
install -m 600 "$ACCOUNT" "$HOME/Desktop/ccrate-credentials.json"
echo "C-Crate is running at http://localhost:17745"
echo "Generated sign-in credentials are on the Desktop: ccrate-credentials.json"
echo "Service controls: systemctl --user status|restart|stop ccrate-local-test.service"
