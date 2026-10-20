# Live UI development for C-Crate

## Goal

Run the local C-Crate UI from a persistent Nuxt development server so source changes appear in the current browser without regenerating the static UI bundle.

## Requirements

- The existing local gateway remains the browser entry point and continues serving/proxying the backend API and native event websocket.
- UI page and asset requests in local development go to Nuxt dev mode; Nuxt's HMR websocket is reachable through the same browser origin.
- The dev workspace includes the project's Homebox base, C-Crate overlays and patches, including the OCR overlay already in source.
- The dev server starts and restarts with the existing local-test supervisor; no separate service is introduced.
- Frontend dependencies are installed once from the pinned lockfile into the local dev workspace using the existing Node/pnpm toolchain.
- Local development changes do not run `nuxt generate` or the release bundle build. Keep the static UI path available when dev mode is disabled.
- Document how to edit, restart, and disable live UI development.

## Constraints

- Do not overwrite or revert unrelated working-tree changes.
- Do not install another runtime or create a system/user service.
- Do not change the deployed/release UI path as part of enabling local development.
