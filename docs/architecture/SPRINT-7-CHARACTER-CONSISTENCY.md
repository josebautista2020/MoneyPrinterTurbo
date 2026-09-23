# Sprint 7 — Character Consistency

## Objective

Make reference-aware visual generation and consistency review first-class,
provider-neutral capabilities.

Sprint 7 does not claim that text-only generation provides identity consistency.
Character/reference assets are explicitly resolved, supplied to a capable generator,
evaluated, and regenerated when the configured threshold is not met.

Default target: at least 0.90 overall consistency and at least 0.90 identity
consistency. The kids-puppies example raises identity minimum to 0.92.

## Reference assets

### ReferenceAsset

A logical visual reference identified by `reference_asset_id`.

It stores:

- URI
- media type
- optional character association
- optional location association
- JSON-safe metadata

### ReferenceCatalog

Project-scoped registry that resolves logical IDs to concrete references.

Example catalogs intentionally use `asset://...` placeholder URIs. They document
identity and ownership but are not accepted by the production OpenAI adapter.
Before paid generation, placeholders must be replaced by:

- HTTPS image URLs
- `openai-file://<file-id>`
- local image paths / `file://` paths

## Bible reference binding

CharacterProfile and LocationProfile already carry `reference_asset_ids`.

`bind_consistency_references(...)` enriches a VisualGenerationPlan with the
current CharacterBible and UniverseBible references.

This deliberately avoids rewriting historical PromptPlan/VisualGenerationPlan
artifacts when a new approved reference image is added later.

Traceability becomes:

```text
CharacterBible / UniverseBible
            |
            v
    reference_asset_ids
            |
            v
VisualGenerationPlan
            |
            v
ReferenceCatalog -> resolved images
```

## Reference-aware generation

### ReferenceAwareVisualGenerator

Provider-neutral protocol requiring a generator to actually consume resolved
ReferenceAsset values.

A normal VisualGenerator is not automatically reference-aware.

### OpenAIReferenceVisualGenerator

Provider adapter under:

`extensions/openai_image_adapter/`

It uses OpenAI Responses image generation with input images. Multiple references
can be supplied through:

- HTTPS URLs
- data URLs produced from local files
- OpenAI file IDs

The adapter requires explicit response-model and image-model configuration.

Paid generation is disabled by default and requires:

`allow_paid_generation=True`

No model name is hard-coded as a permanent production default.

## Consistency evaluation

### ConsistencyAssessment

An evaluator reports four normalized scores:

- identity: 40%
- appearance: 25%
- wardrobe: 20%
- environment: 15%

`overall_score` is the weighted result.

### ConsistencyEvaluator

Provider-neutral vision/evaluation protocol.

Sprint 7 does not ship a fake metadata evaluator as if it were visual similarity.
Tests use deterministic fake evaluators only to validate orchestration.

A future production evaluator may use a vision model, embedding model, or human
review signal, but it must return the canonical assessment contract.

## Acceptance and regeneration

### ConsistencyPolicy

Defaults:

- minimum overall score: 0.90
- minimum identity score: 0.90
- max attempts: 3
- character requests require references

### generate_consistent_visuals

For every VisualRequest:

1. resolve every reference before generation;
2. fail before provider calls if a required reference is missing;
3. generate using ReferenceAwareVisualGenerator;
4. evaluate successful output;
5. accept when policy thresholds pass;
6. otherwise regenerate until max attempts;
7. preserve every attempt and its cost in the report.

No accepted result is silently substituted for a failed consistency check.

## Cost control

When `max_cost_usd` is supplied, Sprint 7 budgets the worst case:

```text
sum(cost_per_generation * max_attempts)
```

for every request before the first provider call.

If any estimate is unknown, budget-controlled execution is rejected.

Discarded regeneration attempts remain included in known cost.

## OpenAI adapter boundary

The reusable Core never imports `openai`.

The OpenAI dependency lives only in:

`extensions/openai_image_adapter/`

MoneyPrinterTurbo remains behind:

`extensions/mpt_adapter/`

This preserves provider replaceability.

## Vertical isolation

Generic examples:

`extensions/content_studio/examples/`

Kids-puppies references and policy:

`verticals/kids_puppies/consistency/`

Toby/Luna IDs and rules remain outside Core defaults.

## CI safety

All OpenAI adapter tests inject a fake client.

CI must not:

- contact OpenAI
- upload files
- create image jobs
- incur image-generation cost

## Safety boundary

Character consistency is a quality gate, not the child-safety gate.

Safety + QA + Human Review remain mandatory before publication.

## ADR assessment

No new ADR is required. Provider-specific image generation remains an external
adapter while canonical consistency contracts remain in Content Studio Core.
