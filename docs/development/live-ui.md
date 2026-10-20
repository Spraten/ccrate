# Live UI development

## Scope: local development, not Pi live-source mode

This workflow provides hot reload for the C-Crate frontend in the isolated
local-test stack. It does **not** put the installed Pi into source or live
development mode. The Pi continues to serve the compiled frontend selected by
its active release; updating the Pi still follows the normal package, bundle,
compatibility-check, and release-activation path documented in the README.

Python companion/API changes do not use Nuxt hot reload. In local testing, the
companion must be restarted through its owning local-test service after those
changes. This guide does not configure or expose a development server on the
operational Pi.

The local development UI runs from `work/homebox-ui-dev`. It uses the pinned
Homebox frontend, C-Crate patches, overlays, and frontend lockfile prepared by
`deploy/build-homebox-ui.py`. The workspace persists across restarts, including
`node_modules`, `.nuxt`, and `.output`.

## First startup

The current `ccrate-local-test.service` runs `deploy/local-test.py`, which
enables live UI by default. On startup it prepares the persistent workspace,
starts the native server and companion, starts Nuxt on `127.0.0.1:17751`, waits
for Nuxt to answer, and then starts the gateway at `http://localhost:17745`.
The gateway receives `WORKSHOP_UI_DEV_PORT=17751` only in this local stack. Its
`HOMEBOX_UI_ROOT` continues to point at the static fallback. Other launchers
and deployment configurations continue to use their static UI roots.

For a standalone UI development session from the repository root, run:

```sh
python3 deploy/dev-homebox-ui.py prepare
python3 deploy/dev-homebox-ui.py serve
```

`prepare` creates the workspace and installs pinned dependencies through the
existing Node and pnpm toolchain in `work/toolchains`. It installs only when the
workspace has no installed packages or the frontend lockfile changes. `serve`
also prepares the workspace, so a supervisor can start that single command.
Nuxt listens on `127.0.0.1:17751` by default. Set `WORKSHOP_UI_DEV_HOST` and
`WORKSHOP_UI_DEV_PORT` to change its bind address and port for a standalone
`serve` run. The gateway always connects to `127.0.0.1` at its configured
`WORKSHOP_UI_DEV_PORT`, so a standalone server used with that gateway must
accept loopback connections on the matching port. The local-test supervisor
uses the fixed loopback address and port `127.0.0.1:17751`.

## Editing and restarting

Edit C-Crate UI files under `homebox-ui/overlay`, branding under
`kiosk/branding`, or the Homebox patch series under `deploy/homebox-patches`.
While `serve` runs, it checks those inputs once a second, prepares the same
patched source as the release UI, and copies changed files into
`work/homebox-ui-dev`. It also removes source files that disappeared, while
preserving installed packages and Nuxt caches. Nuxt watches that workspace and
pushes changes to the current browser through HMR. The pinned upstream checkout
is materialized from its recorded commit; change that base through the patch
series rather than editing the upstream checkout directly.

For a standalone run, stop `serve` with Ctrl-C. In the local-test stack, the
supervisor stops Nuxt with the other children. If Nuxt exits unexpectedly, the
supervisor exits and the existing service restart policy starts the stack
again. The helper checks and syncs source on startup. A lockfile change causes
a dependency install and Nuxt restart. If source preparation fails, fix the
reported patch or source error and restart the stack.

## Static fallback and release builds

To select the static UI in the local-test stack, set
`WORKSHOP_LOCAL_UI_DEV=0` for `ccrate-local-test.service` and restart it. For
example, use `systemctl --user edit ccrate-local-test.service` and add:

```ini
[Service]
Environment=WORKSHOP_LOCAL_UI_DEV=0
```

Then run `systemctl --user restart ccrate-local-test.service`. To restore live
UI, remove that override or set `WORKSHOP_LOCAL_UI_DEV=1`, then restart the
service. Static mode does not start Nuxt or set the gateway's
`WORKSHOP_UI_DEV_PORT`; the gateway serves the existing `HOMEBOX_UI_ROOT`.
Standalone gateways also use static mode when `WORKSHOP_UI_DEV_PORT` is unset.

This development path runs `nuxt dev`. It does not run `nuxt generate`,
`pnpm run build`, or change the release UI. Release generation remains the
separate `deploy/build-homebox-ui.py` path.
