# Live Pi project

The user removed all demonstration data on 2026-10-03. Preserve the real inventory and clean initial state.

- Do not run deploy/complete-baseline.py, deploy/probe_homebox.py or live demo-creating verify scripts against the operational Homebox instance. Use an isolated instance for mutation tests. Unit tests use temporary fixtures.
- Homebox remains the inventory authority. Use supported native APIs and preserve existing metadata.
- Never retry an uncertain create or print automatically. Use durable companion recovery.
- Private credentials, badges, backups and cleanup archives stay on the Pi. Do not log or transfer them without explicit authorization.
- The main service account is Workshop Admin; keep its private credentials and access intact.
- See docs/CLEAN_START.md for the cleanup record.

# Delegation and approval workflow

Apply this workflow to approved work in future chats. The coordinating agent
owns scope, assignments, integration, follow-ups and acceptance.

- Automatically delegate scoped coding tasks to **GPT-6 Luna**, **Low**
  reasoning (`model: gpt-6-luna`, `reasoning_effort: low`). Give each task
  a concrete objective, allowed files, safeguards and validation criteria.
- Use **GPT-6.1 Sol**, **High** reasoning for architectural planning and
  final reviews only (`model: gpt-6.1-sol`, `reasoning_effort: high`).
  Routine coordination, monitoring, coding, fixes and test triage use Luna Low.
  Prioritize speed and token economy: short handoffs, targeted tests, no
  repeated intermediate Sol reviews or unnecessary polling/full rebuilds.
  Use a scoped context fork when specifying these model overrides.
- Run **one coding worker at a time**. The coordinator must not implement
  competing changes in parallel. Finish and review the current coding task
  before starting the next one.
- Require meaningful tests appropriate to each code change and review of the
  final diff before advancing. Use Sol only for the final reviewed deliverable;
  routine intermediate checks stay with Luna.
  Send failures or review findings back to the coding worker; require fixes,
  tests and renewed review before accepting the task. Documentation-only
  changes can be validated through readback and diff review.
- Ask the user **before expanding scope, making destructive changes,
  deploying, or using paid external services**. Prepare a concrete description
  of the proposed action and its impact first. Keep approved independent work
  moving while approval is pending; do not perform the dependent action.
  Approval of a coding task does not by itself authorize deployment or paid
  external services. These model assignments authorize the requested agent
  delegation, not purchases or third-party service use.
- If a requested model, reasoning setting or delegation capability is
  unavailable, explain the limitation and ask before substituting another
  model or workflow. Do not silently fall back.

These requirements take precedence over older blanket authorization for the
four approval categories above. Preserve the live-data safeguards and Ponytail
guidance below when planning, coding, testing and reviewing.

# Project workflow: Ponytail

The user requested Ponytail for all future work on this project. Read and apply
`/home/user/.codex/skills/ponytail/SKILL.md` at the start of project work; default
mode is **full**. Reuse existing Homebox APIs, native UI components and existing
helpers before adding code or dependencies. Preserve every explicit user
requirement, inventory, permissions, accessibility and durable recovery.
Ponytail never overrides these live-project safeguards or user instructions.
See `docs/PONYTAIL_WORKFLOW.md` for installation, validation and updates.

# Requirements and workflow gaps

Before starting any task, review the user's intended workflow and ask what they
may have omitted. Trace the actual code and account/data lifecycle before
choosing the implementation. Check both interfaces, authorization, optional
fields, stable identities, existing inventory/history, interrupted operations,
and likely edge cases relevant to that task. Fill routine gaps within approved
scope with sensible defaults and explain material additions. Ask clarifying
questions when a missing decision materially affects the user's intended
result; follow the separate approval rules above for scope expansion and gated
actions. Continue independent authorized work while waiting. Preserve the
requested queue order and all live safeguards.
Do not turn this review into speculative features or a new approval checklist.
