# Integration validation

Local working-tree validation on 2026-10-14 exercised the real contracts,
coordinator, SQLite persistence, domain definitions, and runtime preparation code.
Agent observations and external operation receipts were synthetic. No client
workflow, real PR, merge, deployment, or live Herdr campaign was launched.

| Check | Observed result |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py' -v` | 91 tests run: 89 passed, 2 skipped for Windows symlink privileges; verified on the Python 3.12 CI baseline and independently on Python 3.14.3 |
| `python scripts/validate_package.py` | Full-checkout package contract passed; existing 27 package regressions retained |
| `python scripts/validate_quality.py` | Python compilation, Ruff, structured parsing, and text-bundle readiness passed; Mermaid skipped because `mmdc` was unavailable; Pyright skipped because no configuration is present |
| `python examples/run_demo.py --out <new-private-directory>` | Six scenarios passed; independent replay and CLI database readback confirmed stage and execution state |
| Independent CLI forward test | Actual local non-software briefing files at versions v1/v2; interrupted-owner recovery, stale/pending approval gates, intentional stop, late-result and duplicate-handoff rejection passed |
| Existing PDF renderer | Synthetic overview rendered successfully in the Python 3.12 environment; this was a rendering smoke check, not visual approval |
| Optional Herdr bridge | All 25 sibling Herdr tests passed; real `prepare_run.py` validation/render/verify preparation and independent replay passed; native control and remote effects were not exercised |
| Documentation and packaging | Integration-guide local links resolved; private state/SQLite sidecar exclusions checked; `git diff --check` passed |

The demo verifies services discovery → proposal only after artifact acceptance,
hiring intake → sourcing only after manager approval, and software implementation
→ review → checks → delivery with simulated independent review and PR readback.
Those workflow records remain `active`. After interrupted submission, the demo
reopens the same store, reconciles the original identity/cutoff, records useful
progress, then preserves an intentional stop and its pending worker-stop check.

The separate forward test wrote actual local briefing revisions and exercised the
public CLI against a private SQLite store. It preserved assignment identity and
failure history after interruption, held the business stage until the revised
artifact's approval passed, and left the wider workflow active. This is live local
filesystem/CLI validation; its supplied approvals and execution observations were
test inputs, and it performed no network or real-client action.

Independent adversarial review produced regression coverage in
`tests/test_orchestration_review.py`. Corrections cover scope matching, unchanged
run limits and authorization windows, separate narrow merge/deployment authority,
extra external effects and required receipts, ownership until result consumption,
concurrent dispatch, acknowledgment/stop races during submission, stale observations,
native session continuity, and scoped reapproval of an exact verified output while
preserving the original assignment and approval history. Core tests also cover
partial results, failed checks, reviewer independence, uncertain outcomes, changed
artifact versions, and dispatch versus supervise semantics.

The local operator and bound callbacks remain responsible for authenticating
identities and acquiring truthful evidence. The helper validates provenance links,
shape, revisions, and gates; it cannot establish the authenticity of arbitrary
caller-supplied receipts. Native callbacks must report actual effective capabilities
and settings. There is no scheduler, background supervisor, exactly-once external
execution guarantee, or active-assignment amendment API.

The generic `skill-creator` quick validator rejects the pre-existing top-level
`version` metadata required by this repository's ClawHub checks. The integration
preserves that metadata and passes the repository-specific packaging contract; it
does not claim compatibility with that conflicting generic validator.

Hosted CI, registry publication, and deployment were not performed. The preserved
quality workflow runs the full suite on Python 3.12 after installing declared
dependencies; the existing cross-platform package matrix remains intact.

## Private repository consolidation

The owner subsequently requested removal of the private Herdr repository. The
preparation helper, 25 original regressions, example configuration and four focused
execution references were copied into `adapters/herdr/`. The adapter defaults to
that bundled helper while preserving explicit helper overrides and the original
three-positional-argument constructor. An added test exercises real local bundled
preparation and duplicate reuse without the separate repository.

The Python 3.12 suite now runs 117 tests: 115 passed and 2 existing Windows symlink
checks skipped. Package validation, Ruff and full Quality passed with the same
Mermaid/Pyright limitations above. The local source checkout and complete Git
history bundle were retained. The initial remote deletion attempt required GitHub's `delete_repo` token scope.
After the owner completed authorization, deletion succeeded. Readback returned
HTTP 404 and the repository was absent from the authenticated owner's repository
list. The local checkout and complete Git-history backup remain preserved.
No publication of the integrated changes occurred.
