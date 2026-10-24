---
name: agentic-services-orchestrator-skill
description: >-
  Coordinate services and software workflows through versioned artifacts, scoped
  approvals, bounded agent assignments, durable execution supervision, and verified
  results. Use native agent tools, explicit handoffs, or an optional Herdr adapter.
version: 1.1.0
metadata:
  openclaw:
    skillKey: agentic-services-orchestrator-skill
    homepage: https://github.com/CompleteTech-LLC/agentic-services-orchestrator-skill
    requires:
      bins:
        - python3
    install:
      - kind: uv
        package: reportlab==4.5.1
      - kind: uv
        package: pyyaml==6.0.3
      - kind: uv
        package: jsonschema==4.25.1
      - kind: uv
        package: pypdfium2==5.8.0
      - kind: uv
        package: pillow==12.2.0
---

# Agentic Services Orchestrator Skill

Coordinate what happens next, assign bounded work, and validate the result before
changing workflow state. The default domain remains CompleteTech services;
services engagements need neither coding agents nor Git repositories.

## Start with the relevant references

- [Architecture and operating rules](references/orchestration-architecture.md):
  authoritative ownership, approvals, execution states, recovery, and boundaries.
- [Services specialists](references/services-specialists.md): artifact ownership
  and original engagement workflows.
- Domain definitions: [services](references/completetech-services-workflow.yaml),
  [hiring](references/hiring-pipeline-workflow.yaml), and
  [software delivery](references/software-delivery-workflow.yaml).
- [Workflow definition shape](references/workflow-definition-schema.yaml),
  [migration](references/migration.md), and [working examples](examples/README.md).
- [Runtime adapters](references/runtime-adapters.md): native capabilities,
  explicit handoff, and the optional bundled Herdr execution path.

## Operating sequence

1. Read the user's requested endpoint and existing authorization. Inspect the
   selected workflow, current tracks, artifact versions, approvals, saved runs,
   ownership, deadlines, pending actions, and available live evidence.
2. Choose a domain adapter. Preserve existing `project_state` facts and specialist
   ownership. Distinguish the **services delivery specialist**
   (`agentic-delivery-skill`) from the **agent execution supervisor**.
3. Select the smallest useful assignment with explicit inputs, dependencies,
   acceptance criteria, owner, endpoint, limits, and stopping conditions. Pass
   approval references and provenance; never grant authority through a model,
   permission mode, or agent's success claim.
4. Prefer supported native agent tools whose actual capabilities satisfy the
   assignment. If unavailable, emit an explicit handoff and wait for evidence of
   acceptance. Use Herdr only when explicitly selected and authorized.
5. Persist assignment intent before dispatch. Reconcile an existing owner before
   retrying. Verify acceptance and concrete useful progress. Follow the selected
   mode: `dispatch` ends there; `supervise` continues to the verified endpoint or a
   precise external blocker.
6. Have execution return a validated result, including artifact versions, checks,
   independent review when required, receipts, blockers, and a proposed transition.
   Workflow coordination validates current gates and revisions before advancing.
7. Report what was verified, unresolved actions and their owner, and the next
   decision. Assignment completion never independently completes the wider workflow.

Use `TBD` for unknown narrative facts. An unknown owner, authority, required
capability, or acceptance condition cannot satisfy an executable gate. Preserve
intentional stops and original deadlines; do not create a replacement campaign or
extend an authorization window as recovery.

## Local and external behavior

The local coordinator validates contracts and writes an explicitly selected SQLite
state file. It has no network client, scheduler, or background service. Runtime
adapters use only explicitly supplied, authorized control capabilities; those tools
may access agent services, repositories, or remote sessions. Capability observations
and external evidence must identify their source. The Herdr preparation helper and
execution references are bundled under `adapters/herdr/`; no separate repository is
required. See the component boundary table in the architecture reference.

Keep JSON assignments/results and SQLite state as operational artifacts. Use
branded PDFs for appropriate human-facing overviews, proposals, and status reports
with approved identity. The existing `scripts/render_pdf.py` CLI remains available;
see [onboarding](ONBOARDING.md). A PDF is neither a required machine handoff nor
approval evidence by itself. Keep credentials and private runtime records out of
Git and registry bundles.
