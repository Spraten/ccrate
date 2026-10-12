# Matched Release Selection and Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select and roll back a complete matched application release while preserving private operational data.

**Architecture:** Package immutable binary/static/Python code artifacts under one release directory and select them through one atomic application symlink. Service launchers resolve that release once per process; code imports use the release and runtime data/tools retain their existing private roots. Verify selection and rollback with fixture directories, fake service commands and disposable native databases before proposing any operational rollout.

**Tech Stack:** Python pathlib/hashlib/os/shutil/unittest, existing systemd user unit definitions, existing Go/Nuxt build artifacts and disposable integration harness.

**Spec:** `docs/superpowers/specs/2026-10-06-user-management-review-fixes.md`

## Global Constraints

- Homebox is the account and inventory authority; use existing native UUIDs, APIs, components and helpers.
- Name-only profiles remain badge-only with NULL native passwords; existing desktop accounts keep their sign-in behavior.
- No password/PIN enforcement, role changes, dependencies, speculative authentication or unrelated refactors.
- Never automatically repeat an uncertain create, save, badge issuance, replacement or print.
- Never mutate live data, issue/print real badges, read secrets/backups, or restart services during implementation verification.
- Private credentials, badge keys, databases and backups stay outside release bundles and logs.
- Preserve the dirty working tree and existing uncommitted features; never reset, stash, delete or replace them with a clean HEAD checkout.
- One GPT-6 Luna Medium coding worker per task; GPT-6.1 Sol High risk review; fixes, tests and renewed review before the next task. No silent model/workflow fallback.
- Planning approval is not deployment approval; physical print/disconnect acceptance is a separately authorized gate.

## Review Focus

- Legacy binary without matching Python source → Task 1 `test_legacy_target_without_matching_source_fails_before_selection`.
- Source edits after packaging or split static selectors → Task 2 `test_launchers_resolve_one_release_and_ignore_working_source`.
- New native user/settings data read by older rollback build → Task 3 `matched_previous_release_preserves_new_fixture_profiles_and_loans`.
- Failure after pointer change or during restart → Task 3 `test_selection_failure_restores_entire_previous_bundle` and `test_failed_rollback_is_reported_without_data_restore`.
- Credential/database/adapter paths confused with release code → Tasks 1/2 `test_bundle_excludes_private_data` and `test_runtime_roots_survive_release_selection`.

---

This plan prepares deployable changes; it does not authorize invoking the publisher or changing systemd units/selectors. Commands below use isolated source and temporary fixtures only. Preserve historical receipts; acceptance must use named checks and hashes for actual artifacts rather than reusing the publisher's fixed `221/7/42` counts.

### Prerequisite: Preserve a proven baseline before any feature edits

- [ ] Coordinator creates an isolated workspace using the worktree skill and the approved current dirty/untracked source allowlist; include these features rather than clean HEAD. Record the initial status/diff and source/build hashes privately on this machine. Do not copy `work/ops`, browser profiles, credentials, keys, operational databases, archives or backups into the workspace. Required toolchains/dependencies may be referenced at their existing paths without copying private runtime data.
- [ ] Before profile/parity implementation, preserve nonprivate current `caci.2` binary/static/code artifacts and their existing matching build/test provenance as the baseline input. Retain all imported Python source in `ops/` and `kiosk/`, `deploy/kiosk-server.py`, `deploy/workshop-gateway.py`, `deploy/run-homebox.py`, public assets and launch definitions. If hashes/provenance cannot establish a match, report the gap and prohibit later selection. Do not substitute the current companion for the old `caci.1` binary or read a private backup to reconstruct it. No live snapshot/testing is required or authorized here.
- [ ] Store the baseline artifact paths/hashes outside task commits. Task 1 subsequently packages this preserved input; it must not package already-modified feature code as the old baseline.

### Task 1: Package and validate a complete code bundle

**Files:** Create `deploy/release_bundle.py`, `tests/test_release_bundle.py`; modify `work/publish-users.py` only to guard existing operational entry point (`main() -> None`, `if __name__ == '__main__': main()`). Later tasks replace its selection body. Do not import the current unguarded publisher in tests.

**Interfaces:** New `stage_bundle(destination: pathlib.Path, *, binary: pathlib.Path, public: pathlib.Path, source: pathlib.Path, provenance: dict) -> dict`; `validate_bundle(release: pathlib.Path) -> dict`. Bundle layout: `native/homebox`, `public/`, `kiosk/` (static **and Python** files), `ops/` (all Python source), `deploy/{kiosk-server.py,workshop-gateway.py,run-homebox.py}`, service definitions, and `manifest.json`. Manifest stores relative-file SHA256 hashes and validated build/test compatibility provenance; no secret values. Only allowlisted code/assets are copied. Reject links escaping the supplied code roots, caches, missing artifacts and mismatched receipts. Do not include `work/` runtime subtrees. After Task 2, also package the release launcher needed by new bundles.

