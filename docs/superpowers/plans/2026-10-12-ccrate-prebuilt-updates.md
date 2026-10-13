# C-Crate Prebuilt Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install verified, prebuilt C-Crate updates on a supported existing Pi installation without compiling application code or dependencies on the Pi.

**Architecture:** Build and cache the three existing components off-device, then seal a candidate with real source/build/test evidence. A standard-library updater stages the trusted package and uses the existing O/C/F release transaction, private backup and compatible recovery logic. Keep production runtime dependencies and user stores outside application bundles.

**Tech Stack:** Python standard library, existing release/backup helpers, GitHub Actions/Releases, Go, Node.js/pnpm, Nuxt/Vue and Vite.

**Spec:** [C-Crate updates and desktop design specification](../specs/2026-10-12-ccrate-updates-and-desktop.md), sections Global constraints and A.

## Current operator-requested delivery: desktop manager source updates

On 2026-10-13 the operator requested a working update action in the desktop
terminal manager, rather than an unavailable installer. The immediate delivery
uses the installed toolchains to build a pinned `origin/main` revision in an
isolated staging directory. The prebuilt publishing pipeline below remains a
separate future optimization; it is not a prerequisite for this source path.

Implementation sequence:

1. Prepare a sealed candidate with real build receipts, source identity, and
   executed artifact-bound compatibility checks, without stopping services.
2. Extend the existing release transaction only where needed to support a
   caller-held lock and verified external compatibility evidence for the
   installed valid format-2 bundle. Do not alter sealed previous artifacts or
   add another selector/rollback mechanism.
3. Under one transaction lock, stop writers, create and verify a private whole
   store snapshot, verify compatible recovery, then activate through
   `select_bundle`. Preserve interrupted-transaction recovery and never restore
   old data or replay physical output automatically.
4. Wire the manager's update check, exact-revision approval, progress, completion
   identity, and recovery controls to the real installer. Test success and
   failure paths with disposable data and simulated services.

Development of this script does not authorize running an update, restarting the
live services, or copying operational data into development fixtures. The
operator will run the completed manager and explicitly approve activation.

### Operator simplification, 2026-10-13

The operator subsequently requested a simple manager and explicitly rejected
mandatory backups, exhaustive test gates, and further manager work while the
site was awaiting activation. The completed d877b35 build is now live; old
application releases were removed and data/configuration retained. The
operator has now authorized manager rework while continuing to use the site.

For this manager delivery, replace the source-update activation sequence above
with the direct flow used successfully on this installation: prepare the exact
approved source (or explicitly reuse a completed build), validate/stage the
application, stop services, atomically switch the selected release, start, and
check the actual local HTTP responses. Keep backup as an optional operator
action. Do not require O/C/F production-data copies or the broad repository
test suite for a normal manager update. Preserve data/configuration and show
failed/interrupted states honestly. Manager development must not restart,
update, or mutate the installation the operator is currently using. Verify the
workflow with small disposable fixtures and simulated service/build calls.

## Global Constraints

- Homebox remains the inventory, account, collection and native-history authority.
- Preserve authentication, collection isolation, manager/owner checks, durable request identities and uncertain-result recovery.
- Keep databases, photos, credentials, peppers, badge keys and private backups outside public source and release assets.
- No new application dependencies; reuse installed components, PrintDesignPro, existing helpers and standard libraries.
- Maintain the pinned Homebox submodule e01dd737238a3fa7e1a6454b37de6c6fc88c86e4 and PrintDesignPro eb118cc05b169c554066d823c44dc179aa3b96bb; retain licenses.
- Build with Go 1.26.0, Node.js 24.21.0 and pnpm 10.28.0; retain both existing dependency lockfiles.
- Do not change the pinned upstream checkout or generated work/ files as maintained product source.
- Pi target is Linux ARM64 with GOOS=linux, GOARCH=arm64, CGO_ENABLED=0 and GOARM64=v8.0; refuse other hosts before activation.
- Existing deployment root and runtime prerequisites must be checked locally; no SSH access is available to the agent.
- Preserve ports 17745 (gateway), 17747 (private native API) and 17749 (Equipment Terminal), with current authentication and exposure rules.
- Never run operational deployment, service restart, data mutation, physical print or camera calibration without explicit operator authorization.
- Automated tests use disposable data, intercepted APIs or verifier-owned loopback services; never the operational Pi.
- Desktop acceptance sizes are 1280x800 and 1440x900 at 100% browser zoom, plus keyboard and 200% zoom checks.
- Mobile refinement and optional new features are deferred.
- Execution uses isolated branches/worktrees and parallel independent work, as requested; coding workers use GPT-6 Luna Low and the final reviewer uses GPT-6.1 Sol High.

