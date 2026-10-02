# Project Handoff: Offline Homebox Equipment Management Kiosk

## 1. Purpose of This Handoff

You are taking over the design and implementation of an offline equipment-management system built around Homebox.

The system is intended for a team/lab/workshop that manages drones, batteries, controllers, radios, cables, tools, accessories, kits, cases, and related equipment.

This is **not simply a Homebox installation on a Raspberry Pi**.

The desired product is:

> A scanner-first, touchscreen-friendly, offline equipment accountability terminal that uses Homebox as the underlying inventory system while adding purpose-built workflows for checkout, return, location mapping, condition tracking, equipment enrollment, label printing, maintenance, and equipment discovery.

The most important product requirement is:

> **The system must be extremely convenient to use.**

If checking equipment in or out is cumbersome, users will avoid doing it and the inventory will become inaccurate.

The kiosk should therefore make the common action the easy action.

---

# 2. Collaboration Requirement — VERY IMPORTANT

The user wants to remain directly involved in product and workflow decisions.

Do **not** independently make significant product decisions simply because one option is technically convenient.

You should actively collaborate with the user.

## Decision protocol

Use the following classifications while working.

### `[DECISION REQUIRED]`

Stop implementation of that specific decision and ask the user when a choice would materially affect:

- user workflow
- screen behavior
- navigation
- terminology
- authentication
- permissions
- equipment status behavior
- checkout rules
- return rules
- kit behavior
- workshop-map behavior
- database architecture
- Homebox modifications
- long-term maintainability
- security
- data retention
- label contents
- hardware behavior
- deployment architecture

Explain:

1. What decision needs to be made.
2. Why it matters.
3. The reasonable options.
4. Advantages/disadvantages of each.
5. Your recommended option.
6. What the user will notice differently.

Then ask the user to decide.

Do not implement past that decision until the user answers.

---

### `[CHECKPOINT]`

At meaningful milestones, stop and show the user what exists.

Examples:

- kiosk home screen working
- scanner prototype working
- checkout workflow working
- return workflow working
- map editor working
- location highlighting working
- label printing working
- first full end-to-end workflow working

At checkpoints:

- summarize what changed
- show screenshots when practical
- explain how to test it
- identify anything that feels unfinished
- ask whether the user wants changes before continuing

The user explicitly wants to ensure the project is going in the intended direction.

---

### `[ASSUMPTION — REVERSIBLE]`

You may make a reasonable engineering assumption without stopping when:

- it is easy to reverse
- it does not materially alter UX
- it does not create significant technical debt
- it does not lock in an architecture
- it does not affect data compatibility

Document the assumption.

---

### `[BLOCKED]`

If something cannot continue because of missing information, hardware, documentation, or an unresolved technical issue:

State:

- what is blocked
- what you attempted
- what information is missing
- whether another portion of the project can continue safely

Do not hide a blocker by inventing behavior.

---

# 3. Do Not Overwhelm the User With Questions

The user wants involvement, but does not want the development process to become annoying.

Do not ask twenty speculative questions up front.

Ask questions **when they become relevant to the phase being implemented**.

For example:

Do not ask detailed battery-maintenance-policy questions while implementing the home screen.

Instead:

1. Build/review the home screen.
2. Resolve home-screen decisions.
3. Move to identity/scanning.
4. Resolve identity decisions.
5. Move to checkout.
6. Resolve checkout decisions.

Use progressive design checkpoints.

---

# 4. Maintain a Decision Log

Create and maintain:

`docs/DECISIONS.md`

Every important confirmed decision should include:

- Decision ID
- Date
- Topic
- Question
- Options considered
- User's chosen option
- Implementation consequence
- Whether the decision can be revisited

Example:

```md
## DEC-014 — Kit Checkout Verification

Decision:
Verified checkout will be required for drone kits.

Behavior:
Scanning KIT-003 opens its manifest and requires each tracked component to
be scanned before the checkout can complete.

Reason:
User wants physical confirmation that expensive equipment is actually
inside the case.

Status:
Approved.
```

Do not repeatedly ask questions that have already been answered.

---

# 5. Maintain Current Project State

Create:

`docs/PROJECT_STATE.md`

Keep this short and current.

Include:

```md
# Current Phase

Phase 3 — Asset Scanning

# Working

- Homebox integration
- kiosk home screen
- badge lookup

# In Progress

- scanner abstraction

# Decisions Waiting on User

- DEC-008 camera scan feedback sound

# Known Problems

- webcam initialization takes ~2 seconds

# Next

- asset QR routing
- location QR routing
```

This should make it possible for another Codex session or developer to resume without reconstructing the project.

---

# 6. Existing Hardware

The expected prototype hardware is:

- Raspberry Pi 3
- 64 GB SD card
- Raspberry Pi OS
- 7-inch touchscreen
- webcam
- physical keyboard
- SUPVAN T50M Pro Bluetooth Label Maker
- printer connected to Raspberry Pi through USB when possible

The system will ultimately operate on an isolated/offline lab network.

The keyboard primarily exists for:

- setup
- administration
- maintenance
- troubleshooting

Normal users should not need the keyboard.

---

# 7. Hardware Constraints

The Raspberry Pi 3 is relatively resource constrained.

Design accordingly.

