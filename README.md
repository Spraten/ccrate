# C-Crate workshop inventory

C-Crate is a local workshop inventory and equipment checkout system built on
[Homebox](https://github.com/sysadminsmedia/homebox). It adds a touch-friendly
Equipment Terminal, workshop workflows, member and badge tools, item history,
room maps, shelf checks, and label design and printing. Homebox remains the
inventory authority; the companion services and browser clients use its native
records and APIs.

## Source layout

- `upstream/homebox/` is the pinned Homebox v0.26.2 Git submodule. Keep changes
  in the overlay and backend extension directories unless an upstream change is
  explicitly intended.
- `homebox-ui/overlay/` contains the native Vue frontend additions;
  `homebox-backend/` contains backend extensions applied by the build script.
- `ops/` and `kiosk/` contain the Python companion service and Equipment
  Terminal client. `desktop/` contains the workshop desktop client.
- `label-ui/` contains the standalone label editor and its pinned vendor source.
- `deploy/` contains build, release, installation, and verification scripts;
  `tests/` contains Python unit and browser-fixture tests; `docs/` contains
  workflow and release notes.
- `work/` and `program-files/runtime/` hold local toolchains, generated builds,
  test evidence, runtime dependencies, operational databases, credentials, and
  private backups. They are local machine state, not source inputs to publish.

## Checkout and local setup

Clone with the upstream submodule initialized:

```sh
git clone --recurse-submodules <repository-url>
cd inventory-system
git submodule update --init --recursive
```

The build scripts target the workshop Pi layout and use private toolchains and
runtime packages under `work/`. A clean checkout therefore needs a compatible
Linux/ARM64 environment, Python 3, the project Python runtime dependencies
(including Pillow, qrcode, and cryptography), and the pinned Go, Node.js, and
pnpm toolchains described in the relevant build documentation. Keep local
credentials, databases, runtime packages, and backups out of source control.
Do not point development or mutation checks at an operational Homebox database.

## Build and test

On the configured Pi, the main build entry points are:

```sh
python3 deploy/build-homebox-ui.py --toolchain-root "$PWD/work/toolchains" --upstream-root "$PWD"
python3 deploy/build-homebox-backend.py
python3 deploy/build-label-ui.py --source-root . --output work/label-ui-build
```

The backend build also requires a built native UI selected at
`work/homebox-ui-current`; it reads the Go toolchain path from
`work/toolchains/go-path.txt`. The UI and label builders use the pinned Node.js
and pnpm toolchains. The label builder expects the project at its configured Pi
path (`/home/user/Desktop/inventory-system`). Builds stage output under `work/`;
they do not by themselves select or deploy a release. See [Label Layouts](docs/LABEL_LAYOUTS.md),
[C-Crate release notes](docs/C_CRATE_RELEASE.md), and the [native UI build notes](homebox-ui/README.md)
for prerequisites and release handling.

Run the Python unit suite with the local hardware runtime on the import path:

```sh
PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -v
```

Some acceptance tests also require local proof artifacts beneath
`work/queue-coordinator`, which are intentionally ignored and are not present
in a clean clone. Browser and native integration verifiers should use disposable
Homebox data as documented by their scripts; do not run live mutation verifiers
against the operational instance.

The services use ports 17745 (Homebox gateway), 17747 (private native backend),
and 17749 (Equipment Terminal) in the configured deployment. Deployment and
live inventory operation require the workshop host setup documented in `docs/`.
