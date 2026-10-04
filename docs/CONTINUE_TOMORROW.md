# Continue the equipment project

Working directory: /home/user/Desktop/inventory-system. Read AGENTS.md first. Preserve real inventory; no demo seeding or live mutation tests. Homebox remains the inventory authority. Never blindly retry an uncertain create, return, or print.

Recent completed work:
- a12124c: separate browser sessions, recoverable touchscreen navigation, checkout and return review, saved CSV drafts, laptop disconnect behavior.
- a300720: optional per-item return_note, badge-author name snapshot and completed-return timestamp in Activity history. Routine notes do not overwrite native condition notes. Recovery preserves notes; cancelled returns do not publish them.
- dff0596: offline HTML user/admin guide with 23 chapters and 13 intercepted training screenshots. Pi desktop: Equipment User Guide. Source: docs/user-guide/index.html.

Services: homebox-native.service (127.0.0.1:17745) and homebox-companion.service (127.0.0.1:17749), user services. Pi Desktop Equipment Terminal opens the kiosk. Laptop SSH launcher is deploy/Open-Workshop.ps1. Dedicated direct cable IP 10.77.0.1; other configured address 192.168.1.61.

137 unit checks, 37 fixture browser interactions, six isolated HTTP checks and ten read-only live-navigation checks passed after return notes. Guide image loads, anchors, audience filter, screenshot modal, Escape, print CSS, and 1280/800/390px layouts passed.

Safe regression commands:
```
PYTHONPATH=ops:kiosk:work/hardware/python python3 -m unittest discover -s tests -q
python3 deploy/verify-workflow-navigation.py
python3 deploy/verify-workflow-http.py
python3 deploy/verify-workflow-live-navigation.py
```

Use git status before changes. Existing untracked camera diagnostic/reopen scripts belong to earlier work; do not delete or stage them blindly. Credentials, personal badge tokens, backups and auth files stay private on the Pi. Admin is temporarily open by user decision. Protect it before broad deployment. The room editor currently supports one rectangular room; additional rooms are future work.

This document carries project context. The existing Windows chat history does not automatically become a new Pi CLI conversation. Ask the new agent to read this file and the relevant source before continuing.