## Review Focus

- Unknown backup formats or a backup missing the selected sealed release must fail before activation; Task 1 tests producer-to-consumer acceptance and offline restoration.
- A changed source, lockfile or compiler must invalidate the correct cache; Task 2 tests fingerprints and corrupted cached outputs.
- An untrusted, truncated, wrong-architecture or escaping archive must never execute code or replace a release; Task 4 tests download/staging refusal.
- A supported-looking bundle on a legacy or incomplete install must not adopt or replace stores; Task 4 tests preflight migration/runtime refusal.
- Candidate exposure, store changes or power loss must recover with compatible code and never replay output; Tasks 5-6 test fresh matched evidence and interrupted O/C/F selection.

---

## File Structure and Work Ownership

| Files | Responsibility |
|---|---|
| deploy/backup-deployment.py, deploy/publish-users.py | Complete private backup and supported producer/consumer contract |
| deploy/build-homebox-backend.py, Dockerfile | Independent backend build and isolated local-test build stages |
| deploy/build-release.py (new) | Component fingerprints/cache, actual evidence capture, sealing and archive metadata |
| .github/workflows/release.yml (new) | Trusted CI checks, component cache and release publication |
| deploy/update-ccrate.py (new) | Trusted download, bounded staging, preflight and operator update entrypoint |
| deploy/verify-update.py (new) | Artifact-only fallback assembly and private offline upgrade verification |
| deploy/release_bundle.py, deploy/run-release.py | Existing immutable validation, selector transaction and packaged launchers; extend only required contracts |
| tests/test_build_release.py, tests/test_update_ccrate.py, tests/test_update_compatibility.py (new) | Focused fixtures for the new entrypoints |
| tests/test_release_bundle.py, tests/test_release_launchers.py, tests/test_shelf_checks_backup.py | Retained authority and regression coverage |
| README.md, docs/C_CRATE_RELEASE.md | Exact operator commands, prerequisites and migration refusal instructions |

Tasks 1 and 2 can run in parallel on separate branches. Task 3 owns CI/packaging; Task 4 owns the updater and can start after the descriptor contract is fixed. Tasks 5 and 6 are dependent. Shared release helpers and README have one editor at a time. Plan self-review is performed by the implementer, not delegated.

All python3/test/build commands below run in Linux WSL or CI with the existing fixture dependencies, not the Windows system Python. Required tests may not be counted as passed when skipped for missing prerequisites. Local Docker remains a disposable test stack; its native binary targets its own container architecture. Only the release orchestrator forces Linux ARM64.

### Task 1: Make the cold backup restorable and publication-compatible

**Files:** Modify deploy/backup-deployment.py, deploy/publish-users.py; test tests/test_shelf_checks_backup.py and tests/test_release_bundle.py.

**Interfaces:**
- Consume existing database_inventory(root), checkpoint_databases(root, databases), build_backup_manifest(root, *, created_at, commit, homebox_pin, members, databases), create_archive(root, target, members, manifest).
- Produce create_cold_backup(root: Path, *, manage_services: bool = True) -> dict with status, backup filename, bytes and database_integrity; main() delegates to it. With manage_services=False the caller already owns the service-stop transaction, and this function never starts/stops services.
- Extend the format-2 backup manifest with selected_release {relative_path, manifest_sha256, files}, capture its immutable files and reconstruct application-current only after restore validation. Keep format-1 support for genuine older archives; missing required sealed-selection data is not acceptable for a current sealed installation.

