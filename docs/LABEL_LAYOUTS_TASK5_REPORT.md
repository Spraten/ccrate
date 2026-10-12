# Label layout maker Task 5 acceptance report

Status: implementation, isolated builds, browser fixtures and the full Python suite passed. A public candidate is staged at `work/label-layout-release-candidate`. This is a review handoff only: no deployment, service restart, private archive, live API, or physical printer action was run.

## Scope and behavior

The native Label maker and Equipment Terminal compose, print and download authoritative reviewed Letter pages. Each explicit Compose, Print or PDF action calls the paper authority again and uses its frozen PNG bytes and 215.9 × 279.4 mm geometry; no action rerenders current item values. The shared PrintDesignPro helper emits exact-size PDF pages or opens the browser print dialog at Actual Size / 100%, with one physical page per returned image. Users must disable headers and footers. Closing the dialog reports physical output as unconfirmed and leaves the pages available. These paper actions do not write Pi print or import status.

Terminal now appends and exposes the reviewed sheet Compose control. The frozen exporter reuses the pinned PrintDesignPro code and same-origin asset route. It validates context after frame load and immediately before the actual print/PDF call. The scoped CSP permits only local assets and the same-origin nested print frame. UUIDv4 nonces, editor request IDs, Save keys and palette element IDs use `crypto.getRandomValues` where `crypto.randomUUID` is unavailable on ordinary HTTP LAN origins; no Math.random fallback is used.

## Builds and verification

The standalone editor was built with:

```sh
python3 deploy/build-label-ui.py --source-root . --output work/label-ui-build
```

The pinned build transformed 463 modules and completed in 5.07 seconds. The manifest records 14 runtime assets and 15 source inputs; its SHA-256 is `f1952a543fdd4348b4af290bcd8a6afa3d38da84bd15465d75a4fdb97f8358cd`. Vendor source SHA-256 is `8beea34af7c96be36edfc9b979d7d43fd216f790a9bc8b9b6ea810de2b14a32c`; coherent patch SHA-256 is `bcf620171148a43a82f8bbac19fb3c79600754a8a5a1fbd5d229888c31fb06c6`. The patch applies cleanly to pinned upstream commit `eb118cc05b169c554066d823c44dc179aa3b96bb` with `git apply --check --whitespace=error`; source `git diff --check` passes (excluding normal unified-diff context markers in the patch).

The native host was prepared and generated with:

```sh
python3 deploy/build-homebox-ui.py --toolchain-root /home/user/Desktop/inventory-system/work/toolchains --upstream-root /home/user/Desktop/inventory-system
```

The build exited 0. Typecheck reported 43 pre-existing diagnostics and zero added. Nuxt generated 24 routes; the client transformed 4,594 modules and completed in 2m49s, and the server build completed in 285ms. Existing output included component-name/circular-chunk and large-chunk warnings, plus the PWA glob warning for unmatched `**/_payload.json`; the PWA generated its existing 3-entry precache. The accepted native source pin is `e01dd737238a3fa7e1a6454b37de6c6fc88c86e4`.

The full offline verifier command passed:

```sh
PYTHONPATH=/home/user/Desktop/inventory-system/work/hardware/python python3 deploy/verify-label-layouts.py --source-root . --output work/label-layout-final-acceptance --offline
```

Its complete JSON evidence is in `work/label-layout-final-acceptance/compatibility-report.json`. It covers 800×480, 1366×850 and 390×844 browser viewports; exact frozen paper pages; native queue Print/PDF callbacks; Terminal Print/PDF callbacks; fresh paper checks; actual page-byte SHA-256 `45bb2de7145aeddc941224a4a3dc33430c0831cb6cd611af66153d6603a41a34`; one stubbed print call; a real PDF with one 612×792-point Letter page; retained pages and unconfirmed output after `afterprint`; zero Pi writes; delayed paper and exporter identity switches suppressing stale output; cut-guide and zero/subpixel-gutter geometry; and unchanged SUPVAN behavior.

The verifier also served both editor hosts from `http://inventory.test` to exercise a non-secure LAN-like origin where `crypto.randomUUID` is absent and `crypto.getRandomValues` is available. Both hosts mounted with UUIDv4 nonces. The iframe editor loaded, created a UUIDv4 palette element and saved with a UUIDv4 request key. Valid nonce/source/origin messages were accepted, while forged nonce, source and origin messages were rejected.

The full test command passed all 290 tests in 84.853 seconds. Its full log is `work/label-layout-final-acceptance/unittest.log`:

```sh
PYTHONPATH=ops:kiosk:/home/user/Desktop/inventory-system/work/hardware/python python3 -m unittest discover -s tests -v
```

The suite includes paper authority rejection before composition, finite/nonfitting geometry, frozen label rendering, output limits, import-safe backup/runtime/install helpers, and matched-candidate staging checks. The Terminal button-flow fixture is dynamic; the actual native queue Print/PDF flow is also dynamic. Existing desktop route tests and static/context fixtures cover Terminal API routes and identity changes. No physical scan, scale, disconnect, or printer output was attempted.

## Candidate and rollback boundaries

The public candidate is assembled by `deploy/stage-label-release.py` under `work/label-layout-release-candidate`. Its `release-manifest.json` hashes the candidate files and records the matched native pin, native/static linkage, Terminal tree, Python dependencies, editor source/build inputs and three identical editor runtime manifests. The candidate contains no private label database, intents or journals. The source report and manifest are copied into the candidate; the candidate manifest is the authoritative file-by-file hash list. Replacing a previous staged candidate first checks its builder marker and only restores owner write/search permissions on real directories inside that verified tree; unowned candidates and symlinks are rejected.

The previous public snapshot has 390 files whose recorded sizes and SHA-256 values verify. Eight bounded receipt files also verify. The earlier desktop baseline receipt is recorded as `partial_known_failure`, with `full_desktop_suite_passed` false; these receipts do not prove legacy print/recovery code can safely roll back while a new label intent is unresolved. Preserve the companion database and resolve outstanding label intents before any code rollback. The isolated native build is based on the older CACI-Create header baseline. Tasks 1–4 are not yet integrated into the deployed C-Crate tree, so central integration must apply the complete accepted Task 1–5 delta from baseline `b863f6a` (Task 1 `e6c7188`, Task 2 `0883139`, Task 3 `330a849`, Task 4 `6b327cf`, plus this Task 5 work) onto the current C-Crate base while preserving its deployed rename, header and branding assets. Then rebuild and repeat acceptance. This candidate is **not deployable as-is**. No release selector or deployment action was added here.
