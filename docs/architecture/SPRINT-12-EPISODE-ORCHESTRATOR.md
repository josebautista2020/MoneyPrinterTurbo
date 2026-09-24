# Sprint 12 — End-to-End Episode Orchestrator / Release Candidate

## Objective

Connect the canonical contracts built in Sprints 1–11 into one explicit,
checkpointed episode workflow without moving provider behavior into reusable Core.

The workflow stops for human review and ends with **publish dry-run**, never live
publication.

## Canonical stage order

```text
project_episode
      ↓
bibles
      ↓
story
      ↓
storyboard
      ↓
prompts
      ↓
visuals
      ↓
consistency
      ↓
media
      ↓
safety_qa
      ↓
review_package
      ↓
human_review
      ↓
publish_dry_run
```

The order is defined by `WORKFLOW_STAGES` and is not inferred dynamically.

## WorkflowArtifact

A typed wrapper around an existing canonical JsonContract.

It contains:

- artifact ID
- canonical contract type
- canonical contract payload
- optional URI
- metadata

The wrapper reconstructs the underlying contract during validation. Arbitrary
unvalidated dictionaries cannot be marked as canonical workflow artifacts.

## StageExecutionResult

One executor result:

- stage
- PASS / FAIL / BLOCKED
- canonical artifacts
- actual cost
- error
- metadata

PASS results undergo cross-stage validation before the workflow can advance.

## WorkflowStageRecord

Checkpointed execution evidence:

- stage/status
- attempt
- deterministic execution key
- workflow revision
- started/finished timestamps
- artifacts
- actual cost
- error
- superseded flag

An IN_PROGRESS record is saved before invoking the executor.

If the process dies after that checkpoint, resume reuses the **same execution key**
instead of generating a new one.

## EpisodeWorkflowState

The workflow state contains:

- workflow/project/episode IDs
- workflow revision
- immutable historical stage records
- optional maximum cost
- metadata

It exposes:

- active records
- latest record per stage
- exact stage status
- accumulated historical cost
- next stage
- completion status
- canonical artifacts by type

Superseded records remain in history and their incurred cost remains visible.

## Cross-stage traceability

PASS is not based only on isolated JSON validity.

The orchestrator validates:

- ProjectSpec contains the exact EpisodeSpec
- CharacterBible and UniverseBible cover ProjectSpec
- StoryboardPlan validates against StoryPlan
- PromptPlan validates against StoryboardPlan
- VisualGenerationPlan validates against PromptPlan
- VisualGenerationReport validates against VisualGenerationPlan and succeeds
- ConsistencyReport validates against VisualGenerationPlan and succeeds
- MediaAssemblyResult validates against MediaAssemblyPlan and succeeds
- Safety/QA requires passing RenderQAReport and eligible HumanReviewGate
- ReviewPackage render matches the actual MediaAssemblyResult
- ReviewPackage Safety/QA evidence matches workflow evidence
- ReviewPackage shot IDs match ConsistencyReport
- human_review PASS requires an approved ReviewDecision that is latest in its audit
- publish_dry_run requires a successful dry-run PublishResult and matching publication audit
- dry-run PublishRequest must reference the same ReviewPackage, approval and render

## EpisodeStageExecutor

Provider-neutral protocol:

```python
estimate_cost_usd(state) -> float | None
execute(state, execution_key) -> StageExecutionResult
```

Core orchestration does not import MPT, OpenAI, Streamlit, requests, vertical code,
or adapter packages.

## Checkpoint store

`JsonWorkflowCheckpointStore` lives under `extensions/orchestration/`.

It:

- stores one JSON checkpoint per workflow;
- validates every loaded EpisodeWorkflowState;
- writes through a temporary file;
- flushes and fsyncs;
- atomically replaces the previous checkpoint.

The store implements `WorkflowCheckpointStore` and can later be replaced by a
database/object-store implementation.

## Resume and idempotency

Before calling a stage executor, the orchestrator persists:

```text
status = IN_PROGRESS
execution_key = deterministic(workflow, revision, stage, attempt, inputs)
```

If that checkpoint is resumed, the same attempt and execution key are reused.

Executors can therefore implement provider-side idempotency without the Core
knowing provider details.

## Cost governance

When `max_cost_usd` is configured:

- an unknown stage estimate blocks before execution;
- estimated remaining cost over budget blocks before execution;
- actual incurred cost is always retained;
- if actual cost exceeds the remaining budget, the stage becomes FAIL;
- cost from failed and superseded attempts remains in historical spend.

A cross-stage validation failure after generation preserves the actual reported
cost instead of rewriting it to zero.

## Human Review

No executor is required for `human_review`.

When absent, the workflow naturally reaches:

```text
human_review = BLOCKED
publish_dry_run = PENDING
```

`apply_review_decision(...)` then handles:

### approve

Adds an auditable PASS for human_review.

### reject

Adds FAIL and leaves publishing unavailable.

### regenerate_shot

Supersedes active records from `visuals` onward, increments workflow revision,
preserves history/cost, and resumes from Visuals.

### regenerate_episode

Supersedes active records from `story` onward, increments revision, and resumes
from Story.

## Release Candidate

`build_release_candidate(...)` is allowed only when every workflow stage is PASS.

It requires:

- approved ReviewDecision
- successful PublishResult
- PublishResult is dry-run
- matching PublicationAuditTrail
- no live publication

Output:

`EpisodeReleaseCandidate(publication_status="dry_run_validated")`

This is the first complete end-to-end release-candidate state, but it is still not
a published episode.

## Offline CI

Sprint 12 CI uses deterministic fixture executors.

The E2E test:

1. executes all stages through ReviewPackage;
2. proves Human Review blocks the pipeline;
3. applies an audited approval;
4. runs Publish dry-run;
5. creates EpisodeReleaseCandidate;
6. verifies checkpoint reload;
7. performs zero external calls.

Additional tests cover:

- resume from IN_PROGRESS with the same execution key;
- unknown-cost budget block;
- estimated-cost budget block;
- actual-cost overrun;
- regenerate-shot rewind;
- regenerate-episode rewind;
- human rejection;
- atomic checkpoint round-trip;
- contract schemas and Core boundaries.

## Publication boundary

Sprint 12 does **not** enable live publication.

The final stage is named `publish_dry_run` deliberately.

Live publishing still requires the governed double opt-in implemented in Sprint 11
and a future explicit user action.

## ADR assessment

No new ADR is required. The orchestrator composes previously approved contracts and
respects the existing Core/provider/vertical boundaries.
