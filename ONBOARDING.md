# Start here: agentic-services-orchestrator-skill

<p align="center"><img src="assets/logo.png" alt="CompleteTech LLC logo" width="260"></p>

**CompleteTech LLC Skills** — Workflow coordination and bounded execution supervision.

[Overview](README.md) · [Agent instructions](SKILL.md) · [Contributing](CONTRIBUTING.md) · [Skill library](https://github.com/CompleteTech-LLC/agentic-services-orchestrator-skill/blob/main/references/skill-family.md)

## 1. Choose the right skill

This is an `orchestrator`. Its install/activation key is **`agentic-services-orchestrator-skill`**. Use the orchestrator when work spans multiple specialists; install only the specialists the engagement needs. Install the complete skill directory, including `SKILL.md`, references, scripts and assets, in the directory supported by your agent. Do not install only the Markdown file. Keep this skill separate from its siblings.

## 2. Get a full checkout and prepare Python

Python 3.12 is the shared CI baseline. Git is needed only for cloning. The full GitHub checkout includes the existing brand assets; text-only registry packages can omit binary logos/previews and are not the target of the checkout validator.

```bash
git clone https://github.com/CompleteTech-LLC/agentic-services-orchestrator-skill.git agentic-services-orchestrator-skill
cd agentic-services-orchestrator-skill
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/validate_package.py
```

On Windows PowerShell, create the environment with `py -3 -m venv .venv`, then use `.\.venv\Scripts\python.exe` instead of `python` in subsequent commands. Activation is optional; do not change machine execution policy for this skill. For an existing checkout, skip `git clone` and start at environment setup.

## 3. Run a safe demonstration

Run from the skill root. The commands below use bundled synthetic/example inputs, not client data. They can replace an earlier demonstration at the same output path; choose a new filename when retaining prior output.

```bash
python scripts/render_pdf.py --markdown assets/examples/example.md --out output/onboarding-demo.pdf --logo assets/logo.png --title "Orchestration demonstration"
```

The bundled orchestration overview renders to `output/onboarding-demo.pdf`; generating this PDF does not execute a workflow or approve a transition. For executable coordination, start with `python scripts/orchestration.py --help` and the synthetic [working examples](examples/README.md). The [migration guide](references/migration.md) explains importing existing `project_state` facts and explicit transition policy. The local core and handoffs require neither Herdr nor a Git repository.

Open the generated output and inspect page breaks, tables, logo, text and any remaining placeholders. Package validation checks structure; it does not certify visual quality or factual correctness. Committed previews in `assets/examples/` are references, not destinations for your first run.

## 4. Use the skill with your agent

Read [SKILL.md](SKILL.md), select `agentic-services-orchestrator-skill` using your agent's skill activation mechanism, and provide verified inputs, the requested artifact, destination and required approval owners. Agent discovery paths differ by product; follow that product's installation documentation rather than assuming one global path. Do not grant broader permissions simply because multiple skills are installed together.

## Branding and handoff

Use the existing CompleteTech LLC logo and the practical, evidence-led voice described in [README.md](README.md). The code license does not grant logo, seal or signature rights: follow [BRAND_ASSETS.md](BRAND_ASSETS.md). Do not replace or republish private artwork or fonts.

For a multi-skill handoff, preserve the source facts, artifact paths, approval owner/status, blockers and next specialist in the orchestrator's existing `project_state` schema. Executable assignments add stable IDs, revisions and approval references while keeping workflow state authoritative. JSON contracts and SQLite state are operational artifacts; branded PDFs are for appropriate human-facing documents. Do not treat a generated artifact, anonymization or successful check as permission to send, publish, bill, sign, award or launch.

## Safety and permissions

Workflow processing, validation, handoff preparation, and document rendering are local. The coordinator writes a selected SQLite store outside Git checkouts; adapters write selected private bundles outside installed skill checkouts or call explicitly supplied native controls. Native callbacks and selected Herdr session controls may access authorized external services. Installation may contact GitHub and package indexes. No component installs background services or schedules. Review the component boundary table in [architecture](references/orchestration-architecture.md) before using real inputs, and keep credentials/private state outside version-controlled workspaces.

## Troubleshooting and verification

A missing module usually means the active interpreter differs from the one used for `pip`; use `python -m pip` in the same environment and this repository's `requirements.txt`. Missing logos or references usually indicate a partial/text-only installation or the wrong working directory; use a full checkout and run from its root. Do not download replacement branding from unrelated sources.

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/validate_package.py
```

Package-only checks use the standard library; orchestration checks use the pinned schema/YAML dependencies. The suite uses synthetic fixtures and does not scan accounts, run client workflows, contact live services, or install schedules. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [QUALITY.md](QUALITY.md) for the additional lint, rendering, parser and diagram checks.
