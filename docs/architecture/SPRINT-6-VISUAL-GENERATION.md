# Sprint 6 — Visual Generation

## Objective

Introduce a provider-neutral visual generation layer that turns `PromptPlan` into
traceable per-shot generation requests and results, with explicit cost controls and
a concrete MoneyPrinterTurbo image adapter behind the existing anti-corruption
boundary.

Sprint 6 does not publish content. Safety + QA + Human Review remain mandatory.

## Core contracts

### VisualRequest

One request per `ShotPrompt`, preserving:

- project/story/episode/scene/shot IDs
- prompt text
- aspect ratio and resolution
- target duration
- character IDs
- negative constraints
- reference asset IDs
- requested asset kind

### VisualGenerationPlan

A complete one-to-one request set for one PromptPlan.

It rejects missing, duplicated or unknown shots and preserves the PromptPlan identity.

### VisualArtifact

A generated image/video artifact with:

- stable asset/request/shot IDs
- artifact URI
- engine/provider identity
- actual width/height when known
- duration target when relevant
- JSON-safe provenance metadata

### VisualResult

Exactly one request outcome.

Successful results must contain artifacts and no error. Failed results must contain
an error and no artifact. `cost_usd` is optional because some provider paths cannot
provide a reliable price estimate.

### VisualGenerationReport

Batch report containing one `VisualResult` per request.

It exposes:

- `success`
- `known_cost_usd`
- `cost_complete`

Unknown cost is kept unknown rather than silently treated as zero.

## VisualGenerator

Provider-neutral protocol:

```python
estimate = generator.estimate_cost_usd(request)
result = generator.generate(request)
```

`generate_visuals(...)` can enforce a `max_cost_usd` preflight ceiling.

When a budget is supplied, every request must have a known estimate before any
generation call is made. If cost is unknown or the projected total exceeds budget,
generation is rejected before the first billable call.

## Plan compilation

`build_visual_generation_plan(prompt_plan, project)` creates one VisualRequest per
ShotPrompt and derives aspect ratio/resolution from ProjectSpec.

Traceability remains:

```text
StoryBeat
  -> StoryboardScene
  -> StoryboardShot
  -> ShotPrompt
  -> VisualRequest
  -> VisualResult
  -> VisualArtifact
```

## MoneyPrinterTurbo adapter

`extensions/mpt_adapter/visual.py` contains `MPTImageVisualGenerator`.

It reuses the real MoneyPrinterTurbo implementation:

`app.services.material.generate_images_openai(...)`

That MPT path supports OpenAI-compatible text-to-image endpoints, including local
compatible gateways when configured.

### Governance protections

The adapter:

1. disables paid generation by default;
2. requires explicit `allow_paid_generation=True`;
3. exposes configured unit cost when known;
4. refuses budget-controlled execution when cost cannot be estimated;
5. validates MPT image configuration before invocation;
6. supports only image requests;
7. rejects `reference_asset_ids` because the current MPT image function does not
   accept reference images;
8. never publishes generated media.

Rejecting unsupported reference assets is intentional: silently dropping reference
images would undermine character-consistency guarantees.

## Character consistency boundary

Sprint 6 preserves reference asset IDs through the canonical pipeline, but MPT's
current OpenAI-compatible image function is text-to-image only.

Sprint 7 — Character Consistency must add or select a generator/adapter that can
actually consume character reference images (or another explicit consistency
mechanism) before claiming reference-based identity preservation.

## CI safety

Adapter tests monkeypatch the MPT material functions. CI must never contact an
external image provider or create billable jobs.

## Vertical isolation

Generic VisualGenerationPlan examples live under:

`extensions/content_studio/examples/`

Kids-puppies visual plans live only under:

`verticals/kids_puppies/visuals/`

No puppy-specific names, provider keys or paid configuration enter the reusable Core.

## ADR assessment

No new ADR is required. The concrete MPT visual integration remains inside the
ADR-0003 anti-corruption layer. A future decision to make a particular external
image provider the default production generator would require separate review.