- [ ] Write fixture tests using tiny synthetic old/new artifact files: `test_bundle_includes_imported_python_and_all_frontends`, `test_bundle_hash_mismatch_is_rejected`, `test_bundle_excludes_private_data`, `test_legacy_target_without_matching_source_fails_before_selection`. Populate fake source with sentinels named `work/ops/ledger.db`, `badge-print.key`, `work/baseline/test-account.json`, `pepper`, browser profile and backup; assert none is read/copied/logged. Fixture old `caci.1` with no code/provenance is rejected; a preserved matched `caci.2` bundle is accepted.

```python
assert set(manifest['files']) >= {'native/homebox', 'public/index.html',
    'kiosk/index.html', 'kiosk/scan_codes.py', 'ops/desktop_api.py',
    'deploy/kiosk-server.py', 'deploy/workshop-gateway.py'}
assert not any(path.startswith('work/') for path in manifest['files'])
assert fixture_private_sentinel not in json.dumps(manifest)
# Changing any code/binary/static byte after staging must make validation raise.
```

- [ ] Run `PYTHONPATH=deploy:ops:kiosk python3 -m unittest discover -s tests -p test_release_bundle.py -v`. Expected RED: missing bundler and current publisher has no matched Python release contract. Do not execute `work/publish-users.py`.
- [ ] Implement stdlib-only allowlisted copy/hashing and validation. Guard publisher operational actions against import. Validate capabilities using artifact-matched fixture results, not the version label alone; a missing/mismatched baseline fails before service operations or selection.
- [ ] Rerun the command. Expected GREEN: unittest OK; spies confirm zero `systemctl`, live file reads, native HTTP calls or private-data copying. Package the preserved baseline only through this validated code and retain it as the future previous-release input, without selecting it.
- [ ] Sol High reviews package closure, baseline provenance and private exclusions; fix/test/re-review, then commit only task-owned code/tests (do not commit staged artifacts or earlier feature work).

### Task 2: Launch every process from the same resolved release

**Files:** Create `deploy/run-release.py`, `tests/test_release_launchers.py`; modify `deploy/kiosk-server.py`, `deploy/run-homebox.py`, `deploy/workshop-gateway.py`, `deploy/homebox-native.service`, `deploy/homebox-companion.service`, `deploy/homebox-workshop-gateway.service`; update `deploy/release_bundle.py`. Inspect `ops/labels.py` adapter path; no change if runtime ROOT remains correct.

**Interfaces:** New `release_command(root: pathlib.Path, component: str, *, release: pathlib.Path | None = None) -> tuple[list[str], dict[str,str]]` accepts only `native|companion|gateway`, validates the supplied resolved release (or resolves `root/work/application-current` once for fixture calls), returns the packaged entry script plus environment `WORKSHOP_ROOT=<runtime root>`, `WORKSHOP_CODE_ROOT=<resolved release>`, `HOMEBOX_UI_ROOT=<resolved release/public>`. Launcher `main() -> None` resolves its own physical bundled directory once and passes it explicitly; it never selects another release mid-startup. Native `run-homebox.py` uses runtime `work/baseline` but packaged `native/homebox`; companion uses code-root `ops`/`kiosk` imports and assets while `ROOT` remains runtime root; gateway uses resolved `HOMEBOX_UI_ROOT` and packaged routing code. Runtime `work/hardware/python` and `work/supvan-cups` remain external private tool paths. Units' ExecStart is `/usr/bin/python3 /home/user/Desktop/inventory-system/work/application-current/deploy/run-release.py <component>`: the launcher and its `release_bundle.py` dependency are bundled and hashed too. Editing working `deploy/run-release.py` cannot change a selected release. Installation/restart is separately gated.

- [ ] Write `test_launchers_resolve_one_release_and_ignore_working_source`, `test_runtime_roots_survive_release_selection`, `test_invalid_component_or_bundle_never_launches`. Resolve old release, change selection to new, assert already-resolved commands/env stay old, newly started processes all resolve new. Alter working `ops`, server, gateway, launcher, bundle helper and kiosk assets and prove packaged responses/import origins remain selected; assert ExecStart uses the bundled launcher. Assert ledger/key/baseline/adapter paths still resolve beneath runtime root and cannot resolve into release directories. No launcher test executes production service binaries or reads credentials.

```python
command, env = release_command(fixture_root, 'companion')
assert env['WORKSHOP_CODE_ROOT'] == str(old_release.resolve())
assert env['WORKSHOP_ROOT'] == str(fixture_root)
assert command[-1] == str(old_release / 'deploy/kiosk-server.py')
# Follow selection with new launches: native, companion and gateway code/static
# paths all share the exact resolved new release, while runtime root is unchanged.
```

