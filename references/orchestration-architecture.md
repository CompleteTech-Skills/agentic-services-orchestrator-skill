# Workflow coordination and execution supervision

This repository is the integration home. It owns the services domain,
`project_state`, specialist catalog and packaging. Reusable execution contracts and
the local coordinator live here. The former private Herdr repository's preparation
helper, example and focused execution references are bundled in `adapters/herdr/`;
the remote repository is no longer a dependency.

## Three responsibilities

| Component | Authoritative facts | Implementation |
|---|---|---|
| Workflow coordination | Domain definition, stages, tracks, dependencies, artifact relationships, business status, approvals, routing and transitions | Workflow records in `scripts/orchestration.py`; domain YAML |
| Execution supervision | Assignments, operational status, runtime owner, progress, resource limits, recovery, review and completion evidence | Execution records and supervisor verification in `scripts/orchestration.py` |
| Runtime adapters | Translation to supported agent controls and observations | Native callbacks, explicit handoff, optional Herdr in `scripts/runtime_adapters.py` |

Domain adapters describe work and its gates; runtime adapters describe how it
reaches an owner. Services, hiring and software share contracts without sharing
Git or deployment requirements. Herdr selection does not change domain policy.
Specialists own their artifacts. `agentic-delivery-skill` remains the services
delivery specialist; the execution supervisor assigns and observes work.
See [services specialists](services-specialists.md).

## Implemented behavior and policy

The earlier services repository provided descriptive YAML, instructions, a PDF
renderer and catalog/package checks. The integration adds validated JSON contracts,
SQLite persistence, revision checks, dispatch intent, result ingestion, supervisor
verification, reconciliation and gated consumption. Native control is a supplied
callback. No agent-service client, daemon or plugin discovery framework is bundled.

Existing `when`, `applies_when`, `routing_rules` and lifecycle-wide `required_fields`
remain human-readable policy. Only explicit `execution_rules` permit helper-driven
stage transitions. `required_facts` are dot paths under `known_facts` whose values
must be boolean `true`; required approvals name workflow approval keys and required
checks name evidence. Dispatch rejects a proposed transition without a current rule
or missing domain-required checks/independent review. Unmapped routes remain usable
instructionally and require reviewed rule mapping before automated consumption.

## Authority and revisions

Separate workflow and execution records share one transactional SQLite store.
Stable workflow, track, run, assignment and result identifiers link them.
Workflow/execution revisions reject stale writers. Assignment scope is immutable
at revision 1; in-place assignment amendments are unsupported. Result identity,
assignment revision and observation ordering reject duplicate/stale evidence.
The workflow owner alone updates business facts, approvals and stage transitions.
The execution owner records operational evidence. Actor names identify trusted
callers; they are not authentication. The operator must authenticate approvers,
identities and evidence sources. This helper is not an authorization server.

| Authority | Owner and scope |
|---|---|
| Business/commercial | Workflow approval for the stated engagement action/scope |
| Artifact | Workflow approval bound to exact artifact versions |
| Merge/deployment | Separate workflow authority for the repository/environment and requested operation |
| Runtime permissions | Observed tool/agent configuration; never business authority |

Assignments carry approval references/revisions and authorization provenance,
never a competing approval ledger. Scope values must match exactly. Reuse valid
approval within its scope. Artifact changes invalidate only approvals bound to
affected versions. Partial/conditional approval permits only its listed actions;
remaining blockers must be reconciled for this scope. Merge and deployment approval
stay separate and may have narrowly different permits. Model or permission choices
do not replace either. Rejected, expired, superseded or out-of-scope approval blocks.

After supervisor verification, the coordinator can register exact produced versions
using `update_workflow`, obtain applicable approval, then consume. For an input
artifact revised by that result, consumption permits the exact verified output to
supersede the input. Reapproval of an originally referenced approval must preserve
scope/category/permits, bind exact produced versions, and retain original history.
It cannot authorize a runtime retry or expanded scope. Acceptance records the
current approval revisions while preserving the immutable original assignment.

## Dispatch and completion

Assignments include identifiers/revision, owner/scope, dependencies/versioned
inputs, expected outputs/acceptance, authority references, runtime roles and
capabilities, resource limits, original deadline, endpoint and stopping conditions.
Results return observations, produced versions, checks/review, external operation
IDs/receipts, blockers, pending actions and a proposed transition. The
[assignment](assignment.schema.json) and [result](result.schema.json) schemas are
the executable contracts.