- [ ] **Step 1: Add failing producer/consumer and restore fixtures.** Use disposable SQLite stores and a real synthetic sealed selection. Assert:

      self.assertEqual(manifest['format'], 2)
      publisher['_validate_backup_members'](archive, manifest)  # no error
      self.assertEqual(restored_selector.resolve(), restored_release)
      self.assertEqual(restored_private_store_digest, original_private_store_digest)

  Add test_format2_backup_restores_selected_release, test_unknown_backup_format_is_refused and test_transaction_backup_does_not_restart_services. Unknown format 99 must raise BundleError; a missing selected bundle and changed archived hash must also fail.
- [ ] **Step 2: Run python3 -m unittest tests.test_shelf_checks_backup tests.test_release_bundle -v.** Expect new cases to fail on the current format mismatch/missing selection.
- [ ] **Step 3: Implement the interfaces above.** Accept formats (1, 2) without weakening path/member/hash/privacy checks; stop gateway as well as writers when the helper owns shutdown. Capture all current stores, photos/journals and selected package. Extend receipt validation and offline restore checks instead of restarting an obsolete flat binary.
- [ ] **Step 4: Run the same tests plus tests.test_release_launchers.** Expect all affected fixtures to pass; no operational service calls are allowed in these tests.
- [ ] **Step 5: Commit.** Stage only these files; commit message: fix: preserve selected releases in compatible cold backups.

### Task 2: Separate component builds and verify reusable caches

**Files:** Create deploy/build-release.py and tests/test_build_release.py; modify deploy/build-homebox-backend.py and Dockerfile; retain deploy/build-homebox-ui.py and deploy/build-label-ui.py as component builders.

**Interfaces:**
- component_fingerprint(component: str, source_root: Path, tools: dict) -> str, with component in backend/frontend/labels and tools containing the captured relevant exact versions.
- build_component(component: str, *, source_root: Path, toolchain_root: Path, cache_root: Path) -> dict with fingerprint, output_path, outputs {relative_path: {sha256, size, mode}}, build_receipt and cache_hit.
- Backend builder gains --external-frontend and explicit Linux ARM64 build environment. In that mode embed a fixed gateway-directed placeholder, not work/homebox-ui-current. Preserve the legacy default until all callers/tests are migrated.

- [ ] **Step 1: Add tests test_frontend_edit_does_not_invalidate_backend_or_labels, test_backend_edit_invalidates_backend, test_toolchain_and_lock_changes_invalidate_cache and test_corrupt_cache_is_rebuilt.** Assert exact fingerprint changes and captured builder invocation counts, not merely Dockerfile strings. Also assert the backend artifact is ARM64 and independent mode succeeds without a current frontend tree.
- [ ] **Step 2: Run python3 -m unittest tests.test_build_release -v.** Expect missing interfaces/independent build behavior to fail.
- [ ] **Step 3: Implement fingerprint/cache behavior and split Docker build stages.** Backend keys include its builder, native overlays, upstream backend pin/content, Go version and target; frontend keys include its builder/overlay, kiosk bridge/branding inputs, upstream frontend pin/content, frontend lock and Node/pnpm versions; label keys include its builder, complete vendor/source/public/patches, label lock and Node/pnpm versions. Use existing cache directories for dependencies; store verified component outputs under work/component-builds. The release orchestrator supplies ARM64 environment values; direct local Docker builds retain their native target so the isolated x64 stack can execute its binary. Do not cache private data or source from an unverified submodule/dirty publication checkout.
- [ ] **Step 4: Run the focused tests and a cold/warm isolated build.** Edit only a disposable frontend copy and assert zero backend/label builder calls on the warm run. Execute the binary on an ARM64 runner, inspect its ELF architecture and test gateway-served UI separately. Record measured timings without claiming Pi timings.
- [ ] **Step 5: Commit.** Commit message: build: separate and cache C-Crate component builds.

### Task 3: Capture real evidence and publish sealed candidates

**Files:** Modify deploy/build-release.py; create .github/workflows/release.yml; test tests/test_build_release.py, tests/test_release_bundle.py and tests/test_release_launchers.py.

