# Operational data safeguards

The operational Homebox is the workshop's inventory authority. Treat its users, inventory, checkout history and private service state as real operational data.

- Do not seed demo data, run mutation verifiers, or use a live instance for local development. Use isolated Docker data or temporary fixtures.
- Do not copy operational databases, credentials, badge keys or backups into a local test environment, source control, logs or release bundles.
- Do not restart operational services or print physical output during local verification.
- Keep uncertain writes and prints under their original request identity. Resolve them through Recovery or a read-only status check; do not retry automatically.

Use the native Homebox APIs and preserve existing identities, metadata, access and history. Badge-only profiles remain separate from web sign-in, and Workshop Admin access must be preserved.
