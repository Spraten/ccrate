# C-Crate workshop inventory

C-Crate is a local workshop inventory and checkout system built on [Homebox](https://github.com/sysadminsmedia/homebox). It adds the Equipment Terminal, member and badge tools, checkout and return workflows, item notes, room maps, shelf checks, imports, and label design and printing. Homebox remains the authority for inventory, people, and native history.

## Architecture

- `upstream/homebox/` is the pinned Homebox submodule. Keep product changes in `homebox-ui/overlay/`, `homebox-backend/`, `ops/`, `kiosk/`, and `desktop/` unless an upstream change is explicitly requested.
- `homebox-ui/overlay/` extends the native Vue interface. `ops/` provides the companion API and durable operation journal. `kiosk/` is the Equipment Terminal client; `desktop/` contains its desktop view.
- `label-ui/` contains the standalone label editor and its pinned vendor source. Keep vendor licenses with vendor code.
- `deploy/` contains build, release, service and retained integration tooling. `tests/` contains temporary-fixture unit and browser tests.
- `work/` and `program-files/runtime/` are local generated builds, toolchains, runtime dependencies and test state. They are not source inputs to publish.

## Local setup

Initialize the pinned upstream source:

```sh
git submodule update --init --recursive
```

Build tools and runtime packages are kept under ignored `work/`. A clean checkout does not include those private deployment dependencies. Keep local data in a separate test environment; never connect local tests to the operational Homebox instance or mount its data, credentials, badge keys or backups.

### Isolated Docker test stack

On Windows with WSL and Docker Compose available, run `.\start.ps1` from this checkout. It builds the pinned Homebox, UI and label assets, then starts the gateway at [http://localhost:17745](http://localhost:17745) and Equipment Terminal at [http://localhost:17749](http://localhost:17749). The stack uses a dedicated named Docker volume and creates one local Homebox account on its first start. The generated sign-in stays in that volume; print it only when needed with:

```sh
docker compose exec ccrate-local-test cat /data/work/baseline/test-account.json
```

The stack preserves local test data across rebuilds and restarts. Do not use `docker compose down -v` unless you intend to remove that test data. Backups and physical printer or camera access are unavailable in this local test container. To inspect startup or shutdown, use `docker compose logs ccrate-local-test`.

The configured Pi builds use the pinned Go, Node.js and pnpm toolchains under `work/toolchains`:

```sh
python3 deploy/build-homebox-ui.py --toolchain-root "$PWD/work/toolchains" --upstream-root "$PWD"
python3 deploy/build-homebox-backend.py
python3 deploy/build-label-ui.py --source-root . --output work/label-ui-build
```

The backend builder uses the selected native UI at `work/homebox-ui-current`. The UI and label builders stage output under `work/`; they do not select or deploy a release. See [C-Crate release notes](docs/C_CRATE_RELEASE.md), [label layouts](docs/LABEL_LAYOUTS.md), and the [native UI build notes](homebox-ui/README.md) for their prerequisites.

## Tests and operational safeguards

The Python fixture suite runs from WSL/Linux with the project dependencies available:

```sh
PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -v
```

Native and browser integration checks require isolated Homebox and companion services. Use disposable local data and synthetic fixtures. Never run demo-creating or mutation checks against the operational Pi, restart its services, or print physical labels as part of routine testing.

Uncertain writes and prints keep their original request identity. Resolve them through Recovery or a read-only status check; never retry automatically. Private credentials, badge keys, databases, and backups stay outside source control and logs. See [user management](docs/USER_MANAGEMENT.md), [clean start](docs/CLEAN_START.md), and [workflow navigation](docs/WORKFLOW_NAVIGATION.md).

## Deployment ports

The configured deployment uses ports 17745 for the Homebox gateway, 17747 for the private native backend, and 17749 for the Equipment Terminal. The Docker test stack publishes only 17745 and 17749 on localhost and keeps 17747 inside its container. Deployments and live inventory operations require the workshop host configuration; local test services use isolated data.
