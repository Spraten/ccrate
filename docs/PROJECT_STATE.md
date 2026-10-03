# Current Phase

Hardware proof checkpoint accepted by user on 2026-10-02. Next: Phase 2 Homebox baseline completion.

# Working

- Pi desktop Git project at /home/user/Desktop/inventory-system.
- Unmodified Homebox v0.26.2 pinned as submodule; isolated baseline on loopback port 17745.
- Native API entity, location, field, key, QR/label and dated maintenance probes passed.
- Touch targets and printer test accepted by user; printer idle without errors.
- Camera captures 640 by 480 at approximately 10 FPS; browser camera settings verified.
- User confirms all hardware tests good. Physical QR acceptance is user-reported; no decoded scan recorded in UI telemetry.

# Decisions

- Companion interaction layer; keep Homebox native and unmodified.
- No extra inventory database approved.
- Permanent deployment and printer permissions still undecided.

# Known Problems

- Previous intermittent SSH and USB webcam failures; long-duration stability unproven.
- No RTC; offline timekeeping unresolved.
- Source/API schema drift; maintenance creation requires a date.

# Next

Complete representative Homebox workshop data and document backup/restore process; demonstrate baseline before kiosk shell design. No checkout implementation yet.

# Resume

Private synthetic baseline credentials, pepper, PID and logs are under restricted work/baseline. Do not expose them. Diagnostic UI is loopback port 17746; scripts in deploy. Work artifacts are ignored by Git. Preserve source and existing test data.