Avoid unnecessarily heavy architecture.

Be cautious with:

- Electron
- multiple heavyweight containers
- excessive browser animations
- high-resolution continuous webcam processing
- large in-memory product catalogs
- frequent disk writes
- unnecessary background services

Initial camera targets may be approximately:

- 640×480
- 10–15 FPS

Barcode/QR decoding should prioritize reliability over visual quality.

Benchmark instead of assuming performance.

---

# 8. Offline Requirement

The finished system must remain useful with **zero Internet connectivity**.

Core workflows must never require:

- cloud authentication
- public APIs
- CDN JavaScript
- cloud barcode APIs
- externally hosted fonts
- external image assets
- external package repositories at runtime
- vendor phone applications
- web-hosted documentation

If something is required at runtime, it needs to exist locally.

Before final air-gap deployment, dependencies must be captured and documented.

---

# 9. Upstream Homebox Strategy

Do not begin by heavily forking Homebox.

Prefer this model:

```text
                   ┌────────────────────┐
                   │     Kiosk UI       │
                   └─────────┬──────────┘
                             │
                             ▼
                   ┌────────────────────┐
                   │ Inventory Ops API  │
                   └────┬────────┬──────┘
                        │        │
                 ┌──────┘        └───────┐
                 ▼                       ▼
             Homebox                  Ops DB
                 │
                 │
                 └─────────┐
                           ▼
                    Product Catalog
```

Homebox should primarily remain the system of record for inventory entities.

Our custom software should handle specialized operational workflow.

Current upstream Homebox versions use the unified entity model/API for items and locations and support API keys for integrations.

Verify the exact upstream version/API behavior before implementation.

Do not write directly against the Homebox SQLite schema unless there is an exceptional reason and the user approves it.

Prefer the supported Homebox API.

---

# 10. Conceptual Components

The project will probably contain at least four logical components.

## A. Homebox

Responsible for:

- inventory entities
- basic inventory metadata
- locations
- attachments
- entity relationships
- relevant custom fields
- existing Homebox functionality

---

## B. Inventory Operations Service

Responsible for workflow Homebox does not natively model well.

Potential responsibilities:

- kiosk sessions
- user/badge resolution
- checkout transactions
- return transactions
- custody
- condition transitions
- scan routing
- kit verification
- location movement
- append-only activity history
- kiosk identity
- operational policies

Exact boundaries are a design decision and should be reviewed before implementation.

---

## C. Kiosk UI

Designed specifically for:

- 7-inch touchscreen
- large touch targets
- minimal typing
- rapid scanning
- obvious visual feedback
- short workflows

This should not simply embed the regular Homebox interface.

---

## D. Product Catalog Service

Provides offline lookup for:

- UPC
- EAN
- GTIN
- manufacturer
- model
- MPN
- product category
- technical metadata
- optionally product images/specifications

Its purpose is to accelerate enrollment of new equipment.

Example:

```text
scan retail barcode

        ↓

0190021012345

        ↓

local product catalog

        ↓

DJI TB30 Intelligent Flight Battery

        ↓

populate equipment enrollment form
```

The catalog is **not** the same as inventory.

One catalog product can correspond to many owned assets.

---

# 11. Critical Data Distinction

Do not confuse:

## Product

Example:

```text
DJI TB30 Intelligent Flight Battery
GTIN: XXXXX
Model: TB30
```

with:

## Asset

Example:

```text
BAT-0182
Serial: TB30-912381
Condition: READY
Location: Charging Shelf C1
```

A retail barcode identifies the product type.

Our asset QR identifies a specific owned physical object.

---

# 12. Product Design Philosophy

The primary UX rule is:

> **Normal operations are fast. Exceptions can be detailed.**

Do not require unnecessary information during routine transactions.

Bad:

```text
Scan badge
Select department
Select location
Search item
Select condition
Choose mission
Enter notes
Confirm
```

Desired:

```text
Scan badge
Scan equipment
Confirm
```

If condition changed, *then* ask additional questions.

---

# 13. Scanner-First Design

Scanning should work throughout the application.

The system should recognize different code classes.

For example:

```text
LAB:U:<token>
```

means:

```text
USER
```

```text
LAB:A:<uuid>
```

means:

```text
ASSET
```

```text
LAB:L:<uuid>
```

means:

```text
LOCATION
```

and ordinary:

```text
UPC / EAN / GTIN
```

means:

```text
PRODUCT CATALOG LOOKUP
```

The exact QR namespace is a `[DECISION REQUIRED]` before labels become permanent.

---

# 14. Scanner Abstraction

Do not tightly couple workflow logic to the webcam.

Create a scanner abstraction.

Conceptually:

```text
Webcam Decoder ───┐
                  │
USB Scanner ──────┼──► Scan Router ───► Application
                  │
Manual Input ─────┘
```

Possible future sources:

- webcam
- USB handheld barcode scanner
- keyboard wedge scanner
- administrator manual entry
- possibly another kiosk/device later

All should produce the same normalized scan event.

---

# 15. Scan Behavior

Scanning should be intelligent.

From the home screen:

### User badge scan

Start that user's kiosk session.

### Asset scan

Open the asset overview.

### Location scan

Open location information or use it as a destination during a relevant workflow.

### Manufacturer barcode