- [ ] Run `PYTHONPATH=deploy:ops:kiosk python3 -m unittest discover -s tests -p test_release_launchers.py -v`. Expected RED: companion imports mutable source and native/static use independent selectors.
- [ ] Implement the specified launcher and code/data separation. Keep gateway proxy behavior and native auth/collection forwarding unchanged. Package all code dependencies. Build the rollback baseline from preserved **caci.2** source/binary/static inputs with only this task's reviewed path/bootstrap adaptations; record the adaptation diff and resulting hashes. Before labeling it launch-ready, require shared disposable integrity, retained-functionality and data-compatibility checks; this previous baseline intentionally lacks the planned fixes, including the October 7 profile-completion revision, and need not pass their new acceptance assertions. The candidate must pass both shared compatibility checks and every new feature acceptance check. The unadapted fixed-ROOT snapshot is not launch-ready. Never import new profile/parity behavior into the previous baseline. Legacy launch behavior may remain for the existing installation until separately approved conversion, but validated selection must never silently fall back to mutable source. Do not install units or change live links.
- [ ] Rerun launcher/bundle tests plus `PYTHONPATH=ops:kiosk python3 -m unittest discover -s tests -p test_workshop_gateway.py -v`. Expected GREEN: all tests OK and unchanged gateway authorization tests pass. Adapt the disposable integration loader to new environment/code-root contract in Task 3; preserve isolation, not operational ROOT substitution assumptions.
- [ ] Sol High reviews import resolution, one-time selection, static roots, complete service set and private adapter/database roots. Fix/test/re-review before task-only commit.

### Task 3: Atomic selection, rollback and old/new compatibility fixtures

**Files:** Modify `deploy/release_bundle.py`, `work/publish-users.py`, `tests/test_release_bundle.py`, `deploy/verify-desktop-integration.py`; create `deploy/verify-release-rollback.py`. Do not modify or run backup/operational verification scripts.

**Interfaces:** New `select_bundle(root: pathlib.Path, release: pathlib.Path, *, run_services: Callable[[list[str]], None], verify: Callable[[pathlib.Path], None]) -> None`. Preflight validates new **and previous** matched bundle, then stops gateway/companion/native, atomically replaces one `application-current` symlink, starts native/companion/gateway and verifies the selected package. On failure stop all, restore previous pointer, restart the same service set and verify previous. If rollback itself fails, surface both failures and preserve recorded selection state; never announce healthy rollback or restore old databases. Public/UI compatibility aliases, if needed, point through `application-current/public` and `/kiosk`; they are installed only in approved conversion, not switched independently per release.

- [ ] Add `test_selection_failure_restores_entire_previous_bundle`, `test_failed_rollback_is_reported_without_data_restore`, `test_missing_previous_bundle_never_stops_services`, and `test_selection_keeps_private_files_byte_identical` with fake service callbacks. Inject failure before selection, after pointer replacement, during start and verification. Assert one matched pointer, exact three-service ordering, old Python imports/static/binary restored, explicit rollback failure, private fake-file bytes unchanged and no database restore/copy. Fix hardcoded publisher check counts by validating current artifact hashes and named required checks in matching fixture receipts; stale receipts must fail preflight.
- [ ] Run `PYTHONPATH=deploy:ops:kiosk python3 -m unittest discover -s tests -p test_release_bundle.py -v`. Expected RED: current publisher restores only binary/UI and leaves mutable companion source; missing-target/rollback-failure semantics absent.
- [ ] Implement the selection helper and wire guarded publisher to it. Publisher stages/verifies the full bundle; preserves inventory/backup safeguards as operational actions behind its explicit entry point, never fixture imports. All real stop/start, baseline verification or private backup activity remains awaiting separate deployment approval. Do not automatically restore inventory databases on code rollback.
- [ ] Create `verify-release-rollback.py` CLI `--previous <matched-bundle> --candidate <matched-bundle>` requiring both bundle manifests, rejecting operational runtime paths and creating only a new temporary database/runtime root. Start packaged native/companion/gateway on disposable ports; substitute fake printer/hardware boundaries before any request. Seed synthetic admin, name-only member, profile/avatar/private-note fixture, badge and current loan; exercise candidate, induce verification failure, restart previous against **the same fixture data**. Named assertion `matched_previous_release_preserves_new_fixture_profiles_and_loans` checks user UUID, NULL password, original web login, saved avatar/notes, badge resolve, loan/date/history and collection privacy after rollback. Named assertion `legacy_missing_member_api_is_not_a_rollback_target` rejects a deliberately incomplete legacy package before launching. Never claim `caci.1` supports new member endpoints.
- [ ] Run both unit files and `python3 deploy/verify-release-rollback.py --previous "$PREVIOUS_MATCHED_FIXTURE_BUNDLE" --candidate "$CANDIDATE_MATCHED_FIXTURE_BUNDLE"` after explicitly setting these variables to the validated nonprivate staged bundle paths. Then `HOMEBOX_VERIFY_NATIVE_BINARY="$PWD/work/homebox-backend-build/homebox" python3 deploy/verify-desktop-integration.py`. Expected GREEN: named compatibility/rollback checks, `live_mutations:0`, `physical_prints:0`, all existing profile/parity/auth/collection assertions pass. Receipts hash the previous/candidate binary **and Python/static manifest**, record fake-service/fixture-only execution, and contain no private data. No live rollback occurs.
- [ ] Sol High reviews final combined diff and all failure-injection receipts. Luna fixes/test/re-review until accepted. Commit only accepted task changes. Coordinator presents the exact candidate/baseline hashes, proposed launcher/unit conversion, data-preservation evidence, legacy limitation and service impact for **separate deployment approval**; no deployment action is taken by this plan's completion.
