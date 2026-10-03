# Live Pi project

The user removed all demonstration data on 2026-10-03. Preserve the real inventory and clean initial state.

- Do not run deploy/complete-baseline.py, deploy/probe_homebox.py or live demo-creating verify scripts against the operational Homebox instance. Use an isolated instance for mutation tests. Unit tests use temporary fixtures.
- Homebox remains the inventory authority. Use supported native APIs and preserve existing metadata.
- Never retry an uncertain create or print automatically. Use durable companion recovery.
- Private credentials, badges, backups and cleanup archives stay on the Pi. Do not log or transfer them without explicit authorization.
- The main service account is Workshop Admin; keep its private credentials and access intact.
- See docs/CLEAN_START.md for the cleanup record.