Search offline product catalog.

### Unknown code

Offer appropriate troubleshooting/enrollment behavior.

Avoid forcing users to choose "what type of barcode am I scanning?"

The system should infer it.

---

# 16. Home Screen

Current proposed home screen:

```text
┌───────────────────────────────────────┐
│            TEAM EQUIPMENT             │
│                                       │
│     CHECK OUT        RETURN           │
│                                       │
│     FIND ITEM        BROWSE STOCK     │
│                                       │
│          REPORT / INSPECT             │
│                                       │
│ Scan badge or equipment QR anytime    │
│                                       │
│                             ⚙ ADMIN   │
└───────────────────────────────────────┘
```

Potential additional context after badge login:

```text
Welcome, Andreas

CHECK OUT          RETURN

MY EQUIPMENT       REPORT ISSUE

Currently checked out: 4
```

Management tasks should not clutter the normal kiosk home screen.

---

# 17. Administrative Area

Admin functions may include:

```text
Inventory
Workshop Map
Locations
Users
Equipment Enrollment
Kits
Maintenance
Labels
Product Catalog
Audits
Reports
Backup / Restore
System Status
Settings
```

Administrative authorization requirements are a later `[DECISION REQUIRED]`.

---

# 18. User Identification

Expected flow:

```text
CHECK OUT
    ↓
SCAN BADGE
    ↓
USER SESSION
```

Badge QR should contain a random/stable identifier, not personal information.

For example:

```text
LAB:U:7fc54e...
```

The server resolves the token.

Avoid encoding:

- name
- rank
- team
- employee number
- other PII

directly into the QR.

---

# 19. Authentication vs Identification

A QR badge is identification, not necessarily secure authentication.

Someone could photograph another user's QR.

Possible policies:

### Option A

Badge only.

Fastest.

### Option B

Badge + PIN.

Better attribution.

### Option C

Different security depending on operation.

Example:

```text
Browse Inventory:
No authentication

Checkout:
Badge

Restricted Item Checkout:
Badge + PIN

Admin:
Admin authentication
```

Do not select this policy without discussing it with the user.

`[DECISION REQUIRED]`

---

# 20. Checkout Workflow

Target:

```text
CHECK OUT
    ↓
SCAN BADGE
    ↓
SCAN ITEM
    ↓
SCAN ITEM
    ↓
SCAN ITEM
    ↓
REVIEW
    ↓
CONFIRM
```

Support batch checkout.

Do not require a new badge scan for every asset.

Example:

```text
CHECKOUT — ANDREAS

✓ DRN-0041   DJI Matrice 30T
✓ BAT-0182   TB30 Battery
✓ BAT-0183   TB30 Battery
✓ CTRL-0014  RC Plus

4 ITEMS

[ CONFIRM CHECKOUT ]
```

---

# 21. Equipment Status Card

When scanned:

```text
DJI MATRICE 30T
DRN-0041

✓ AVAILABLE
✓ READY

Location
Drone Cage > Shelf B2

Last inspection
29 SEP

[ ADD TO CHECKOUT ]

History
Notes
```

Users should not navigate multiple Homebox pages just to understand basic equipment status.

---

# 22. Return Workflow

Routine returns must be extremely fast.

Target:

```text
RETURN
   ↓
SCAN BADGE
   ↓
SCAN ITEM
   ↓
Condition unchanged?
   ↓
YES
   ↓
SCAN / CONFIRM DESTINATION
   ↓
DONE
```

If something changed:

```text
CONDITION CHANGED
        ↓
Choose condition
        ↓
Add note
        ↓
Optional photo
        ↓
Maintenance/quarantine behavior
```

---

# 23. Structured Condition

Do not rely only on free-form notes.

Potential condition values:

```text
READY
SERVICEABLE
SERVICEABLE_WITH_LIMITATIONS
MAINTENANCE_REQUIRED
DAMAGED
```

The final vocabulary must be reviewed with the user.

`[DECISION REQUIRED]`

---

# 24. Availability Is Not Condition

Keep these concepts separate.

Example:

```text
Condition:
READY

Availability:
CHECKED_OUT
```

Potential availability states:

```text
AVAILABLE
CHECKED_OUT
RESERVED
MAINTENANCE
QUARANTINED
MISSING
RETIRED
```

An asset could therefore be:

```text
Condition:
SERVICEABLE

Availability:
CHECKED_OUT
```

Do not collapse everything into one giant status field.

---

# 25. Custody

Track:

```text
Current custodian
Current physical location
Checkout timestamp
Transaction ID
```

The system should be able to answer:

> Who has this?

> Where should this be?

> Where was it last?

---

# 26. Transaction History

Do not simply overwrite fields and lose history.

Every operational action should generate an event.

Possible schema concept:

```text
transaction_id
event_type
timestamp

user_id
asset_id

from_location_id
to_location_id

previous_custodian
new_custodian

condition_before
condition_after

notes

kiosk_id
```

Examples:

```text
CHECKOUT
RETURN
MOVE
INSPECTION
CONDITION_CHANGE
QUARANTINE
RELEASE_FROM_QUARANTINE
MAINTENANCE_START
MAINTENANCE_COMPLETE
```

Prefer an append-only operational history.

If a transaction needs correcting, create a correction event rather than silently modifying historical records.

