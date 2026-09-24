# Content Studio Operator Console

Operational UI and CLI over the checkpointed EpisodeOrchestrator.

## Streamlit

```bash
uv run streamlit run extensions/operator_console/app.py
```

## CLI

```bash
uv run python -m extensions.operator_console.cli list
uv run python -m extensions.operator_console.cli show --workflow-id <id>
```

Commands:

- `list`
- `create`
- `show`
- `artifacts`
- `apply-stage`
- `apply-bundle`
- `review`
- `publish-dry-run`
- `release`

Storage can be changed with:

- `CONTENT_STUDIO_WORKFLOW_DIR`
- `CONTENT_STUDIO_REVIEW_LOG_DIR`
- `CONTENT_STUDIO_PUBLICATION_LOG_DIR`

## Governance

The console deliberately has no live-publish command or UI control.

`human_review` cannot be completed through `apply-stage`; it must use an
audited ReviewDecision.

`publish_dry_run` cannot be completed through `apply-stage`; it must use the
governed Publishing Gateway, and the service rejects:

- `PublishRequest(dry_run=False)`
- `PublishingPolicy(live_publish_enabled=True)`

Provider executors remain outside this operator package.