**Interfaces:**
- capture_verification(source_root: Path, artifacts: dict) -> dict, running the configured isolated checks and recording actual outcomes, source entries and closure hashes.
- package_release(source_root: Path, component_results: dict, verification: dict, destination: Path) -> dict, using stage_bundle and returning the descriptor from spec section A.
- CLI: python3 deploy/build-release.py --source-root . --toolchain-root work/toolchains --output work/releases/COMMIT.
- Produce ccrate-linux-arm64-COMMIT12.tar.gz, release.json and SHA-256 metadata. Candidate contains public/ccrate-release.json {format:1, application:'ccrate', commit:40-hex, upstream_pin:40-hex, built_at:UTC ISO timestamp}.
- Preserve the public metadata's UI-build meaning during F recovery. F keeps O's exact public/terminal tree; update CLI output names the actual selected manifest/runtime separately instead of changing O's captured UI bytes.

- [ ] **Step 1: Add test_failed_or_empty_verification_cannot_publish, test_package_binds_actual_source_and_artifacts, test_package_excludes_private_inputs and test_release_descriptor_matches_archive.** Start with private sentinel files and assert they are absent from archive membership and receipts. Mutated runtime files, cached bytes, modes or label assets must cause refusal; stage_bundle must validate the actual candidate as format 2.
- [ ] **Step 2: Run python3 -m unittest tests.test_build_release tests.test_release_bundle tests.test_release_launchers -v.** Expect the new producer tests to fail before implementation.
- [ ] **Step 3: Implement actual evidence capture and sealing.** Persist raw build/test receipts and their canonical/raw hashes. Execute artifact-bound workshop_read_v1, workshop_read_v2 and workshop_write_v2 cases; bind capability to the exact runtime/static/native closure. A cache hit retains original component build evidence and adds a current assembly/verification receipt. No test outcomes may be fabricated from expected values.
- [ ] **Step 4: Add the CI workflow and exercise it on a branch.** Pin toolchains/actions; run checks for PRs; publish only trusted main/tag builds after checks. Use an ARM64 runner for native execution. Cache each component independently, bind release tag to source commit and publish the exact descriptor/archive digests. Run tests again; expect a valid downloaded candidate and no public private-data artifacts. Fold publication docs into this task.
- [ ] **Step 5: Commit.** Commit message: ci: publish verified prebuilt ARM64 releases.

### Task 4: Stage trusted downloads and report installation readiness

**Files:** Create deploy/update-ccrate.py and tests/test_update_ccrate.py; modify README.md operator instructions.

**Interfaces:**
- fetch_release(tag: str, *, opener=urllib.request.urlopen) -> dict, resolving only Spraten/ccrate release/tag/asset identity and validating the spec descriptor.
- stage_download(root: Path, release: dict, *, opener=urllib.request.urlopen) -> Path, returning the verified candidate package directory.
- preflight(root: Path, candidate: Path) -> dict with status ready/migration_required/runtime_missing/unsupported_arch/insufficient_space, candidate path, previous path and redacted reasons.
- CLI --root PATH --version TAG --check stages/preflights only; --apply invokes Task 6 after preflight. Reject simultaneous/missing mode flags. Imports are inert.

- [ ] **Step 1: Add test_rejects_wrong_repository_tag_digest_or_architecture, test_partial_download_keeps_active_release, test_tar_escape_links_duplicates_and_devices_are_refused, test_check_never_stops_services and test_legacy_or_missing_runtime_requires_operator_repair.** Assert archive limits 512 MiB compressed, 1 GiB expanded, 20,000 members and descriptor 256 KiB; test limits without allocating those sizes. Candidate/store sentinels must remain unchanged on every failure.
- [ ] **Step 2: Run python3 -m unittest tests.test_update_ccrate -v.** Expect missing staging/preflight interfaces to fail.
- [ ] **Step 3: Implement bounded HTTPS staging and preflight.** Bind commit/tag and archive digest to the trusted GitHub metadata before extraction; validate all members before writing under work/update-downloads. Call the installed trusted validate_bundle before packaged code executes. Check actual installed runtimes and data paths, not USB connection state. Compute space from actual sizes plus fallback/backup needs and 100 MiB reserve; never clear old data to make room. Fail closed on unsupported selectors; document migration_required instead of quietly adopting a legacy install.
- [ ] **Step 4: Run the tests with a local intercepted release server and verify the check command.** Expect readiness results and zero compiler, package-install, print or service-stop calls. A disconnected camera/printer must not by itself block a software update.
- [ ] **Step 5: Commit.** Commit message: feat: stage and preflight trusted prebuilt updates.

