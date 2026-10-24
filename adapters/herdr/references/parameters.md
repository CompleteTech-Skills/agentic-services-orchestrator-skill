# Parameters

The helper accepts JSON with `version: 1`. Unknown fields are rejected to catch misspelled controls. Natural-language invocations can be resolved into this contract; copying a preset never grants authority.

| Field | Meaning/default |
|---|---|
| `repository` | Required `owner/name` or GitHub HTTPS URL; verify the actual remote live. |
| `scope` | Required concrete task and limits. |
| `operation` | `bootstrap`, `implement` (default), `sync-merge`, `recover`, `stop`, `deploy`. |
| `delivery` | `triage`, `implementation` (default), `pr`, `merge`, `deploy`. |
| `control` | `dispatch` (default) or `supervise`; infer from the user's request. |
| `base_branch` | Optional; discover the remote default when absent. |
| `target` | Optional routing fields below; unresolved identity means discover before input. |
| `models` | Coordinator, worker, capacity fallback, reviewer, effort/tier, depth and workers. |
| `permission` | `inherit` (default), `workspace`, `yolo`. Do not reduce a live authorized mode without reason. |
| `authority` | Evidence strings for allowed actions; omitted entries mean no recorded authorization. |
| `acceptance` | List of task-specific checks. Default empty; discover repository requirements. |
| `limits` | CPU/disk/PID/concurrency/time constraints below. |
| `escalation` | Owner, route and handoff directory; default route `manual-handoff`. |

`target`: optional `ssh_host`, `container`, `herdr_session` (default `default`), `pane`, `native_session_uuid`, `account`, `cwd`, `goal_id`. Use the native UUID and account as identity; the pane is a routing hint. A pane without a UUID is rejected. A known UUID with an unknown current pane is valid for discovery/recovery; locate its current live occupant or reconcile its absence before any input or relaunch. Omit both when neither is known. No passwords, private keys or tokens are accepted.

`target.account` is the receiver/coordinator account. Worker account launchers, including `claude2` where available, belong in their bounded assignments and worker receipts; do not change the coordinator account just to select a worker launcher. A launcher is separate from `models.worker` and `models.tier`. See [account launchers](session-control.md#account-launchers) for discovery and verification.

`models` defaults:

```json
{
  "coordinator": "gpt-6.1-sol",
  "worker": "claude-sonnet-5-5",
  "fallback_worker": "gpt-6.1-sol",
  "fallback_when": "capacity",
  "reviewer": "gpt-6-astra",
  "effort": "high",
  "tier": "default",
  "levels": 3,
  "max_workers": 2
}
```

`models.tier` defaults to `default`: normal inference without `/fast` or equivalent fast settings. This is a workflow value, not a literal provider CLI argument. Set `tier: fast` only from an explicit user request. **Luna agents always require fast**, whether coordinator, worker, fallback or reviewer, even when the shared tier is `default`. The helper reports `requested_tiers` per role and embeds that map in its prompt. It recognizes `luna` as a delimited model-name component, including provider-prefixed names; confirm the actual model behind any opaque alias before launch.

Apply the tier to the actual selected model whenever it changes, including fallback: Luna to Sol returns to normal unless fast was explicitly requested; Sol to Luna requires fast. A previously rendered template with `tier: fast` does not prove a user requested it. Preserve old receipts and reconcile a continuation's tier with current user instructions. Verify actual session state rather than assuming that omitting a launch flag clears an inherited fast setting.

Change exact model IDs for future campaigns when the user selects them. `fallback_when` is `capacity` or `never`; `never` forbids fallback. Verify current runtime availability independently. A disabled fast tier is not a model-capacity failure. Luna fast is mandatory; if unavailable, report the blocker for that agent. For other models, an explicitly requested fast preference can fall back to the same model's available tier with disclosure; a mandatory tier remains a blocker. Never enable billing or silently change models.

`levels` counts the outer conversation: Level 1 outer owner, Level 2 receiving Herdr coordinator, Level 3 directly assigned workers and independent reviewer. Level 3 cannot spawn. With `levels: 2`, the outer owner assigns bounded author and reviewer peers at Level 2; neither may delegate. Applicable instructions may require exactly three levels. A reviewer must be independent of the author even if user-selected model names match. Do not reset depth at a handoff or create a fourth level.

`authority` has optional evidence strings `implementation`, `publish`, `merge`, `deploy`, `yolo`, `create_repository`, `stop`, `resume`. Quote or reference current user instructions and previously established scope; the helper cannot verify provenance. For a PR endpoint, implementation and publication must be recorded; merge adds merge authority. Code operations (`implement`, `sync-merge`, `bootstrap`) through deployment require implementation, publication, merge and deployment evidence. Use `operation: deploy` for an existing reviewed artifact; it needs deployment authority without requiring new code/publication. Recovery needs resume authority and reconciliation with the existing owner's authority ledger; stop needs stop authority. Bootstrap needs repository-creation authority. `yolo` always needs its own evidence. These are checks on this contract, not a new approval ceremony: the same existing user instruction can authorize multiple stages.

For `implement` or `sync-merge` with a `triage` endpoint, the helper generates read-only assessment instructions without code or remote mutations. Authorized bootstrap triage can create the repository and issue plan. When the user later requests implementation, resolve a new contract/delta from that instruction instead of retaining the old planning-only endpoint.

`limits`: optional `disk_reserve_gib` (default 8), `pid_admission_fraction` (default 0.6), `max_heavy_jobs` (default 1), `original_cutoff_utc` (default null), `checkpoint_seconds` (default 120). Recheck actual machine limits; values are budgets, not permission to change host quotas. Preserve an existing original cutoff. An expired cutoff is printed explicitly as expired and cannot authorize a restart; an explicitly authorized scoped stop and no-relaunch verification can still execute. Expired recovery/code campaigns remain limited to preparing blocked/stop evidence.

`escalation`: `owner` (optional), `route` (`manual-handoff`, `verified-channel`, or `none`), `handoff_dir` (optional), `capability_evidence` (required only for `verified-channel`). A successful CLI queue probe does not prove the original desktop conversation can be awakened. Escalation content includes request ID, original run/session, repository, blocker, attempted action, evidence, exact needed fact/decision and independent work that can continue.

Example invocation in conversation:

```text
Use $orchestrate-herdr-delivery for CompleteDotTech/codex.
operation=sync-merge, delivery=merge, control=dispatch.
Reuse the existing coordinator; use --yolo for this campaign.
Sol 6.1 coordinator, Sonnet 5.5 workers with Sol 6.1 capacity fallback,
and independent Astra review. Preserve the current PR stack and safety gates.
```

The helper's `receipt.json` is an empty evidence checklist with state `prepared`; no field in it proves a live action. Record actual native identities, goal, effective policy, delivery acknowledgments and evidence after inspecting the real run. Keep updates and failed attempts in the owner's existing durable ledger.

`verify --run <directory>` checks strict UTF-8 decoding, canonical configuration digest, exact prompt bytes and contract identity against the receipt. Add `--expected-prompt-sha256 <source-digest>` to compare against a digest recorded independently before transfer. Verification is read-only and does not regenerate the prompt using potentially changed skill references. A successful result reports `runtime_verified: false`; it does not validate authority provenance or prove the receiver consumed the assignment.