| State | Evidence and meaning |
|---|---|
| `submitted` | Durable intent or submission; no established acceptance |
| `acknowledged` | Owner accepted matching assignment digest and actual effective runtime |
| `progressing` | Concrete work beyond process liveness |
| `review-pending` | Result awaits supervisor validation or required review |
| `blocked` | Precise dependency/input prevents endpoint |
| `stopped` | Intentional stop; no automatic restart |
| `failed` | Recorded failure; reconcile before recovery |
| `completed` | Supervisor verified outputs, criteria/checks, required review and endpoint |

The valid transition table is enforced in the coordinator. A worker's completed
observation becomes `review-pending`. `verify_result` requires readback bound to
that result's identity/digest, versions and endpoint; only then is execution
completed. `consume` separately checks current workflow gates and imports versions
before advancing a track. General updates cannot bypass stage transitions.
Completed work retains track ownership until consumption. No assignment or mode
implicitly closes the wider workflow.

Identify implementer and reviewer in `runtime.role_config.author` and `reviewer`,
as identity strings or objects with `identity`. Required review must be for final
produced versions and independent of author/supervisor, using the configured
reviewer where specified. Model names alone cannot establish independence.
Every required check must pass for exact outputs. Partial work and failed checks
cannot satisfy completion. PR/merge/deploy require corresponding remote readback
and operation receipts at the final revision; an earlier endpoint is insufficient.
Every resolved external effect needs a receipt, and every effect needs scoped
authority. Definitive failed attempts remain in history when later work succeeds.

`dispatch` ends after matching receiver acceptance and useful progress; writing a
handoff file alone is insufficient. `supervise` continues to the verified endpoint
or a precise external blocker, preserving pending independent work and authority.

## Recovery and concurrency

Intent commits before an adapter call. A crash between an external effect and its
receipt leaves an uncertain outcome. Reopen the existing store, reconcile saved
state with live owner/session and remote operation evidence, then reuse that owner.
Do not treat a timeout as proof of non-execution or redispatch blindly. Submission
receipts arriving after acknowledgment/stop are merged without rewinding status.
Uncertain/planned external effects block recovery/completion until definitive
readback. Pending actions persist until explicitly resolved with evidence.

Preserve run identity, original cutoff/authorization window, resource ceilings,
ownership, failure history, receipts and native session/goal accounting. Run limits
cannot be raised by later assignments; resumed work must fit current capacity.
Duplicate assignment, stale result, conflicting ownership, intentional stop,
completed work or expired authority cannot justify replacement execution. Stopping
persists intent and leaves worker-stop/no-relaunch verification pending; actual
runtime controls remain the host/operator's responsibility.

SQLite transactions and revision checks protect one local store. They provide no
distributed lock, exactly-once external execution, scheduler, automatic wakeup or
continuous supervision while the invoking agent is absent. Native session/goal
accounting stays authoritative; the helper records references rather than resetting
budgets. Models, review roles, fallback, depth and limits remain configurable.
Observe actual settings/capabilities before accepting them; unsupported settings
need a supported, authorized route or an explicit handoff.

## Filesystem, network and presentation

| Component | Filesystem behavior | Network behavior |
|---|---|---|
| Coordinator/contracts | Read selected definitions/contracts; write selected SQLite state and explicit CLI output | None after dependency installation |
| Native adapter | Pass bounded data to trusted callbacks; store evidence through supervisor | Only explicitly authorized supplied callbacks |
| Handoff adapter | Immutable assignment JSON in selected private directory | None |
| Herdr adapter | Read bundled or selected trusted helper/config; prepare private mapped bundle | Preparation offline; subsequent selected controls may access configured hosts |
| PDF renderer | Read selected Markdown/local logo; create parent directories and replace requested PDF/optional PNG paths | None |
| Catalog | Read metadata/siblings; print install plan or audit | Never clones or contacts hosts |
| Package checks | Read source/synthetic fixtures; write caches/temp QA artifacts; invoke installed tools | Dependency/tool installation may contact registries; tests simulate external effects |

State must be outside Git checkouts. Handoffs must be outside installed skill
checkouts and excluded from enclosing version control. Verify inherited Windows
ACLs; POSIX file modes do not configure them. Ignore rules exclude conventional
state/SQLite sidecar paths, not arbitrary filenames. Keep credentials, transcripts,
client facts and native databases outside public fixtures.

JSON/YAML and SQLite are operational artifacts. Branded PDFs are optional
human-facing documents with approved identity. Rendering grants no approval,
publication consent, billing/signature authority or deployment permission.
Text-only registry bundles exclude binary assets; full-checkout package checks
remain separate. See [migration](migration.md), [runtime adapters](runtime-adapters.md)
and [validation](integration-validation.md).