### Task 5: Prepare compatible fallback and genuine local upgrade evidence

**Files:** Create deploy/verify-update.py and tests/test_update_compatibility.py; modify only necessary release_bundle.py provenance extension points and updater calls; retain deploy/verify-release-rollback.py fixture behavior.

**Interfaces:**
- assemble_fallback(previous: Path, candidate: Path, destination: Path, *, verification: Callable[[Path], dict]) -> Path; retain candidate native/ops/deploy/kiosk Python/label bytes and previous public/non-Python kiosk bytes. The callback executes closure checks against the actual owned staging tree before it is sealed and supplies real outcomes; it is not a predeclared success dictionary.
- verify_upgrade_pair(root: Path, previous: Path, candidate: Path, fallback: Path, backup_archive: Path) -> dict; privately restores the actual snapshot into owned temporary roots and returns the exact matched receipt expected by validate_matched_receipt.
- Keep fallback policy strategy candidate-code-with-captured-previous-public, read versions [1,2], same-stores-no-restore and never-replay. Private proof resides under root/work with mode 0600.

- [ ] **Step 1: Add test_fallback_uses_candidate_code_and_previous_ui, test_matched_proof_requires_actual_snapshot_and_checks, test_changed_store_or_artifact_invalidates_proof, test_packaged_rollback_process and test_verification_never_contacts_operational_endpoints_or_hardware in UpdateCompatibilityTests.** Assert final manifest hashes bind O/C/F; genuine fixture output remains fixture-only and cannot pass the production gate. After a candidate write, fallback reads the changed state without rewinding the stores or resending any physical action. The process case creates owned temporary O/C/F packages/dependency paths/evidence and invokes the existing rollback CLI with those exact paths.
- [ ] **Step 2: Run python3 -m unittest tests.test_update_compatibility tests.test_release_bundle tests.test_release_launchers -v.** Expect missing assembly/matched-verification behavior to fail.
- [ ] **Step 3: Implement artifact-only assembly and offline verification.** Record captured origins and actual assembly/test receipts rather than fake compilation evidence. Reuse owned-temp-root/loopback guards and authority assertions from the existing rollback verifier; leave its fixture-only mode intact. Test rooms v1/v2, member profile/loan compatibility, pending operation identities and disabled physical effects against privately restored actual stores. Candidate-specific failure must refuse activation and retain the original selection.
- [ ] **Step 4: Run python3 -m unittest tests.test_update_compatibility tests.test_release_bundle tests.test_release_launchers -v, including UpdateCompatibilityTests.test_packaged_rollback_process.** That case invokes deploy/verify-release-rollback.py --mode fixture-process --previous PATH --candidate PATH --fallback PATH --dependency-path PATH --fallback-evidence PATH using its verifier-owned paths. Expect passed artifact-bound checks, preserved private stores, no endpoint escape and no physical effects. Keep production-matched claims limited to checks that actually ran against the captured installed state.
- [ ] **Step 5: Commit.** Commit message: feat: verify compatible prebuilt upgrade pairs offline.

### Task 6: Activate through the existing durable release transaction

**Files:** Modify deploy/update-ccrate.py and deploy/publish-users.py; test tests/test_update_ccrate.py and existing release transaction suites. Do not replace select_bundle or recover_interrupted with a new selector.

**Interfaces:**
- apply_update(root: Path, candidate: Path, *, run_services, verify) -> dict with status completed/recovered/refused and selected_manifest_sha256.
- Consume Tasks 1/4/5 plus select_bundle(root, release, *, run_services, verify, fallback, fallback_receipt, backup_receipt_sha256) and recover_interrupted(root, *, run_services, verify).
- Verification callbacks check readiness, current release identity and native inventory/profile/loan preservation without physical output.

