# Back-and-forth, escalation and recovery

Every campaign has one current owner and a durable ledger outside Git. Track request/run/native session/goal identity, repository, actor/account, actual models and effective permissions, original cutoff, known stops, pending actions, artifact/reviewed SHAs, failures and evidence paths. Discover existing state before writing a replacement.

## Handoff receipt

A meaningful handoff contains:

- What the user authorized, exact scope and delivery endpoint.
- Correct receiver native UUID, account, server/session and observed pane.
- Concrete files/commits/issues and evidence needed to act.
- Requested next action, pending decisions and independent work that can continue.
- Contract/delta ID, source and received byte digests, submission time, later acknowledgment of that specific assignment and useful-progress evidence.

Update an existing ledger rather than replacing earlier failures with a success-only story. Responses should identify which request/action they settle. An accepted tool write, visible message, started turn and completed action are different stages.

Preserve immutable submitted prompts and give follow-ups distinct delta IDs linked to the same owner/run. While the receiver is compacting or busy, record a follow-up as queued until its specific acknowledgment or unmistakable action is observed. Do not treat unrelated activity as consumption or repeat an uncertain submission.

## Missing facts, access or authority

Finish independent work and prepare concrete artifacts before requesting a missing decision. Reuse already supplied answers and authorization. Record the exact source of a genuine owner-only requirement; do not invent approval gates from a skill's general caution. A failed `gh` operation needs diagnosis of the actual account/repository/permission, while a missing SSH route needs deployment-client access. Neither implies that raw credentials must be copied.

Queue a structured escalation with stable request ID, blocker class, source/target identity, relevant repository/goal, attempted command category, sanitized evidence, precise requested fact/action and expiry/cutoff. Keep credential values out. Preserve user questions in the native UI rather than blindly submitting a generic continuation.

Without a proven automatic channel, save the handoff in the existing private run directory and report the exact path to the user/owner. In supervised mode check it at bounded intervals while doing independent work. Do not claim a file notification or `codex queue` wakes the original Windows/ChatGPT conversation. A `verified-channel` configuration must point to evidence for that exact endpoint and current capability.

When supervision includes deployment through another machine, the outer owner follows the existing authorized execution route instead of stopping at a prepared bundle. Return the executor's receipt archive through that route, compare its digest and read back the files at the original owner's destination. Track return-transfer success separately from owner acknowledgment; a queued receipt follow-up is still pending consumption. Keep the pinned release distinct from any newer feature campaign sharing the repository.

## Recovery versus intentional stop

An unexpected stop within an active authorized window can be diagnosed and safely resumed with the same identity after reconciliation. A user stop, completed run, expired cutoff, response with stale authority or uncertain prior side effect is not restart permission. Preserve pending actions, receipts, ownership and failure history. Reconcile uncertain execution before retrying it.

For a permission-only relaunch, record the temporary interruption reason and resume the same native goal; avoid converting it into a new goal or resetting usage. For a requested stop, disable the scoped resumer first and verify delayed no-relaunch. Never shut down or terminate the shared WSL VM; inspect process/service/storage state and repair only the authorized component.

## Honest status

Use `prepared`, `submitted`, `accepted`, `progress-observed`, `blocked`, `stopped`, and `completed` only with matching evidence. A finished worker may have completed a bounded assignment while the campaign remains incomplete. Distinguish a software fix from a temporary mitigation, and a passing test suite from a fully satisfied delivery gate.
