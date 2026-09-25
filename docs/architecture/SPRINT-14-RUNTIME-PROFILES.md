# Sprint 14 — Runtime Profiles + Provider Executor Wiring

## Objective

Connect EpisodeOrchestrator provider-backed stages to existing adapters through
explicit runtime profiles while preserving Core/provider isolation, cost governance,
and zero-secret checkpoints.

## Architecture

```text
RuntimeProfile
 ├─ provider bindings
 │   ├─ adapter id
 │   ├─ capabilities
 │   ├─ SecretReference[]
 │   ├─ non-sensitive options
 │   ├─ external_calls_enabled
 │   ├─ paid_calls_enabled
 │   └─ max_stage_cost_usd
 └─ stage_bindings
       │
       v
RuntimeProviderRegistry
  allowlist + validation
       │
       v
RuntimeExecutorFactory
 ├─ visuals -> RuntimeVisualStageExecutor
 └─ media   -> RuntimeMediaStageExecutor
       │
       v
EpisodeOrchestrator
       │
       v
checkpoint / cost / artifacts
```

Provider imports are lazy and remain outside reusable Core.

## Provider-neutral contracts

`extensions/content_studio/runtime.py` defines:

- SecretReference
- RuntimeProviderBinding
- RuntimeProfile
- SecretAvailability Protocol
- capability constants
- capability validation
- secret availability validation

Sensitive keys are recursively rejected from runtime options.

## Registered adapters

Current registry:

| Adapter | Capability | External execution |
| --- | --- | --- |
| mpt-image | visual.image | guarded |
| openai-reference-image | visual.image.reference | guarded |
| mpt-media | media.assembly | guarded |
| mpt-render | render.general | registered for future wiring |

Unknown adapters fail closed.

## Visual executor

`RuntimeVisualStageExecutor` builds the canonical VisualGenerationPlan from:

`ProjectSpec + PromptPlan`

For basic plans it uses the VisualGenerator protocol and `generate_visuals(...)`.

For plans containing reference_asset_ids:

- `visual.image.reference` is mandatory;
- ReferenceCatalog must exist and match project_id;
- every referenced ID must resolve;
- a request without references cannot be silently routed through a
  reference-only provider;
- no reference IDs are dropped.

## Media executor

`RuntimeMediaStageExecutor` builds MediaAssemblyPlan from:

`ProjectSpec + StoryPlan + ConsistencyReport`

It derives the narration script from StoryPlan beats and uses profile options for:

- voice_name
- output_uri_template
- subtitle_enabled
- adapter work directory / cost estimate

Assembly executes through the existing `assemble_media(...)` Core function.

## Cost governance

Effective stage ceiling is the minimum of:

- remaining EpisodeWorkflowState budget;
- RuntimeProviderBinding.max_stage_cost_usd.

Existing provider estimates remain authoritative.

Provider costs are returned through StageExecutionResult and therefore remain part
of workflow historical cost.

## Operator Console integration

New CLI commands:

- `runtime-matrix --profile <file>`
- `run-runtime --workflow-id <id> --profile <file>`

External profiles additionally require:

- `--confirm-external`

Paid profiles additionally require:

- `--confirm-paid`

Streamlit exposes equivalent checkboxes before runtime execution.

The Operator Console never persists the RuntimeProfile in EpisodeWorkflowState.

Only non-sensitive execution metadata is checkpointed:

- runtime profile ID
- provider ID
- adapter ID
- execution key
- cost/status

## Secret handling

Environment secret availability can be checked through
`EnvironmentSecretAvailability`.

It exposes only:

`is_available(reference) -> bool`

There is intentionally no `resolve()` method.

Secret-manager references are fail-closed until an explicit resolver is added.

## Committed profiles

### offline

No provider bindings and no external calls.

### mpt-guarded

Visual + media bindings with external and paid calls disabled.

### openai-reference-guarded

Reference-aware visual provider with:

`env:OPENAI_API_KEY`

as a reference only. Calls and spend remain disabled.

### kids-puppies-guarded

Vertical-isolated profile using:

- OpenAI reference-image for visuals;
- MPT media for assembly.

The current Kids Puppies ReferenceCatalog still contains placeholder asset URIs, so
reference generation remains operationally blocked until those references are
materialized.

## CI safety

Runtime tests inject fake VisualGenerator and MediaAssembler instances.

CI does not:

- instantiate a live OpenAI client;
- invoke MPT image generation;
- invoke TTS providers;
- create paid requests;
- publish content.

Variable provider cost: $0.

## Publication boundary

Sprint 14 changes generation/runtime wiring only.

Publishing remains governed by Sprint 11 and Operator Console still exposes only
Publish dry-run.

## ADR

ADR-0004 records the runtime profile / provider registry / secret-reference
decision.