The exact event/data architecture needs technical review before implementation.

---

# 27. Item History UI

Example:

```text
DRN-0041
DJI Matrice 30T

OVERVIEW
HISTORY
MAINTENANCE
FILES
```

History:

```text
02 OCT 08:14
CHECKED OUT
Andreas
Drone Cage → Andreas

01 OCT 16:44
INSPECTION
Condition: READY

30 SEP 11:13
RETURNED
Jordan
Jordan → Shelf B2

29 SEP 09:02
CONDITION CHANGE
READY → SERVICEABLE

"Minor crack on antenna mount"
```

---

# 28. Equipment Kits

Kits are an important feature.

Example:

```text
MATRICE FIELD KIT 03

├── Aircraft
├── Controller
├── Battery 1
├── Battery 2
├── Battery 3
├── Battery 4
├── Charger
├── Antenna Kit
└── Case
```

Possible checkout modes:

## Fast

Scan kit once and check out its manifest.

## Verified

Scan kit.

Then physically scan each expected component.

The system compares expected versus present equipment.

Example:

```text
MATRICE KIT 03

Expected: 9
Verified: 8

✗ Battery 4 missing

KIT NOT COMPLETE
```

Kit policy is a `[DECISION REQUIRED]`.

The system may eventually allow policy per kit/type.

---

# 29. Workshop Map — Major Feature

The user strongly wants a visual workshop map.

The map should answer:

> Where is this item physically located?

Instead of simply saying:

```text
Drone Cage > Rack 2 > Shelf B
```

show the room and visibly highlight the exact location.

Example:

```text
┌─────────────────────────────────────┐
│           WORKSHOP                  │
│                                     │
│        ┌──── DRONE CAGE ─────┐      │
│        │                      │      │
│        │ Shelf A   Shelf B ★  │      │
│        │                      │      │
│        └──────────────────────┘      │
│                                     │
│  KIOSK                              │
│                                     │
│              Maintenance            │
│                 Bench               │
└─────────────────────────────────────┘
```

The selected shelf should visibly flash/highlight.

Potential optional behavior:

```text
KIOSK
  │
  └──── dotted path ────► Shelf B
```

This path does not need real navigation intelligence initially.

It can simply provide visual orientation.

---

# 30. Map Editor

Admins should be able to create a map without writing configuration files.

Initial concept:

```text
CREATE ROOM

Workshop
```

then add:

```text
Shelf
Rack
Table
Cabinet
Cage
Workbench
Charging Station
Maintenance Area
Quarantine Area
Door
Kiosk
```

Objects should be assigned Homebox location entities.

Example:

```text
Visual object:
Shelf B2

Homebox location:
Workshop
└─ Drone Cage
   └─ Rack 2
      └─ Shelf B2
```

---

# 31. Map Data Concept

Do not hardcode the workshop into the UI.

Potential separate map representation:

```text
room
- id
- name
- width
- height

map_object
- id
- room_id
- type
- label
- x
- y
- width
- height
- rotation
- homebox_entity_id
```

The exact storage method should be reviewed first.

Possible options include:

1. separate Ops database
2. Homebox custom fields
3. Homebox attachment containing layout JSON
4. another integration mechanism

Compare maintainability before choosing.

`[DECISION REQUIRED]`

---

# 32. Map UX

The administrator should ideally be able to:

- add object
- select object
- rename object
- move object
- resize object
- optionally rotate object
- connect it to Homebox location
- print its QR label
- delete object
- duplicate object

Do not make drag-and-drop the only way to manipulate objects.

Provide accessible/manual positioning options eventually.

---

# 33. Location QR Codes

Locations should receive labels too.

Examples:

```text
Shelf A1
Shelf B2
Charging Station
Maintenance Bench
Quarantine Shelf
Vehicle
Pelican Case
```

Scanning a location should be usable during equipment movement.

Example:

```text
SCAN ASSET
    ↓
SCAN DESTINATION
    ↓
ASSET MOVED
```

This avoids navigating nested location menus.

---

# 34. Find Item

Search should support:

- asset ID
- name
- serial
- model
- manufacturer
- category
- possibly notes/tags

Example:

```text
Search:
"Matrice"
```

Result:

```text
DJI Matrice 30T
DRN-0041

AVAILABLE
READY

Drone Cage
 > Rack 2
 > Shelf B
```

Then:

```text
[ SHOW ON MAP ]
```

The shelf highlights immediately.

---

# 35. Browse Stock

Find Item answers:

> Where is something I already know about?

Browse Stock answers:

> What equipment do we have?

Potential categories:

```text
Drones
Batteries
Controllers
Payloads
Radios
Networking
Tools
Cables
Cases
Consumables
Kits
```

Useful filters:

```text
Available
Ready
Location
Manufacturer
Category
Condition
```

---

# 36. Report / Inspect

There should be an easy path for reporting problems.

Home screen:

```text
REPORT / INSPECT
```

Then:

```text
SCAN ITEM
```

Possible issue types:

```text
Damage
Performance Issue
Missing Part
Needs Inspection
Other
```

Allow:

```text
Condition
Notes
Photo
```

Normal users should not have to navigate administrative maintenance screens.

---

# 37. Automatic Quarantine / Maintenance

