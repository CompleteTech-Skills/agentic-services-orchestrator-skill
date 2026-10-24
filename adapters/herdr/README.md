# Bundled Herdr preparation

The optional runtime adapter includes its preparation helper, example configuration,
and session/delivery/recovery references here. No separate repository is required.
The files were imported from `CompleteDotTech/orchestrate-herdr-delivery` at
revision `ddf383c9e1d8caa1abbcc83d4519e9e0953ec43f` in preparation for the owner-requested
repository retirement. The previous local checkout and Git history were preserved separately.

`scripts/prepare_run.py validate/render/verify` retains its offline behavior and
reads the adjacent `references/`. It prepares artifacts only. It cannot grant
approval, launch agents, or establish that a remote action completed. For current
workflow ownership and the runtime API, read
[runtime adapters](../../references/runtime-adapters.md).

From the integration root:

```text
python adapters/herdr/scripts/prepare_run.py validate --config <private-config.json>
python adapters/herdr/scripts/prepare_run.py render --config <private-config.json> --out <new-private-run-directory>
python adapters/herdr/scripts/prepare_run.py verify --run <received-run-directory> --expected-prompt-sha256 <independently-recorded-source-digest>
```

The example in `assets/run.example.json` is synthetic and supplies no authority.
The existing 25 helper regressions are included in the integration's main test suite.
