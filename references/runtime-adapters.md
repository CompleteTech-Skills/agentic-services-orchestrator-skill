# Runtime adapters

Domain adapters define stages, specialist artifacts and gates. Runtime adapters
deliver already authorized bounded assignments and observe execution. They cannot
advance business stages or create approvals. The services delivery specialist owns
services artifacts; the execution supervisor owns agent assignments.

The API has `submit(assignment)`, `observe(assignment)` and
`recover(assignment, evidence)`. Call through the existing coordinator, which
persists dispatch intent before effects and reconciles uncertainty before retry.
Calling a native callback directly provides no duplicate-dispatch protection.

| Adapter | Implemented behavior | Filesystem/network behavior |
|---|---|---|
| `HandoffAdapter(private_directory)` | Immutable assignment JSON/digest; repeat identical revision reuses it, changed content fails | Selected private directory; no network, Git, agent or Herdr dependency |
| `NativeAdapter(capabilities=..., submit=..., observe=..., recover=...)` | Explicit trusted host callbacks; capability/config checks; recovery reuses owner | No bundled network client; callbacks may access authorized agent tools/hosts/files |
| `HerdrAdapter(config=..., private_directory=..., helper_path=None)` | Bundled helper validation/render/verify and shared mapping; prepared status only | Local trusted Python helper via argument array with `shell=False`; no live agent/network launch |

There is no runtime discovery framework, daemon or wake scheduler. Prefer supported
native tools; otherwise use an explicit handoff. Missing capability is not authority
to bypass a tool denial.

## Native observations

Native submit returns `status: submitted`, `operation_id`, `receipt` and actual
`effective_runtime`. It establishes submission only. Observe returns matching
workflow/track/run/assignment IDs and revision, distinguishable status and:

```json
{
  "capabilities": ["bounded_assignment", "observation"],
  "role_config": {"author": "implementer", "reviewer": "independent-reviewer", "worker": {"model": "actually-observed-model"}},
  "limits": {"max_concurrency": 1, "max_delegation_depth": 0},
  "owner": "existing-owner",
  "native_session_id": "existing-session",
  "native_goal_id": "existing-goal",
  "evidence": "Native status observation or operator receipt reference"
}
```

`validate_observation` requires every requested capability, recursively matching
requested role settings, observed resource limits no higher than requested, the same
owner, and pinned native session/goal preservation. Unpinned IDs may be discovered.
Requested settings include roles/models, effort/tier, permissions and fallback.
They confer no business authority. A trusted host must obtain actual observations;
the helper validates shape/consistency rather than authenticating evidence. Do not
copy launch arguments into observed settings without proof. Missing enforcement
requires a recorded capability gap and a supported authorized route.

A live process establishes liveness. Matching assignment acceptance and concrete
work establish useful progress. The supervisor separately verifies checks, final
artifact versions, required independent review and the requested endpoint.

For recovery, supply matching identity/revision, `reconciled: true`,
`uncertain_operations: []`, `intentional_stop: false`,
`existing_owner_recoverable: true` and effective runtime evidence. The native
adapter rejects stopped/completed observations, expired cutoffs/authorization and
owner/session replacement. Its recovery callback must return
`action: reused-existing-owner`, unchanged native IDs and a receipt. It never
falls back to submit. Handoff/Herdr preparation recovery returns a manual blocker.
The state store preserves pending actions, receipts, failures and native accounting.

## Handoff and bundled Herdr preparation

A handoff's submitted receipt means a local file is available. It is not acceptance
or progress. The owner must consume the identified assignment and return evidence.
JSON is operational; an optional human-facing PDF does not replace it.

The optional Herdr helper, synthetic config and focused session/delivery/recovery
references are [bundled here](../adapters/herdr/README.md). The private source
repository is no longer needed. The v1 CLI remains available at
`adapters/herdr/scripts/prepare_run.py`. Default construction is:

```python
adapter = HerdrAdapter(config=config, private_directory=private_directory)
```

The previous three-positional-argument constructor remains supported for an
explicit trusted helper override. Config must match assignment scope, mode and
software endpoint. Preparation preserves the original cutoff and writes:

- `assignment.json`: full shared contract and authority references.
- `legacy-config.json`, `legacy-run/`: legacy config, prompt and prepared receipts.
- `workflow-link.json`: stable IDs/revision, assignment digest, approval references,
  legacy contract/prompt digest and selected helper digest.

The bridge maps `role_config.models`, per-role model/effort/tier, top-level
effort/tier/fallback conditions and named permissions, rejecting conflicting legacy
settings. Legacy concurrency cannot exceed the assignment limit. Shared depth
counts delegation edges; legacy levels include the outer owner. Shared depth 1
therefore permits legacy level 2. Zero-depth tasks use local/native/handoff routes.
Unrepresentable differing per-role effort/tier settings fail. Native session/goal
IDs and cutoff cannot be replaced. Other role annotations/limits travel in the full
assignment and require observed enforcement before live acceptance.

The generated prompt instructs the receiver to read the full assignment, reconcile
legacy discrepancies and return evidence to workflow coordination. Legacy authority
strings refer to existing authorization, not a competing approval ledger. Prepared
or digest-verified artifacts never establish live acceptance or success. Legacy
accepted maps to acknowledged; progress-observed maps to progressing only with
matching concrete work. Current endpoint evidence is still required.

An old legacy run is not automatically linked or rewritten. Reconcile its native
identity, original deadline, owner, pending actions, receipts, uncertain operations,
failures and intentional stops before introducing reviewed shared state. Preserve
old artifacts/accounting; do not create a duplicate coordinator.

## Private storage and validation limits

Choose private handoff paths outside either installed skill checkout and exclude
them from enclosing VCS workspaces. Helpers use exclusive files and request
restrictive POSIX modes. On Windows verify inherited directory ACLs separately.
Keep credentials out of contracts; reference existing authenticated routes.

Interrupted preparation can leave an incomplete directory. Preserve it for
reconciliation; deletion is not evidence that no action occurred. Digests detect
drift, not authority/authenticity. There is no exactly-once execution guarantee.
Tests simulate native effects and exercise real local bundled helper preparation;
they do not establish live Herdr/provider/GitHub/client outcomes. See
[architecture](orchestration-architecture.md) and [validation](integration-validation.md).