Example:

User reports:

```text
Right rear motor making grinding noise.
```

and selects:

```text
MAINTENANCE REQUIRED
```

Potential automatic result:

```text
Availability:
MAINTENANCE
```

Asset can no longer be checked out.

Potential maintenance record created automatically.

Rules for automatic quarantine/maintenance need user approval.

`[DECISION REQUIRED]`

---

# 38. Product Catalog

The desired experience for new equipment:

```text
SCAN PRODUCT BARCODE
         ↓
LOCAL DATABASE
         ↓
Recognize product
         ↓
Pre-fill manufacturer/model/specs
```

Sources may eventually include:

- appropriate open product catalogs
- manufacturer catalogs
- organization-specific data
- curated imports

Any database licensing must be reviewed before bulk copying data into the offline system.

Do not assume an online API permits permanent local mirroring.

---

# 39. Equipment Enrollment

Target workflow:

```text
ADD EQUIPMENT
      ↓
SCAN MANUFACTURER BARCODE
      ↓
Product recognized
      ↓
SCAN / ENTER SERIAL
      ↓
OPTIONAL PHOTO
      ↓
SCAN STORAGE LOCATION
      ↓
CREATE ASSET
      ↓
PRINT ASSET QR
```

Avoid requiring an administrator to manually enter:

```text
manufacturer
model
description
voltage
capacity
part number
etc.
```

when product data can be safely populated automatically.

---

# 40. Asset Labels

Suggested basic label:

```text
┌─────────────────────┐
│ DJI MATRICE 30T     │
│                     │
│       QR CODE       │
│                     │
│ DRN-0041            │
└─────────────────────┘
```

The QR should contain a stable internal identifier.

Do not encode changing data such as:

- location
- owner
- condition
- checkout state

into the QR.

---

# 41. Label Printer

Hardware:

```text
SUPVAN T50M Pro
USB
```

Desired behavior:

```text
Kiosk / Admin UI
        ↓
Label Service
        ↓
Linux Printing Stack / Driver
        ↓
SUPVAN T50M Pro
```

Do a hardware proof-of-concept before making printing central to application architecture.

Verify:

- ARM compatibility
- USB recognition
- Linux driver reliability
- available label sizes
- QR readability
- print orientation
- repeatability
- behavior after reboot
- behavior if printer is disconnected

Do not assume a community driver is reliable until tested on this exact Pi.

---

# 42. Session Behavior

A user scans their badge once.

The session persists while they perform the current operation.

After completion, eventually return to anonymous state.

Potential timeout:

```text
30–60 seconds
```

Exact timeout is `[DECISION REQUIRED]`.

Do not log a user out halfway through an active multi-item checkout simply because a timer elapsed.

---

# 43. Touchscreen UX Requirements

Target display:

```text
7-inch touchscreen
```

Therefore:

- primary controls should be large
- approximately 44 px minimum touch target
- avoid tiny icons
- avoid hover-only actions
- minimize dense tables
- make status readable several feet away
- avoid long forms
- use high contrast
- do not depend on right-click
- important buttons should have text labels
- provide obvious Cancel/Back behavior
- prevent accidental destructive operations

---

# 44. Feedback

Scanning must give immediate feedback.

Potential feedback:

```text
GOOD SCAN
green visual confirmation
short beep
item appears in list
```

Error:

```text
INVALID / BLOCKED SCAN
different sound
clear explanation
```

Examples:

```text
Already scanned.
```

```text
This item is currently checked out to Jordan.
```

```text
This item is quarantined and cannot be checked out.
```

Do not simply ignore invalid scans.

---

# 45. Scan Debouncing

Camera scanners can read the same QR repeatedly.

Implement scan debouncing.

A scan should not produce:

```text
BAT-0182
BAT-0182
BAT-0182
BAT-0182
BAT-0182
```

within milliseconds.

---

# 46. Undo

Users will make mistakes.

Important flows should have:

```text
UNDO LAST SCAN
```

and/or:

```text
REMOVE FROM CART
```

Before transaction confirmation.

Avoid requiring administrator intervention for ordinary mistakes.

---

# 47. Error Recovery

Design explicitly for:

- camera unavailable
- printer unavailable
- barcode unreadable
- item QR destroyed
- product not found
- serial number missing
- Homebox temporarily unavailable
- database locked
- SD card nearly full
- kiosk browser crashes
- sudden power loss
- duplicate scan
- duplicate serial number
- asset already checked out
- unknown user badge
- invalid location
- maintenance asset scanned for checkout
- incomplete kit
- database backup failure

Each feature plan should include failure states.

No black boxes.

---

# 48. Timekeeping

Because the system will be offline and transaction history matters, reliable clock behavior matters.

Consider adding a Raspberry Pi RTC such as a DS3231.

This is a hardware recommendation, not yet a requirement.

The system should clearly surface clock problems rather than silently logging incorrect transaction times.

---

# 49. Backup / Recovery

The user must not lose inventory because an SD card fails.

Plan for easy backup.

Potential contents:

```text
Homebox database
Homebox attachments
Ops database
Map layouts
Product catalog modifications
Configuration
Label templates
Audit/event history
```

Potential destination:

```text
USB storage
```

or another approved lab system.

Backup policy is `[DECISION REQUIRED]` later.

