# Compatibility and migration

Activation remains `agentic-services-orchestrator-skill`. Existing PDF rendering,
catalog CLI, package validation, services/hiring definitions and specialist
workflows remain usable. The former private Herdr repository's helper, example,
regressions and execution references are now bundled under `adapters/herdr/`; the
separate repository is unnecessary. Existing installed helper copies can still be
selected explicitly. The original local checkout and Git history are preserved.

## Existing project_state

Instructional workflows can continue using existing `project_state` without SQLite
or agents. For the executable coordinator, retain business fields and normalize:

| Legacy shape | Executable addition |
|---|---|
| Wrapped `project_state` examples | Unwrap reviewed workflow state before initialization |
| Narrative owner or `TBD` | Known workflow owner and stable `workflow_id`, revision 1 |
| `track` or `track_id` | Stable track IDs, stage, status, owner, blockers |
| `artifact` or `artifact_id` | `artifact`, exact `version`, `path`, source references, current/superseded status |
| Approval maps | Preserve evidence; add revision, category, scope, permits, provenance, approver and bound artifact versions |
| Natural-language transition conditions | Reviewed explicit `execution_rules`; required fact dot paths refer to boolean true under `known_facts` |
| Unversioned handoff | Assignment linked to workflow/track/run IDs and current workflow revision |

Approval categories are `business`, `artifact`, `merge` and `deployment`; tool
permissions/model settings stay in runtime fields. Scope comparisons are exact,
not inferred legal containment. Referenced approvals with remaining blockers fail
closed. Reconcile only affected scope while retaining unrelated track blockers and
original approval history. Existing authorization need not be requested again.

Input/approval versions must be current before dispatch/verification. Once output
is supervisor-verified, register its exact versions through coordinator update,
record applicable artifact reapproval, then consume. A changed originally referenced
approval is accepted at consumption only for the exact verified output with the
same scope/category/permits and retained history. It grants no expanded runtime
authority. Merge and deployment references may retain distinct narrow permits.

## Shared contracts and immutable assignments

[Assignments](assignment.schema.json) bind workflow/track/run/assignment IDs,
revision, owner, inputs, outputs/criteria, authorization references/provenance,
runtime configuration, endpoint, mode and stopping conditions.
[Results](result.schema.json) bind observations and evidence to exact assignment
identity/revision. Validators reject unknown structural fields, invalid timestamps,
duplicate identities and inconsistent artifact-version evidence.

Workflow/execution revisions are mutable CAS counters. Assignments are immutable
at revision 1 in this implementation; there is no in-place amendment API. Preserve
original submitted records and reconcile the owner rather than replacing scope
during recovery. Stale-result checks do not imply amendment support.

Recording a worker result does not consume it. Supervisor readback and workflow
gate validation are separate. Old helper log text or v1 configuration alone cannot
satisfy a shared result. Use `runtime.role_config.author`/`reviewer` identity strings
or objects with `identity` when independent review is required.

## Storage and packaging

Select a private SQLite file outside all enclosing Git checkouts. Preserve it
across interruptions rather than initializing replacement state. Keep original
identity/deadline, pending actions, receipts, failures and native accounting.
Conventional `.orchestration/`, `runtime-records/`, SQLite database/sidecar files are
excluded from Git and registry bundles as an extra safeguard. Runtime handoff
directories must be outside installed skill checkouts; verify private permissions.

The manifest's `operator-selected-hosts` classification covers optional runtime
tools. Local coordination/validation, preparation and rendering remain offline
after dependency installation. JSON/YAML and SQLite remain operational artifacts;
approved human-facing documents may be branded PDFs. Full checkout checks include
brand assets; text-only registry packages omit binary artwork. No migration step
launches client work or publishes packages. See [Herdr preparation](../adapters/herdr/README.md)
and [runtime adapters](runtime-adapters.md).
