# Delivery modes

## New repository and triage

When creation is authorized, determine owner/name/visibility from current context; private is a reasonable stated default if visibility is unspecified. Verify absence and account access before creation. Preserve any same-named local folder. Seed concise scope, architecture assumptions, orchestration instructions and an issue map, with no secrets or copied operational transcripts.

Create implementable issues with observed problem, bounded scope, priority, estimated size/risk, acceptance evidence, failure tests and dependencies. Keep optional hardening distinct from release requirements. Verify the graph is acyclic. Publish native dependency links where supported and read them back. Record exact issue URLs and IDs; never assume numbering when another writer could create an issue concurrently. List APIs can lag newly created issues; confirm missing entries directly by the recorded issue number rather than creating duplicates.

Honor signing configuration, but verify the result on GitHub. On Windows a configured signing helper may invoke WSL against a Windows private key and fail permissions; select the existing authorized native signing route for the new checkout instead of weakening file permissions or disabling signing. Do not change machine-wide signing defaults.

Dispatch after repository content and issue links are concrete. A coordinator should implement through the authorized endpoint, not merely repeat the inventory. Broad production enrollment remains separate unless expressly included in the user mandate.

## Existing issues and stacked PRs

Discover the repository's actual default branch and remote. For a fork, distinguish syncing PRs with the fork's base branch from adopting upstream changes. Inventory all live PR heads/bases, draft state, owner comments, unmerged and unpublished candidates, checks and applicable policies. A stale `MERGEABLE` flag is not evidence that an unsafe candidate is ready.

Build the dependency graph from actual refs. Reconcile existing owners before writes. Use isolated worktrees; record old refs and remote heads. Work bottom-up, preserving PR identities and branch history. Coordinate any necessary rewrite with branch ownership and use exact force-with-lease checks; never use a blanket force push. Update descendant bases after prerequisite merges and verify no duplicate or dropped commits.

Explain meaningful conflict decisions. Fix causal defects noted by owners/reviewers before merging prerequisites. Review actual changed code at the final SHA, run required and relevant tests, then publish signed updates. Separate real PostgreSQL/device/OS coverage from simulations or skipped fixtures. Do not trigger broad hosted matrices if the user deferred them; finish independent preparation and identify the exact remaining gate. Do not change billing, protection or repository visibility to make checks pass.

If hosted Actions are disabled or unavailable, record the observed reason and distinguish absent checks from passing checks. Do not re-enable workflows, change billing or bypass protection. A prior release's CI exception applies only to its recorded scope/candidate; it is not a standing waiver for new features. Complete the reviewed candidate and feasible local validation before requesting a genuinely missing decision, citing the exact repository/owner gate. Reuse an existing exception only when its recorded scope covers the current candidate; never claim it supplies missing hosted evidence.

Use normal merges after current required checks and independent review. Verify the final remote configured/discovered base branch, post-merge checks and owned clean checkout synchronization. A partial prerequisite PR does not close its parent acceptance issue. Do not delete worktrees or branches containing unrelated or local-only work.

## Deployment handoff across machines

Repository access and deployment SSH access are separate capabilities. Verify each from the machine that will execute it. Prefer an existing authenticated Windows route when the remote worker cannot deploy; keys stay with their owner. Never send private keys or raw tokens in pane prompts, artifacts or logs.

The producing agent prepares the reviewed immutable artifact, revision/tree identity, manifest, archive SHA-256, scoped deploy/readback/rollback scripts, baseline evidence and remaining acceptance gaps. The executing coordinator retrieves it through an authorized route, validates archive paths and digest before extraction into a new directory, inspects scripts and parses them in the actual platform runtime. Stop on drift or partial-failure uncertainty; inspect receipts before retrying.

Compare every extracted application payload file against the reviewed manifest before upload and after any executor-side helper correction. The executor must not patch the application payload in place; payload changes require a newly identified, reviewed candidate and matching release authority. Keep deployment/test helper corrections separate: preserve original bytes, create the smallest explicit UTF-8 diff, independently review the change and rerun affected checks. Record both payload and executed helper hashes. A passing browser suite does not prove the harness still contains the intended Unicode inputs or assertions.

Fix test timing by waiting for the actual persistence/transition condition, retaining the behavior assertion. For example, wait for debounced history storage before reload; do not reselect the expected provider after reload to hide a persistence failure. Inspect non-ASCII fixtures against the original UTF-8 source. Preserve failed runs and superseded helpers with the reason for correction; associate successful evidence with the exact corrected helper and unchanged application payload.

Deployment execution requires the current release's existing authorization and exact intended environment. Preserve unrelated files, protected directories and old assets. Upload assets and verify them before switching an index/activation marker where applicable. Do not reuse a previous release's approval for a new candidate merely because both belong to the same repository.

Verify actual remote bytes/revision and appropriate live health/behavior. Run native or browser checks from a capable machine, reporting platform and scope. Intercept external provider submission in synthetic browser tests when no real submission is requested. Keep separate human/device criteria open. Return manifests, operation receipts, failed attempts, successful checks and rollback location to the original coordinator, and verify acknowledgment. The executor supports the existing owner; it does not create a second campaign.
