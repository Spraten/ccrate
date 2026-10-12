# C-Crate project rules

- Make the smallest complete change. Reuse existing Homebox APIs, UI components and helpers. Do not add dependencies or unrelated features.
- Homebox is the inventory and account authority. Preserve native identities, metadata, access rules and history.
- Never run demo-creating or mutation checks against an operational Homebox instance. Use isolated local Docker data or temporary fixtures; never connect local tests to the live Pi.
- Never automatically repeat an uncertain create, save, badge issue, replacement or print. Keep its request identity and use Recovery/status checks.
- Keep credentials, badge keys, databases, backups and cleanup archives out of source control, logs and release bundles. Preserve Workshop Admin access.
- Do not weaken authentication, role checks, input validation, accessibility or recovery behavior. Name-only profiles remain badge-only; existing web accounts keep their sign-in behavior.
- Do not restart or deploy services, print physical output, or change operational data unless the user explicitly authorizes that action.
- Use one coding worker at a time unless the user explicitly requests parallel independent tasks. For requested parallel work, keep each worker's file scope isolated. Coding work uses GPT-6 Luna Low; the final review uses GPT-6.1 Sol High. Do not silently substitute models.
- Run the focused unit or fixture checks for a change before calling it complete. Do not rely on historical receipts or require old baseline artifacts for a fresh local test setup.
