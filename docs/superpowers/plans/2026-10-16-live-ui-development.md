# Live UI development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current local C-Crate UI use Nuxt hot reload and keep doing so across local stack restarts, without generating a static bundle for each edit.

**Architecture:** Extend the existing local-test supervisor to prepare a persistent Nuxt workspace from the current frontend source and start `nuxt dev`. Keep that workspace synchronized from the repo's upstream frontend and C-Crate overlay sources while excluding dependencies and Nuxt caches, so Nuxt watches the files being edited. Teach the existing gateway to proxy UI requests and the Nuxt HMR websocket to that child while preserving its current API and Homebox event websocket routing. Keep static serving as the fallback when live development is disabled.

**Tech Stack:** Python local supervisor and HTTP/websocket gateway; Node.js 20; project-pinned pnpm and Nuxt 4.2.2.

**Spec:** `docs/superpowers/specs/2026-10-16-live-ui-development.md`

## Global Constraints

- Use the existing Node and pinned pnpm toolchain; install only the lockfile-pinned frontend packages in the isolated development workspace.
- Do not run the static UI generation or release build for local source edits.
- Preserve the existing local gateway entry point and backend routes.
- Do not touch unrelated working-tree modifications.
- Do not add a separate service or alter deployed/release UI configuration.

## Review Focus

- Nuxt HMR websocket upgrades must reach Nuxt without intercepting `/api/v1/ws/events`.
- API and desktop API requests must continue to reach their existing backends.
- Missing or stopped dev-server behavior must fail clearly and retain a static fallback when live mode is disabled.
- Paths, query strings, and asset responses must survive proxying.
- The workspace must reflect updates from overlay and upstream frontend source without repeating the dependency install.

---

### Task 1: Create a persistent patched frontend dev workspace

**Files:**
- Modify: `deploy/build-homebox-ui.py`
- Create/modify: `deploy/dev-homebox-ui.py` (or a focused helper in the existing script if that better matches its current structure)
- Create: `docs/development/live-ui.md`

**Interfaces:**
- Consumes the same frontend source, C-Crate overlay, lockfile, and patch steps used by the static UI preparation.
- Produces a persistent dev workspace under the existing local work root and a command that launches Nuxt dev mode in that workspace.

- [ ] Add a development preparation/sync mode that applies the existing patched-source transformations and copies source changes into the persistent dev workspace without removing `node_modules` or Nuxt caches.
- [ ] Install dependencies from the lockfile only when the dev workspace is new or its lockfile changes; source edits must not reinstall packages.
- [ ] Run source synchronization while the dev server is active, excluding `node_modules`, `.nuxt`, and `.output`, so changed source reaches Nuxt and triggers HMR.
- [ ] Add a command for starting `nuxt dev` on a loopback port with host/port configurable via environment.
- [ ] Document first startup, source editing, restart, disable/fallback behavior, and the distinction from release generation.
- [ ] Inspect the resulting workspace configuration and command paths.

### Task 2: Proxy UI HTTP requests and HMR websocket through the gateway

**Files:**
- Modify: `deploy/workshop-gateway.py`

**Interfaces:**
- Reads optional `WORKSHOP_UI_DEV_PORT` (default disabled), which identifies a loopback Nuxt dev server.
- Keeps `/api` and desktop API routing on existing backends; `/api/v1/ws/events` continues through the existing native event proxy.
- Proxies Nuxt page/assets and the Vite HMR websocket to the dev server when enabled.

- [ ] Add HTTP reverse proxy handling that preserves path, query, headers needed by Nuxt, response status, and body.
- [ ] Route only the Nuxt HMR websocket upgrade to the dev-server upstream; preserve the native event websocket path.
- [ ] Return an actionable unavailable response when live mode is configured but Nuxt is not ready.
- [ ] Review route precedence, websocket headers, and existing gateway security/path checks.

### Task 3: Supervise Nuxt and activate live UI in the current local stack

**Files:**
- Modify: `deploy/local-test.py`
- Modify: `deploy/setup-local-native.sh` only if it owns the current local-test environment configuration.
- Modify: `docs/development/live-ui.md`

**Interfaces:**
- The local-test supervisor owns the Nuxt dev child alongside current native server, companion, and gateway children.
- Live UI is enabled for the local development stack and can be disabled to use the existing static UI root.

- [ ] Prepare the persistent dev workspace before launching children.
- [ ] Start, monitor, and restart the Nuxt process with the existing supervisor lifecycle and logs.
- [ ] Configure the gateway to use the live UI upstream for this local stack only.
- [ ] Keep other deployment/service configurations on the static UI path.
- [ ] Verify current local stack health, UI response, OCR overlay availability, and HMR behavior without running static generation.