Restore must also be tested.

A backup that has never been restored is not considered validated.

---

# 50. System Status Screen

Admin should be able to tell whether things are healthy.

Potential status:

```text
Homebox             ✓
Ops Service         ✓
Database            ✓
Camera              ✓
T50M Pro            ✓
Disk Space          41 GB free
Clock               ✓
Last Backup         02 OCT 16:10
Product Catalog     742,381 records
```

Avoid forcing administrators into Linux commands for routine diagnostics.

---

# 51. Security

This is an offline environment but should still be treated as a multi-user system.

Consider:

- API keys stored outside source control
- restrictive file permissions
- least-privileged Homebox integration account
- admin authentication
- audit events
- no PII in QR codes
- kiosk browser restrictions
- CSRF/session behavior
- physical access assumptions
- USB device assumptions
- local network access
- backup data protection

Do not claim the kiosk itself is a strong security boundary unless the threat model supports that.

---

# 52. Development Principle: No Black Boxes

A core requirement is maintainability.

When something breaks, an administrator should be able to determine:

- what failed
- why it failed
- where logs are
- what dependency is affected
- whether data is safe
- what corrective action can be taken

Provide useful logs.

Avoid overly clever architecture that is difficult to troubleshoot offline.

---

# 53. Recommended Project Phases

Do not attempt all features simultaneously.

## Phase 0 — Reconnaissance and Architecture

Goals:

- inspect Homebox code/API
- identify target Homebox version
- reproduce vanilla Homebox
- document integration points
- inspect Pi hardware constraints
- propose repository structure
- identify what belongs in Homebox vs Ops layer
- identify unresolved architectural decisions

No major feature coding yet.

### Required checkpoint

Present findings to user.

---

# 54. Phase 1 — Hardware Proof

Verify:

- Pi boots reliably
- touchscreen works
- kiosk browser works
- webcam works
- barcode/QR can be decoded
- keyboard works
- SUPVAN printer enumerates via USB
- test label can be printed

Do not build sophisticated application logic until hardware feasibility is understood.

### Required checkpoint

Show hardware findings and blockers.

---

# 55. Phase 2 — Homebox Baseline

Install a known Homebox build.

Document:

- version
- configuration
- storage locations
- Homebox API endpoints needed
- authentication/API-key process
- backup process

Create representative data:

```text
Workshop
Drone Cage
Shelf A1
Shelf A2
Shelf B1
Shelf B2
Charging Station
Maintenance
Quarantine
```

and representative assets.

### Required checkpoint

Show the baseline and API integration.

---

# 56. Phase 3 — Kiosk Shell

Create touchscreen UI shell.

Implement:

- home
- navigation
- session banner
- admin entry
- scan indicator
- status feedback
- inactivity behavior
- responsive sizing

Do not yet implement every backend operation.

### Required checkpoint

User should click through the interface and approve overall feel.

---

# 57. Phase 4 — Scan Infrastructure

Implement normalized scan service.

Support at minimum:

```text
User QR
Asset QR
Location QR
UPC/EAN
manual fallback
```

Implement:

- debounce
- invalid scan handling
- duplicate handling
- scan type routing

### Required checkpoint

Demonstrate each code type.

---

# 58. Phase 5 — Identity

Implement:

- local users
- badge token
- session start
- session end
- session timeout
- disabled/inactive user behavior

Resolve badge/PIN policy.

### Required checkpoint

Demonstrate user flow.

---

# 59. Phase 6 — Checkout

Implement:

- badge
- asset scanning
- cart
- batch checkout
- validation
- availability check
- condition display
- transaction creation
- custody update
- undo/remove
- confirmation

### Required checkpoint

User performs a complete checkout.

---

# 60. Phase 7 — Return

Implement:

- return scanning
- previous condition
- unchanged fast path
- changed-condition path
- destination
- transaction history
- custody clear
- optional maintenance routing

### Required checkpoint

User performs normal and damaged return.

---

# 61. Phase 8 — Workshop Map

Implement:

- room
- shelf/location objects
- location linking
- map display
- search result highlighting
- item → map location
- location labels

Then introduce editor functionality.

### Required checkpoint

User searches for an asset and sees its shelf visually highlighted.

This is one of the major project milestones.

---

# 62. Phase 9 — Kits

Implement:

- kit definition
- manifest
- completeness
- nested equipment
- kit checkout
- kit return
- missing component warnings

Resolve fast vs verified policy.

### Required checkpoint

Demonstrate complete and incomplete kit.

---

# 63. Phase 10 — Condition / Inspection

Implement:

- structured condition
- inspection
- notes
- photo
- issue reporting
- quarantine
- maintenance transition

### Required checkpoint

Demonstrate damaged-equipment workflow.

---

# 64. Phase 11 — Enrollment

Implement:

```text
barcode
→ catalog lookup
→ serial
→ location
→ asset
→ label
```

Keep typing minimal.

### Required checkpoint

Enroll a completely new item end-to-end.

---

# 65. Phase 12 — Search / Browse

Implement:

- Find Item
- Browse Stock
- filters
- asset overview
- history
- map link

### Required checkpoint

Ask user to find several items without instructions.

---

# 66. Phase 13 — Administration

Implement:

- users
- locations
- map editor
- labels
- categories/types
- possibly kit policies
- system status
- backup controls

Keep admin UI distinct from kiosk workflow.

---

# 67. Phase 14 — Offline Hardening

Remove accidental network assumptions.

Test with Ethernet/Wi-Fi disconnected.

Verify:

- startup
- inventory
- scans
- labels
- maps
- product catalog
- checkout
- return
- authentication
- logs
- documentation

Everything core must still work.

---

# 68. Phase 15 — Recovery Testing

Test:

- abrupt reboot
- application crash
- Homebox restart
- full service restart
- corrupted transaction attempt
- disconnected camera
- disconnected printer
- disk warning
- restore from backup

Document recovery.

---

# 69. Phase 16 — User Testing

Give the terminal to someone who has not been taught how it works.

Ask them to:

```text
check out a drone
return a battery
report damaged equipment
find a controller
locate a battery shelf
browse available drones
```

Do not coach them unless necessary.

Observe confusion.

Every explanation we have to verbally give is a potential UX defect.

---

# 70. Per-Feature Planning Documents

Eventually create individual implementation files.

Suggested structure:

```text
docs/features/
    001-kiosk-shell.md
    002-scanner-service.md
    003-user-badges.md
    004-checkout.md
    005-return.md
    006-condition.md
    007-workshop-map.md
    008-location-management.md
    009-kits.md
    010-product-catalog.md
    011-equipment-enrollment.md
    012-label-printing.md
    013-maintenance.md
    014-find-item.md
    015-browse-stock.md
    016-audit-history.md
    017-backup-recovery.md
    018-system-status.md
```

Do not create all of these with speculative details immediately.

Write each when its design is being actively resolved.

---

# 71. Required Template for Feature Plans

Every feature plan should contain:

```text
# Feature

## Problem

## User Goal

## User Experience

## Current Homebox Behavior

## Proposed Behavior

## Scope

## Out of Scope

## User Decisions

## Data Model

## API Changes

## Homebox Integration

## UI Changes

## Hardware Dependencies

## Security Considerations

## Offline Considerations

## Failure Modes

## Logging / Diagnostics

## Implementation Steps

## Unit Tests

## Integration Tests

## Hardware Tests

## User Acceptance Tests

## Upgrade / Migration Considerations

## Rollback Plan

## Definition of Done
```

---

# 72. Coding Standards for This Project

Prioritize:

- understandable code
- modular components
- typed interfaces where appropriate
- explicit state
- clear error messages
- tests around workflow
- structured logging
- reproducible builds
- minimal dependencies
- offline installation
- maintainability by someone other than the original author

Do not optimize for cleverness.

---

# 73. Do Not Modify Upstream Homebox Casually

Before changing Homebox itself, answer:

1. Can this be implemented through the supported API?
2. Can the behavior live in the Ops service?
3. Can the behavior live in the kiosk?
4. Would a Homebox custom field/entity relationship solve it?
5. Would upstream Homebox likely implement something similar?

Only modify Homebox core when there is a strong justification.

If modifying upstream code is proposed:

`[DECISION REQUIRED]`

Explain why the integration approach is insufficient.

---

# 74. Version Pinning

Because this system becomes air-gapped:

Record exact versions of:

- Raspberry Pi OS
- Homebox
- project source
- runtime
- libraries
- barcode decoder
- printer driver
- database migrations
- browser

Prefer reproducible dependency locks.

Do not rely on:

```text
latest
```

for offline deployment.

---

# 75. Future Possibilities — Do Not Build Yet

Possible future enhancements:

- NFC badges
- RFID asset tags
- handheld scanners
- multiple kiosks
- reservation system
- expected return times
- calibration tracking
- consumable inventory
- notifications
- mobile interface
- battery cycle tracking
- automatic battery-health imports
- mission loadout templates
- visual floor maps for multiple rooms
- storage-bin capacity
- advanced reporting
- CSV imports
- additional barcode databases
- computer vision / OCR
- AI-assisted inventory lookup

These should not distract from the core product.

---

# 76. Minimum Viable Product

The MVP is successful when a user can:

### 1. Identify themselves

```text
Scan badge
```

### 2. Check out equipment

```text
Scan asset
Confirm
```

### 3. Return equipment

```text
Scan asset
Confirm condition
Confirm location
```

### 4. Find something

```text
Search / scan
→ location
→ highlighted shelf on workshop map
```

### 5. Report a problem

```text
Scan asset
→ condition
→ note
```

### 6. Administer locations

```text
Create room
Create shelf
Link to Homebox
Print QR
```

### 7. Enroll equipment

```text
Scan product
→ serial
→ location
→ create
→ print label
```

Everything else builds on this.

---

# 77. Success Metric

The project is not successful merely because every feature technically works.

Success means ordinary users actually keep the inventory accurate.

For common workflows, measure:

- number of taps
- number of scans
- elapsed interaction time
- number of fields requiring typing
- error rate
- number of times users need help
- number of screens visited

When choosing between designs, prefer the one that reduces friction while preserving accountability.

---

# 78. First Assignment for Codex

**Do not begin by implementing the entire project.**

First perform reconnaissance.

### Step 1 — Inspect the repository/environment

Determine:

