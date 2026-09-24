# Sprint 13 — Operator Console / Release Operations

## Objective

Provide safe operational surfaces over the checkpointed EpisodeOrchestrator.

The console is a **control plane**, not a provider execution engine.

It supports:

- create/list/load workflows;
- inspect stage status, attempts, costs and artifacts;
- resume an IN_PROGRESS stage using the orchestrator;
- apply one canonical StageExecutionResult;
- apply a sequential bundle of canonical stage results;
- record governed human decisions;
- route regenerate-shot and regenerate-episode decisions;
- run governed Publish dry-run;
- build/download EpisodeReleaseCandidate.

Live publication is intentionally absent.

## Shared service

`extensions/operator_console/service.py` contains
`OperatorConsoleService`.

Both Streamlit and CLI call the same service so governance rules do not diverge
between interfaces.

### Workflow lifecycle

`create_workflow(...)`

Creates and atomically checkpoints a new EpisodeWorkflowState.

`list_workflow_ids()`

Lists only validated JSON checkpoints whose filenames match their workflow IDs.

`load_workflow(...)`

Loads a validated checkpoint or fails closed.

`summarize(...)`

Provides the 12-stage operational view:

- status;
- attempt;
- revision;
- cost;
- execution key;
- artifact count;
- error.

## Canonical stage operation

### Single stage

`apply_stage_result(...)` accepts a canonical `StageExecutionResult` for the
exact current `next_stage`.

The result is passed back through `EpisodeOrchestrator.run_next(...)`, so all
cross-stage validation, budgeting, checkpointing and resume semantics remain active.

### Sequential bundle

`apply_stage_results(...)` processes a tuple of canonical results in order.

It stops when:

- the bundle ends;
- a stage does not PASS;
- Human Review is reached;
- Publish dry-run is reached;
- the workflow completes.

This is the operator equivalent of run-until-blocked without embedding provider
credentials in the console.

## Resume

If the loaded checkpoint already contains:

```text
status = IN_PROGRESS
attempt = N
execution_key = K
```

applying the stage result calls EpisodeOrchestrator, which reuses the same attempt
and execution key.

The console therefore preserves provider-side idempotency semantics from Sprint 12.

## Human Review cannot be bypassed

`apply_stage_result(...)` explicitly rejects:

`human_review`

Human Review must go through:

`record_review_decision(...)`

The service:

1. loads the active ReviewPackage;
2. constructs ReviewDecision;
3. validates the decision against the package **before persistence**;
4. appends the decision to JsonlReviewDecisionStore;
5. applies it through `apply_review_decision(...)`;
6. checkpoints the resulting workflow.

An invalid approval therefore does not pollute the audit trail.

Supported actions remain:

- approve;
- reject;
- regenerate_shot;
- regenerate_episode.

## Publish dry-run cannot be bypassed

`apply_stage_result(...)` also rejects:

`publish_dry_run`

That stage must use:

`prepare_publish_dry_run(...)`

The service requires:

```text
PublishRequest.dry_run == True
PublishingPolicy.live_publish_enabled == False
```

It then calls the Sprint 11 governed Publishing Gateway with `DryRunPublisher`.

`DryRunPublisher.publish(...)` always raises because the gateway must never reach
the live branch in Operator Console.

The generated PublishResult and PublicationAuditTrail are then passed back through
EpisodeOrchestrator for final cross-stage validation.

## Double protection against live publishing

There is no:

- live publisher adapter import;
- MPT publishing adapter import;
- Upload-Post import;
- live-publish CLI command;
- live-publish Streamlit button;
- `allow_live_publish=True` path.

Even a policy configured for live publication is rejected by OperatorConsoleService.

## Streamlit UI

Run:

```bash
uv run streamlit run extensions/operator_console/app.py
```

Features:

- workflow creation;
- workflow selector;
- revision/next-stage/cost/budget/artifact metrics;
- 12-stage status table;
- single StageExecutionResult upload;
- sequential stage bundle upload;
- Human Review controls;
- render preview when locally available;
- Publish dry-run request/policy upload;
- Release Candidate display/download;
- artifact explorer;
- raw checkpoint view.

Controls are contextual to the current `next_stage`.

## CLI

Run:

```bash
uv run python -m extensions.operator_console.cli <command>
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

The CLI intentionally has no `publish-live` command.

## Storage

Default directories:

```text
output/content_studio/workflows/
output/content_studio/review_audit/
output/content_studio/publication_audit/
```

Environment overrides:

- CONTENT_STUDIO_WORKFLOW_DIR
- CONTENT_STUDIO_REVIEW_LOG_DIR
- CONTENT_STUDIO_PUBLICATION_LOG_DIR

## Governance tests

Sprint 13 tests verify:

- create/list/load/summary;
- duplicate workflow rejection;
- stage execution through EpisodeOrchestrator;
- sequential bundles;
- resume keeps the same execution key;
- manual Human Review injection is rejected;
- manual Publish dry-run injection is rejected;
- valid approval is audited/applied;
- invalid approval is not persisted;
- regenerate-shot rewinds the workflow;
- Publish dry-run creates a Release Candidate without network calls;
- live request is rejected;
- live policy is rejected;
- publication ledger remains empty after rejected live attempts;
- validated checkpoint listing;
- CLI create/list/show;
- UI/CLI/service have no MPT/Upload-Post/live-publish path.

## Cost

Operator Console itself has no provider variable cost.

Publish dry-run uses the gateway validation branch and does not contact providers.

## ADR assessment

No new ADR is required. Sprint 13 exposes operations over existing approved
governance boundaries without changing those boundaries.