- [ ] **Step 1: Add test_apply_preserves_stores_without_build_commands, test_pre_exposure_failure_keeps_previous, test_post_exposure_failure_selects_compatible_fallback, test_interrupted_update_recovers_once and test_concurrent_or_changed_baseline_update_is_refused.** Inject stop, backup, selector, readiness and journal failures in temporary fixtures. Assert no automatic database restore, no replay, no unmanaged service restart and no duplicate transaction.
- [ ] **Step 2: Run python3 -m unittest tests.test_update_ccrate tests.test_update_compatibility tests.test_release_bundle tests.test_release_launchers -v.** Expect missing activation orchestration to fail.
- [ ] **Step 3: Implement activation orchestration.** One owner holds the release transaction and controls all three services. Stop writers/gateway, create the cold snapshot without independently restarting, obtain/revalidate matched O/C/F evidence and bind the backup receipt before selection. Extend the existing helper's callback/preflight seam if required for fresh proof under the same lock; do not introduce nested flock deadlocks or a second journal. Detect interrupted updates before initiating another transaction and preserve explicit service-failure diagnostics.
- [ ] **Step 4: Run all transaction tests and a disposable process-level update.** Assert that execution used prebuilt artifacts with no go, pnpm, Rust, pip or dependency-install calls. Verify the same data digests before/after and correct F recovery after candidate exposure. The real Pi --apply remains an operator-authorized acceptance step.
- [ ] **Step 5: Commit.** Commit message: feat: activate prebuilt updates with durable compatible recovery.

### Task 7: Ship the updater bootstrap and prove the user update path

**Files:** Modify .github/workflows/release.yml, deploy/build-release.py, README.md and docs/C_CRATE_RELEASE.md; extend tests/test_update_ccrate.py and tests/test_build_release.py. Include the small trusted updater/verifier/backup maintenance entrypoints as explicit public release assets with external digests; never copy arbitrary deployment source into an installed root.

**Interfaces:**
- Exact documented --check/--apply commands from Task 4, plus a one-time trusted updater download or source pull for a supported existing installation.
- The workflow publishes the archive/descriptor and required maintenance entrypoints from the same checked commit. Documentation explains native installation prerequisites, migration_required, recovery and the separate Docker test stack.

- [ ] **Step 1: Add test_documented_bootstrap_stages_supported_release and test_release_assets_have_one_commit_and_no_private_files.** Exercise bootstrap into a synthetic installed root; --check must leave services/stores untouched and --apply must succeed using injected fixture callbacks. Assert app/version metadata matches the selected archive rather than the backend's upstream version.
- [ ] **Step 2: Run python3 -m unittest tests.test_update_ccrate tests.test_build_release -v.** Expect missing bootstrap asset/command wiring to fail.
- [ ] **Step 3: Wire publication/bootstrap and write the operator guide.** Explain that no compile is needed during normal updates, account/data creation is outside this updater, and arbitrary legacy roots cannot be auto-adopted. Keep existing calibration and dependency installation outside normal updates. Include how to retain/recover the selected O/C/F transaction; do not offer a blind old-binary rollback command.
- [ ] **Step 4: Run python3 -m unittest tests.test_build_release tests.test_update_ccrate tests.test_update_compatibility tests.test_release_bundle tests.test_release_launchers tests.test_shelf_checks_backup -v and inspect the downloaded branch-built test artifact.** Require passing tests and exact descriptor/archive hashes before release publication.
- [ ] **Step 5: Obtain fresh whole-branch review and perform the operator handoff.** The user runs --check on the Pi and supplies its redacted status. Resolve unsupported runtime/selector state before requesting an explicitly authorized real --apply. Record actual timing and disk usage from that run; a local fixture is not Pi acceptance.
- [ ] **Step 6: Commit and publish the verified implementation.** Commit message: docs: deliver the prebuilt Pi update workflow. Push reviewed work to Git; attach any PR created. Do not deploy to the Pi during this task without operator authorization.

## Execution Handoff

Preserve the user's requested parallel branches/sessions. Tasks 1-2 are independent; after shared interfaces stabilize, CI/package work and updater staging can proceed independently. Activation and matched recovery have sequential gates and fresh review. Use GPT-6 Luna Low coding workers and GPT-6.1 Sol High final review.

This plan requires user review before implementation. Unknown Pi runtime/selection is an explicit rollout prerequisite, not permission to bypass validation. Mobile, a fresh installer, automatic legacy migration and unattended updates are outside this plan.
