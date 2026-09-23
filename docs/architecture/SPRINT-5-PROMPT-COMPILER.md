# Sprint 5 — Prompt Compiler

## Objective

Compile a validated `StoryboardPlan` into provider-neutral per-shot prompt packets
that preserve visual identity, world continuity, camera intent and traceability.

Prompt compilation is deliberately separated from rendering providers. OpenAI,
Gemini, Veo, Runway, Kling, Midjourney and MoneyPrinterTurbo syntax do not belong
in the canonical Core.

## Core contracts

### ShotPrompt

One compiled prompt per storyboard shot.

It carries:

- stable prompt/scene/shot/location IDs
- shot duration
- canonical character references
- provider-neutral `visual_prompt`
- `negative_constraints`
- `reference_asset_ids`
- JSON-safe metadata

### PromptPlan

Contains every `ShotPrompt` for one storyboard.

It requires:

- unique prompt IDs
- exactly one prompt per storyboard shot
- no unknown or missing shots
- exact scene/location/character preservation
- duration preservation within a small floating-point tolerance

### PromptContext

Binds the compiler to canonical context:

- `ProjectSpec`
- `StoryPlan`
- `CharacterBible`
- `UniverseBible`

The Storyboard is revalidated against this context before prompt compilation.

### PromptCompiler

Provider-neutral protocol:

```python
plan = compiler.compile(storyboard, context)
```

`compile_prompts(...)` guards any injected implementation and rejects output that
is not a valid `PromptPlan`.

### CanonicalPromptCompiler

A deterministic reference implementation that assembles visual intent from:

- shot action/framing/camera
- location description and visual traits
- location ambience and consistency rules
- universe world rules
- character signature features and wardrobe
- storyboard composition/continuity notes

Negative constraints are built from location and character `forbidden_changes`.
Reference assets are aggregated from location and character profiles, preserving
order and removing duplicates.

The output is plain provider-neutral language. Provider adaptation belongs to the
future rendering adapter layer, not this compiler.

## Architecture

```text
ProjectSpec
 + StoryPlan
 + CharacterBible
 + UniverseBible
        |
        v
   PromptContext
        |
StoryboardPlan
        |
        v
   PromptCompiler
        |
        v
    PromptPlan
        |
        +-- ShotPrompt #1
        +-- ShotPrompt #2
        +-- ...
        |
        v
Sprint 6 Visual Generation / Rendering adapters
```

## Continuity guarantee

The compiler never invents canonical IDs. It can only compile shots already
validated by the Storyboard layer.

A ShotPrompt must preserve:

```text
StoryboardScene.scene_id
StoryboardShot.shot_id
StoryboardScene.location_id
StoryboardShot.character_ids
StoryboardShot.duration_seconds
```

This creates a traceable chain:

```text
StoryBeat -> StoryboardScene -> StoryboardShot -> ShotPrompt
```

## Vertical isolation

Generic examples live under:

`extensions/content_studio/examples/`

Kids-puppies prompt examples live only under:

`verticals/kids_puppies/prompts/`

Toby/Luna, child-facing language and puppy-specific rules are never Core defaults.

## Safety and provider boundaries

Negative constraints preserve consistency and world restrictions, but the Prompt
Compiler is not the final safety authority. Dedicated Safety + QA + Human Review
remain mandatory before publication.

Provider-specific syntax, model IDs, quality flags, seeds, CFG values, API keys or
vendor request payloads must be implemented outside this canonical module.

## ADR assessment

No new ADR is required. Sprint 5 follows the upstream-preserving, governed
composition boundaries established by ADR-0001/0002/0003.
