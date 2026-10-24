# Session control and permission correction

Installed CLI help is authoritative. Use the same explicit server/session selector for discovery and mutation. For this machine the historical route was Windows SSH -> `herdr-vm-stage` -> Podman `session-home-complete-tech` -> Herdr session `default`; it is an example to verify, not a universal default. Never assume pane IDs from a previous run.

Read `agent get`, `agent read --source visible`, and `pane process-info --pane <id>`. Working alternate-screen agents may reject large history reads; switch to visible output rather than scrolling or repeatedly retrying. An initial new session may expose its UUID only after the first turn.

## Account launchers

Discover launchers on the actual execution host/container. `claude2`, where installed, selects an alternate Claude account/profile; it is not a model name or a fast-mode setting. Check the launcher's version and supported authentication-status command without exposing credentials. Launcher presence and a logged-in status do not establish requested-model access, effective tier or inference capacity; verify those separately before claiming useful work.

For new authorized Claude workers, consider the available `claude2` route when selecting an account that supports the requested model. Honor an explicitly selected launcher. Account selection is separate from model fallback: preserve the requested model where supported and apply the recorded fallback condition only on actual evidence. Record each worker's launcher/account, native UUID, model and tier in its receipt. `target.account` identifies the receiving coordinator, not all workers. Resume existing sessions with their original account and UUID; a newly available launcher does not by itself authorize account migration, replacement or a duplicate owner.

## Prompt transport

1. Write the complete assignment to a UTF-8 file with explicit encoding and record its SHA-256 before transfer. Include literal quotes, dollar signs, backticks and Unicode unchanged. Do not pass the assignment through PowerShell interpolation or a multi-shell command string.
2. Transfer bytes through the existing authorized file route into the receiver's native filesystem. Verify the digest there against the separately recorded source value. For a generated run directory use the helper's `verify` command; for a standalone follow-up hash its actual bytes. If the destination is inside a container, check the final file inside that container, not only the SSH host copy.
3. Send only a short instruction naming the exact native path, contract/delta ID and digest through the installed supported agent API. Use argument arrays for local process launch. SSH still evaluates a remote command through a shell: for a POSIX receiver use `shlex.join(remote_argv)` in Python, including the short path instruction as one argument; do not use `JSON.stringify`, PowerShell escaping or manual quote replacement as POSIX shell quoting. Verify each container/CLI boundary against installed help.
4. Read back the receiver's acknowledgment of that ID/digest and fresh useful progress. A successful transport, queued prompt or generic working status is not proof it consumed this assignment. After an ambiguous error, inspect the destination and queue before retransmission.

When reading or editing scripts on Windows, specify UTF-8 explicitly and compare original bytes. A mojibake-corrupted file and a diff produced with the same wrong decoder can agree while both are wrong. Preserve the original file and inspect expected Unicode fixtures as well as test results.

## Live model changes

Use raw pane text for native slash commands; agent prompts may bracket-paste them as ordinary text. Send `/model`, wait, then Enter; inspect the actual model menu and reasoning menu. Prefer session-only selection where available. Verify confirmation, footer and fresh runtime metadata. A process started with one model can later use another; old argv alone is not enough.

Use normal inference by default; do not enable `/fast` or an equivalent setting unless the user specified it. Luna is the exception and always requires fast. Check the actual selected model and tier for every role, including fallback workers. Apply the policy again after model changes and resume. If a non-Luna session inherited fast from a preset or a prior Luna model, correct it through supported session controls unless current user instructions explicitly retain fast. Do not change account-wide defaults or blindly toggle an unknown current state.

## Authorized `--yolo` restart

1. Verify UUID, account, cwd, goal, current work, pending UI and original process IDs. Read only the account/profile variable needed, not the full environment. Preserve receipts and any draft. Record the original goal identity/state.
2. Settle a pending command only within already granted authority. A harmless read approval may be accepted; a question requiring a user's choice cannot. If suspending the session, record that the interruption is for permission correction rather than an intentional task stop.
3. Interrupt only the owned coordinator when necessary, then use native `/exit` or supported graceful exit. Verify the shell is foreground and the original writer has exited; do not launch another controller while it is alive.
4. Resume using the same account launcher and exact UUID, e.g. `codex1 resume <uuid> --model gpt-6.1-sol -c model_reasoning_effort=high --yolo`. Add a supported fast setting only for an explicit fast request or a Luna model. Select arguments from the contract and installed CLI; do not hardcode this account/model for another run. Omitted flags alone do not prove that a saved fast setting is off; inspect the resumed state.
5. Inspect optional update/trust/paused-goal screens. Skip unrelated updates. A repository just created and inspected for the authorized task can be trusted within that scope; an uninspected folder cannot be treated as equivalent. Resume the same paused goal if the user authorized continuation and the cutoff is valid.
6. Verify exact UUID/account, one writer, effective `danger-full-access` + `never` (or the runtime's equivalent), `--yolo` argv when relaunched, Full Access, unchanged goal identity/accounting, and fresh useful progress. Tell the agent to propagate the authorized launch mode to native Codex workers in this campaign; permissions do not automatically propagate through every external CLI wrapper.

If the user asked only to correct effective permissions and did not require a restart or literal launch flag, a native `/permissions` control can apply the exact policy while preserving ongoing work. An explicit same-session restart or `--yolo` launch request takes precedence: use the graceful resume procedure and verify argv. Report effective policy honestly rather than claiming original process arguments changed. Do not edit a live session database to change model, goal or permissions.

## Provider failures

Distinguish local model validation, authentication, network error and real capacity exhaustion. Probe exact models with a bounded synthetic request before promising substitution. In this environment a prior Claude model-window compatibility setting allowed `claude-sonnet-5-5`; revalidate the installed supported behavior, do not blindly turn off checks or label the warning as capacity. Check command/file type before reading launcher scripts: some similarly named paths are large binaries.

Inspect the actual fast-mode state and reason. `extra_usage_disabled` or unavailable fast inference does not mean the model is exhausted. Luna must use fast: if unavailable, report the precise blocker for that agent and continue independent work. For other models, keep the requested model on an available tier only when explicitly requested fast was a preference; disclose the actual tier. A mandatory tier remains a blocker. Do not enable paid usage. Account launchers can select different available models; verify the native account/profile without printing credentials.

## Stop verification

Identify both the worker and the mechanism that resumes it: owner goal, watchdog, timer, retry queue or restore hook. Send the user stop to the verified owner, persist it in its ledger, revoke pending owned grants/queued starts, and gracefully stop the specified workers. Do not disable global Herdr restore or unrelated jobs merely to stop one repository's agents. Inspect worker processes and a delayed snapshot for relaunch; preserve history. An intentional stop dominates old generic recovery instructions.
