# Local orchestration examples

Run from the skill root after installing `requirements.txt`. All fixtures are
synthetic. Their authorization, review, progress, and remote-operation receipts are
explicitly labeled `SIMULATED`; they are not client permission or live verification.

```bash
python examples/run_demo.py --out /tmp/orchestration-demo
```

On Windows, use a writable path such as `C:/Temp/orchestration-demo` after confirming
that it is outside any Git checkout. A home directory can itself be a Git checkout,
so the usual user-profile temporary directory is not always suitable.

Choose a new private output directory outside the skill checkout and all enclosing
version-control workspaces. Preserve the output to inspect or resume
the saved workflow; do not reuse a fresh database as recovery for an existing run.

The demo uses the same coordinator, schemas, domain definitions, and handoff
adapter as normal operation. It demonstrates a services assignment whose result
cannot advance discovery until its artifact acceptance gate passes, a non-software
hiring assignment, and software delivery with review/check/endpoint evidence. It
also reopens persisted state after a simulated interruption and reconciles the
existing identity before continuing. No Herdr, Git repository, agent service, or
network call is required.

`integration_fixtures.py` supplies explicit workflow, assignment, observation,
result, approval, and supervisor-readback data. It is test/example material, not a
live runtime adapter. A submitted handoff is not acceptance; the fixture then
supplies separate acknowledgment and useful-work observations. A worker's completed
result remains pending until supervisor verification. The coordinator subsequently
checks current workflow gates before consuming it.

## Inspect and validate

The coordinator's actual CLI lists supported operations and input meanings:

```bash
python scripts/orchestration.py --help
python scripts/orchestration.py validate --kind assignment --file /private/path/assignment.json
python scripts/orchestration.py validate --kind result --file /private/path/result.json
python scripts/orchestration.py inspect --db /private/path/run.sqlite
```

Use `--file` for JSON inputs and `--definition` for the chosen YAML domain. `init`
creates the workflow in a selected existing private directory. `handoff` accepts an
assignment file and `--out` private bundle directory; it persists intent before
preparing that handoff. `record`, `verify`, `reconcile`, `stop`, and `update` require
the current execution or workflow revision and the authoritative actor. `consume`
requires the current workflow revision. Revisions printed by one step are the
inputs to the next; do not hardcode revision numbers for a resumed run.

The Python API supports native callback bindings and the optional Herdr bridge as
described in [runtime adapters](../references/runtime-adapters.md). These examples
exercise explicit handoff, which also works for a human specialist.

## CLI receipt inputs

Replace the placeholder IDs, paths, evidence, and `REVISION` below with the current
saved identity and execution revision. Acquire trusted readback before filling
these objects; copying worker assertions or fixture receipts is not verification.

For `verify`, save a `verification.json` object:

```json
{
  "result_id": "RESULT_ID_FROM_SAVED_RESULT",
  "result_digest": "CANONICAL_DIGEST_OF_SAVED_RESULT",
  "verifier": "EXECUTION_OWNER",
  "evidence": "REFERENCE_TO_SUPERVISOR_READBACK",
  "artifact_versions": [{"artifact": "briefing", "version": "v2"}],
  "endpoint": {"kind": "task", "verified": true, "revision": "v2", "receipt": "REFERENCE_TO_ENDPOINT_READBACK"}
}
```

Artifact versions and endpoint must match the saved result after independent
readback. Compute its canonical digest from the exact result JSON:

```bash
python -c "import json,sys; sys.path.insert(0,'scripts'); from contracts import canonical_digest; print(canonical_digest(json.load(open(sys.argv[1],encoding='utf-8'))))" /private/path/result.json
python scripts/orchestration.py verify --db /private/path/run.sqlite --file /private/path/verification.json --assignment-id ASSIGNMENT_ID --actor EXECUTION_OWNER --expected-revision REVISION
```

For recovery, save `reconciliation.json`. Replace `effective_runtime: {}` with the
full observed object from the [runtime observation example](../references/runtime-adapters.md#native-observations):

```json
{
  "owner": "EXECUTION_OWNER",
  "evidence": "REFERENCE_TO_EXISTING_OWNER_READBACK",
  "accepted_assignment_digest": "DIGEST_ACKNOWLEDGED_BY_EXISTING_OWNER",
  "effective_runtime": {},
  "resume": true,
  "owner_available": true,
  "operations": [],
  "resolved_pending_actions": []
}
```

The digest command also works on assignment JSON, but a locally computed hash does
not prove receiver acceptance. Use `resume: false` when recording evidence without
resuming. Populate `operations` for each uncertain saved operation using its same
`operation_id`, `kind`, and `revision`, definitive `status` (`succeeded`, `failed`,
or `not-performed`), and readback `receipt`. List only verified resolved actions in
`resolved_pending_actions`; empty arrays do not clear saved uncertainty.

```bash
python scripts/orchestration.py reconcile --db /private/path/run.sqlite --file /private/path/reconciliation.json --assignment-id ASSIGNMENT_ID --actor EXECUTION_OWNER --expected-revision REVISION
```

For `stop`, save `stop.json` as
`{"reason":"INTENTIONAL_STOP_REASON","evidence":"REFERENCE_TO_STOP_REQUEST"}`:

```bash
python scripts/orchestration.py stop --db /private/path/run.sqlite --file /private/path/stop.json --assignment-id ASSIGNMENT_ID --actor EXECUTION_OWNER --expected-revision REVISION
```

Stopping records intent and leaves worker-stop/no-relaunch verification pending;
it does not terminate processes itself. Each successful mutation returns a new
revision; read that revision before the next command.

## Recovery and failure demonstrations

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

The regression suite covers duplicate dispatch, stale results, changed artifact
versions, scoped approval reevaluation, partial work, failed checks, uncertain
external operations, intentional stops, preserved native identity, and recovery
without extending original deadlines. Read individual assertions and fixture
receipts when assessing what was verified; tests do not establish real PR, merge,
deployment, model configuration, or client outcome evidence.

Existing human-facing orchestration samples remain under `assets/examples/`.
They can be rendered with `scripts/render_pdf.py`; JSON contracts and SQLite state
remain operational artifacts and are not converted to PDFs for execution.
