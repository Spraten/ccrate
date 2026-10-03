# Homebox baseline and recovery proof

Date: 2026-10-02. Homebox v0.26.2 remains unmodified, pinned at e01dd737238a3fa7e1a6454b37de6c6fc88c86e4. This is a loopback-only synthetic demonstration, not a production installation.

## Configuration

Project: /home/user/Desktop/inventory-system. Binary: work/homebox-bin/homebox. Baseline runs on 127.0.0.1:17745. SQLite and storage are in work/baseline/data; API-key pepper and synthetic account file are in restricted work/baseline. Release checks and analytics disabled. No boot service installed.

## Representative data

Created nine native location entities: Demo Workshop, Drone Cage, four shelves, Charging Station, Maintenance and Quarantine. Six sample assets represent a drone, controller, two batteries, radio and repair tool. All names have Demo prefixes; descriptions identify synthetic data. Existing reconnaissance entities were preserved. Total baseline entity count: 27, including locations.

deploy/complete-baseline.py uses supported API calls, matches existing entities by name and parent, and can resume seeding without duplicating these demo entities. It also creates a new timestamped backup/restore check on every invocation; do not rerun unnecessarily.

## Integration

Native endpoints exercised include users/login, entity-types, entities (paginated item/location lists, creation, detail, updates, paths and tree), API keys, QR/label rendering and dated maintenance creation. See api-probe-results.json for prior results. The shell server reads only demo inventory through the API; synthetic credentials stay server-side. Production authentication and permissions remain to decide.

## Tested backup procedure

1. Confirm the PID executable belongs to the isolated baseline.
2. Stop Homebox gracefully and wait for process exit. Refuse to copy while it runs.
3. Copy the entire configured storage directory and preserve the API-key pepper in a restricted timestamped backup folder under work/backups. Include every attachment/subdirectory when present; do not copy only the SQLite database.
4. Restart the baseline with its original configuration.
5. Generate SHA256 checksums of copied storage files.
6. Copy storage into a separate restricted restore folder, launch the same pinned binary on loopback port 17748 with the original pepper, authenticate through the API and compare every entity ID.
7. Stop the restore instance and confirm baseline login still succeeds.

Result: all 27 entity IDs matched; baseline restarted successfully. Evidence: baseline-completion-results.json. No direct database mutation was performed. Attachments and API-key continuity have not been exercised in this restore test. The local backup shares the Pi SD card; independent backup media and retention remain a deployment decision.

## Kiosk prototype

Port 17749 serves the approved six-button shell. Find Item and Browse Stock show native Homebox items, search by name/asset number/location, and open item summaries. Other task buttons show explicit workflow previews; no inventory mutation is enabled. Admin is a prototype information view and Homebox link, not a production permission boundary. Session identity, inactivity policy, scanner indicator behavior and operational workflows remain pending design decisions.

Start manually with python3 deploy/kiosk-server.py from the project folder. The service binds loopback and uses no external runtime assets. Source: kiosk/index.html and deploy/kiosk-server.py.


## Attachment recovery follow-up

The original absolute HBOX_STORAGE_PREFIX_PATH caused blob keys to resolve under a nested runtime path. Entity-only restore checks did not detect this. The configuration now uses storage prefix data relative to each Homebox process working directory; the SQLite path remains explicit. Existing synthetic attachment bytes and attributes were preserved before copying them into work/baseline/data. Original nested files remain preserved under work/backups/storage-prefix-original-* and their original location.

Verified with deploy/verify-recovery.py: native group member lookup, synthetic multipart attachment upload/download, complete cold storage copy, exact attachment hash after restore and API-key continuity using the preserved pepper. Temporary verification key revoked; restore instance stopped and original baseline restarted. Evidence: recovery-verification-results.json. Previous attachment/API-key limitations in the first report are superseded by this test. Independent backup media and abrupt power-loss recovery remain unverified.
