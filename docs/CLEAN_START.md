# Clean start

The user requested removal of demonstration data on 2026-10-03.

The live deployment now has no equipment, locations, templates, tags, badge tokens, import batches, custody or test-operation history. Only native Item/Location types and the required Workshop Admin service account remain. The account's existing private login credentials are unchanged.

The cleanup removed 51 demo/test assets, 20 locations (including built-in household examples), three test categories, one test product template, six default example tags and the other test group member. Immutable demo history (33 operations, 33 native jobs, 23 badges) is archived privately on the Pi under work/demo-archive. A consistent complete private backup was created before cleanup. The scoped cleanup audit is work/demo-cleanup.json.

Workshop shows an empty setup action. Create real locations or import equipment through Admin. Badge-only workflows require issuing fresh badges. Previously printed demo badges and equipment QR labels no longer identify live records.

Do not seed demo data again on this live deployment. deploy/complete-baseline.py and many deploy/verify-*.py scripts create native demonstration records or require old demo IDs. Use isolated test Homebox instances for such checks. The unit suite uses temporary fixtures and can run without adding live data. deploy/verify-demo-cleanup.py verifies the current empty initial state and is only appropriate before real inventory is added.
