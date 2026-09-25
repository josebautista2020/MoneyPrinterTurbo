# ADR-0004 — Runtime Profiles, Allowlisted Providers, and Secret References

- Status: Accepted
- Date: 2026-09-24
- Decision owners: Content Studio Architecture / Supervisor Agent

## Context

Content Studio now has a complete checkpointed episode workflow and an Operator
Console, but provider-backed execution must remain replaceable, auditable, and
separate from reusable Core.

Directly embedding provider configuration or credentials into workflow state would:

- couple Core to specific vendors;
- risk persisting secrets in checkpoints and audit artifacts;
- make provider selection implicit;
- weaken cost and external-call governance;
- make testing depend on real provider configuration.

## Decision

Runtime provider selection is represented by provider-neutral
`RuntimeProfile` contracts in `extensions/content_studio/runtime.py`.

Concrete provider factories live outside Core under
`extensions/runtime_profiles/`.

### Runtime profiles are declarative

A RuntimeProfile contains:

- stable profile ID;
- provider bindings;
- declared capabilities;
- non-sensitive adapter options;
- stage-to-provider bindings;
- external-call authorization flag;
- paid-call authorization flag;
- optional per-stage cost ceiling;
- SecretReference values only.

### Secret values are forbidden

Credentials must not appear in:

- RuntimeProviderBinding.options;
- RuntimeProfile metadata;
- EpisodeWorkflowState checkpoints;
- StageExecutionResult metadata;
- committed examples.

Secrets are referenced using:

```text
env:OPENAI_API_KEY
secret-manager:<logical-name>
file-ref:<path>
```

The current runtime only checks availability. It does not return secret values to
Core or serialize them into workflow state.

### Registry is allowlisted

`RuntimeProviderRegistry` recognizes only explicitly registered adapter IDs.

Unknown adapters, options, capabilities, and missing required configuration fail
closed.

### Providers load lazily

MPT/OpenAI modules are imported only when a concrete adapter factory is invoked.

Listing profiles or rendering a capability matrix does not load provider
implementations or MoneyPrinterTurbo internals.

### Capabilities are explicit

Current capability IDs include:

- `visual.image`
- `visual.image.reference`
- `media.assembly`
- `render.general`

A stage cannot silently use a provider lacking the required capability.

In particular, reference-aware VisualRequests cannot silently drop
`reference_asset_ids` to use a basic image provider.

### External and paid calls need two layers of authorization

The provider binding must opt in:

```text
external_calls_enabled = true
paid_calls_enabled = true
```

and Operator Console execution requires explicit per-run confirmation:

```text
confirm_external = true
confirm_paid = true
```

Paid authorization requires external authorization.

Committed profiles keep both flags disabled.

### Cost remains fail-closed

Provider adapters expose estimates through existing Core protocols.

Runtime stage execution continues to use:

- workflow `max_cost_usd`;
- provider `max_stage_cost_usd`;
- existing visual/media cost preflight;
- historical workflow cost accounting.

Unknown cost remains blocking when a budget ceiling is active.

## Consequences

### Positive

- Core remains provider-neutral.
- Secrets are not persisted in checkpoints.
- Provider choice is explicit and reviewable.
- Runtime profiles are portable and versioned.
- Provider modules are loaded only when needed.
- Tests can inject fake generators/assemblers.
- Kids Puppies can have an isolated runtime profile without polluting Core.

### Trade-offs

- Runtime profiles add configuration objects and validation.
- Reference-aware execution requires a materialized ReferenceCatalog.
- New provider adapters must be registered explicitly.
- Stage wiring must be added deliberately instead of falling back dynamically.

## Rejected alternatives

### Put API keys in runtime options

Rejected because secrets would be serializable and easy to leak into checkpoints
or logs.

### Auto-discover provider modules

Rejected because implicit discovery weakens the allowlist and makes execution less
predictable.

### Silently ignore unsupported reference assets

Rejected because it would degrade character consistency without operator consent.

### Enable provider calls from committed profiles

Rejected. Repository examples remain default-deny.