- whether Homebox source is already present
- Homebox version/commit
- project directory structure
- current build/deployment method
- whether custom code already exists
- Raspberry Pi target architecture
- current available tests
- current API surface
- whether any previous experiments should be preserved

### Step 2 — Run vanilla Homebox

Confirm baseline operation.

Do not modify it yet.

### Step 3 — Research integration points

Specifically inspect:

- unified entity API
- locations
- parent/child entities
- attachments
- maintenance
- QR generation
- barcode lookup
- API keys
- custom fields
- entity types
- templates
- export/import
- relevant events/history

Document actual endpoint behavior instead of guessing.

### Step 4 — Examine Raspberry Pi constraints

Identify likely resource concerns.

### Step 5 — Examine T50M Pro support

Do not write printer integration yet.

Determine whether the selected Linux printing approach is viable on Raspberry Pi ARM.

### Step 6 — Propose project structure

Present something such as:

```text
inventory-system/
├── upstream/
│   └── homebox/
│
├── kiosk/
│
├── ops/
│
├── catalog/
│
├── deploy/
│
├── tests/
│
└── docs/
```

This is an example, not an instruction to use exactly this structure.

### Step 7 — Produce architecture findings

Create:

```text
docs/00-project-overview.md
docs/01-homebox-reconnaissance.md
docs/02-architecture-proposal.md
docs/DECISIONS.md
docs/PROJECT_STATE.md
```

### Step 8 — STOP

Do not start implementing checkout.

Present the findings to the user.

Use:

```text
[CHECKPOINT — INITIAL ARCHITECTURE]
```

Explain:

- what Homebox already gives us
- what needs custom development
- recommended architecture
- expected Pi limitations
- major risks
- decisions that need to be made before Phase 1

Then wait for user feedback.

---

# 79. Initial Questions You May Need to Ask

Do not dump every question at once.

During the initial architecture checkpoint, prioritize only questions that truly block the next phase.

Likely early decisions include:

### Question A — Homebox Strategy

Should this remain:

```text
Homebox + external kiosk/Ops application
```

as much as possible?

This is currently the preferred architecture.

---

### Question B — User Authentication

For the first prototype:

```text
Badge only
```

or:

```text
Badge + PIN
```

Recommendation for initial UX testing:

```text
Badge only
```

unless policy requires stronger authentication.

---

### Question C — Workshop Map Editor

For MVP, should map editing initially support:

```text
simple placement/grid
```

or immediately support:

```text
free drag + resize + rotate
```

Recommendation:

Start simple enough to validate the concept but design the data model so free-form positioning is possible.

---

### Question D — Location on Return

Possible flows:

```text
Return asset
→ scan destination every time
```

versus:

```text
Return asset
→ default known home location
→ scan a different destination only if needed
```

This materially affects convenience and location accuracy.

Ask the user before implementing.

---

### Question E — Kit Verification

Determine whether initial kit checkout is:

```text
fast
```

or:

```text
verified
```

or configurable.

---

# 80. How to Present Questions to the User

Do not ask:

> What do you want?

Provide useful context.

Example:

```text
[DECISION REQUIRED — Return Location]

There are two good approaches.

A. Require the user to scan the shelf every time.

Pros:
- maximum physical-location accuracy

Cons:
- adds another action to every return

B. Default to the item's assigned home shelf and only scan a different
location when needed.

Pros:
- faster routine return
- less friction

Cons:
- assumes users actually put the item back where it belongs

My recommendation for this system is B because our core design principle is
making the common path extremely fast.

Which behavior do you want?
```

This is the expected collaboration style.

---

# 81. Do Not Silently Expand Scope

If you discover something interesting, say:

```text
[IDEA — NOT CURRENT SCOPE]
```

and explain it.

Do not automatically build it.

The user should remain in control of product scope.

---

# 82. Preserve Working Systems

Before risky changes:

- commit
- tag or branch when useful
- ensure tests pass
- make database backup where relevant
- document migrations

Do not put the prototype in a state where the only way forward is continuing an unfinished migration.

---

# 83. Testing Philosophy

Every feature has three different questions.

## Technical

Does the code work?

## Operational

Does the workflow survive real-world problems?

## Human

Will someone actually use it correctly?

All three matter.

---

# 84. Example Acceptance Test

For checkout:

Give a test user no instructions other than:

> Check out this drone and these two batteries.

Success means they naturally:

1. press Check Out
2. scan their badge
3. scan three items
4. understand their condition
5. confirm
6. leave

If they ask:

> Where do I click now?

record that as UX feedback.

---

# 85. Product Tone

The terminal should feel:

- professional
- utilitarian
- fast
- obvious
- trustworthy

Not:

- playful
- cluttered
- over-animated
- AI-generated
- dashboard-heavy
- overly technical

The user should feel that it is an equipment terminal, not a generic web application.

---

# 86. Final Operating Instruction

Throughout the project:

> Build with the user, not merely for the user.

Engineering decisions that do not affect product behavior can proceed.

Product decisions should be surfaced.

After every major functional milestone:

```text
build
→ test
→ demonstrate
→ user feedback
→ adjust
→ continue
```

Do not spend weeks implementing downstream features based on an unvalidated workflow.

The highest priority is not completing the largest number of features.

The highest priority is ensuring the system becomes something the team will actually use correctly.