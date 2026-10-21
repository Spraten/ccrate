# Printer recovery review

Verdict: changes requested. Adapter resolution, missing-software classification, and the read-only reconnect flow address the demonstrated root cause. The recovery script cannot currently complete with the Pi's standard package candidates.

## Important findings

1. **P1 — Standard package instructions install a compiler too old for the pinned source.** `deploy/restore-printer-adapter.sh:12–17` only checks command availability and recommends `apt install cargo rustc ...`; line 42 builds source pinned to `9fd7af09580c3e710202e5471e77e0b88db0e3bb`. On this Pi, `apt-cache policy` reports Rust/Cargo 1.85.1 candidates. The pinned `crates/supvan-proto/src/printer.rs:256` and `:496` use let chains, which require Rust 1.88 ([official Rust release announcement](https://blog.rust-lang.org/2025/06/26/Rust-1.88.0/)). Installing the suggested packages therefore still leaves recovery blocked. Check the actual minimum compiler version and provide a compatible package-managed path, or explicitly explain the blocker before agreeing any alternative with the user. Do not silently substitute a downloaded toolchain.

2. **P2 — The script rejects its own added example on rerun.** `deploy/restore-printer-adapter.sh:25–28` accepts only `?? crates/supvan-proto/examples/kiosk-label.rs`, but the pinned source has no tracked examples directory. After lines 38–40 create it, ordinary `git status --porcelain` reports the untracked directory as `?? crates/supvan-proto/examples/`. A failed first build (including the compiler failure above) makes the next restore attempt refuse the checkout as dirty. Use `git status --porcelain --untracked-files=all` so the existing exact-file/content guard can work.

## Confirmed scope and limits

- Resolution precedence is explicit adapter, code root, then legacy data/code root; all existing print call sites use the shared resolver.
- Reconnect calls `probe`, whose adapter command is `probe`; the Rust adapter returns before the print branch. The changes add no print retry.
- Missing/nonexecutable adapter detection precedes USB enumeration, and the new status supplies software restore guidance without recommending USB changes for this failure.
- Atomic output replacement preserves an existing adapter when compilation fails.
- The reported six focused tests were not rerun in this review. No compiler build, deployment, service restart, hardware probe, or physical print was performed; printer readiness remains unverified.

Only this review artifact was written.

## Re-review

Verdict: approved for the diagnostic fix and recovery tooling. Both findings above are addressed in the latest script: it rejects Rust older than 1.88 before repository/build changes, gives an official Debian Trixie backports installation path, and uses `--untracked-files=all` so its own copied example is accepted on rerun. Debian publishes a sufficiently recent package-managed compiler in [Trixie backports](https://packages.debian.org/trixie-backports/rustc). Retaining the separate build cache avoids unnecessary full rebuilds.

Inspected the two added shell preflight tests and the corrected report explaining that the physical adapter was absent under both roots. Root reports all 23 label, hardware, and restore-script tests passing; this review did not rerun them. Root also reports the backend diagnostic change applied via a service restart and localhost:17745 ready. The report's earlier sentence saying no service restart/deployment occurred should be updated to reflect that later action.

No new blocking code findings. The toolchain is still uninstalled, the adapter has not been built, and hardware readiness remains unverified; approval of these changes does not establish printer reconnection.
