# Original plan acceptance audit

## Scope and authority

Original PROJECT_HANDOFF.md governs requirements, with later user decisions in DECISIONS.md taking precedence. Delegated best judgment replaces routine approval checkpoints; it does not prove human acceptance. Future section75 items remain excluded. Native Homebox is unmodified and pinned; no companion writes bypass its supported API. Actual Pi hardware supersedes the initial assumed Pi3/physical keyboard; this deployment uses a Pi4 and touch keyboard.

| Original phase | Current evidence | Limit or remaining gate |
|---|---|---|
| 0 Reconnaissance | 00-project-overview, 01-homebox-reconnaissance, 02-architecture-proposal, api-probe-results | None for current prototype |
| 1 Hardware | hardware-proof-results, initial user acceptance, real-camera-results, label-integration-results | New physical QR/label test still needs a person |
| 2 Native baseline | baseline-completion-results, pinned clean upstream submodule, runtime-manifest | Real inventory not supplied |
| 3 Shell | scan-integration-results, home screenshot, reboot-results | Uncoached feel not observed |
| 4 Scan infrastructure | scan_codes unit tests, scan-integration-results, final-touch and audit-gaps results | Physical source positioning unobserved |
| 5 Identity | badge-integration-results, account-integration-results, session tests | Real people/badges not configured |
| 6 Checkout | checkout-integration-results, ledger tests | User physical batch walkthrough pending |
| 7 Return | return-integration-results, return tests, kit-integration-results | Physical normal/damaged return pending |
| 8 Map | map-integration-results, native map fields, location-label preview | Actual room layout not provided |
| 9 Kits | kit-integration-results, kits unit tests | Real kit completeness walkthrough pending |
| 10 Condition/inspection | condition/problem/photo/admin-stock results | Real damage/inspection acceptance pending |
| 11 Enrollment | enrollment/photo/label results, serial scan support | Physical enrollment-to-label acceptance pending |
| 12 Search/browse | admin-stock and audit-gaps results | Human find/browse study pending |
| 13 Admin | account/map/admin-stock/final-touch results, backup and label modules | Open prototype Admin remains chosen policy |
| 14 Offline | offline-isolation-results; clone with only loopback; zero external browser requests | Physical cable removal not performed |
| 15 Recovery | crash/reboot/deployment-restore/audit-gaps results; 95 unit tests | Abrupt physical power loss and actual USB disconnect tests not performed |
| 16 User testing | No uncoached-user evidence | Requires a person; never claim complete |

## Recovery gate detail

Orderly reboot is proved, not an abrupt power cut. SIGKILL tests prove application and native restart, custody preservation and badge-session clearing. Corrupted duplicate-asset requests are rejected without a journal write. Isolated restore verifies runtime hashes, native entity/location/member IDs, operational tables and one native attachment's bytes; it does not replace the live deployment or prove every attachment. Printer disconnect and missing-camera feedback are failure-injected; USB hardware was not physically disconnected. Storage warning is tested at critical, absolute-low, percentage-low and healthy values without filling the disk.

## Human study protocol

Give an unfamiliar tester only these tasks: check out a drone; return a battery; report damage; find a controller; locate a battery shelf; browse available drones. Record taps, scans, screens, seconds, typed fields, errors and requests for help. Do not coach unless needed to finish safely. Use synthetic equipment or approved actual setup; never manufacture a pass. Inspect label orientation and legibility, then scan badge, asset and location codes physically. Ask an administrator to supervise actual USB reconnection and abrupt power-loss recovery after ensuring a usable external backup.

## Current genuine blockers

No person is available to complete physical and uncoached acceptance. Actual setup identities/inventory/geometry have not been supplied. Automatic approval review rejected copying the private archive to this PC because it contains credentials and private data without specific payload/destination authorization; the approval remains pending. All public report files were transferred successfully. These gates prevent a full-completion claim.
