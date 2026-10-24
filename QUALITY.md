# Quality Checks

Run the production-readiness checks from this repository root:

```bash
python3 scripts/validate_quality.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate_package.py
```

The validator compiles Python files, runs Ruff, parses YAML/JSON/INI files, renders Mermaid sources when Mermaid tooling is available, runs generator `--help` smoke checks where generator scripts exist, runs catalog `--list` smoke checks where renderer catalog scripts exist, and runs Pyright when a `pyrightconfig.json` file is present.

GitHub Actions runs the same validator on push and pull request.

The offline test suite additionally exercises assignment/result schemas, runtime
observations, workflow gates, durable recovery, duplicates, stale results,
approval versions, partial work, failed checks, uncertain external outcomes, and
intentional stops. External effects use fixtures or mocks; passing these tests is
not evidence of a live agent run, PR, merge, or deployment. Package-only tests keep
their existing standard-library baseline; orchestration tests require the pinned
dependencies in `requirements.txt`.

See [integration validation](references/integration-validation.md) for the recorded
local checks, independent review, simulated-effect boundary, and tooling limitations.
