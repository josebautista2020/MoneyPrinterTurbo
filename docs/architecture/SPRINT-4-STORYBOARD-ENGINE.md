# Sprint 4 — Storyboard Engine

## Objective

Create a provider-neutral storyboard layer that converts a validated `StoryPlan`
into visual scenes and shots without generating provider prompts or invoking a
rendering engine.

The storyboard is a visual planning artifact. Prompt compilation belongs to Sprint 5.

## Core contracts

### StoryboardShot

Represents one visual shot:

- stable `shot_id`
- order within its scene
- duration
- visual action
- framing
- optional camera angle and movement
- character references
- composition notes
- continuity notes
- JSON-safe metadata

These fields describe visual intent, not provider syntax.

### StoryboardScene

Represents exactly one `StoryBeat` and contains one or more shots.

It preserves:

- beat mapping
- scene order
- canonical location
- scene character set
- shot ordering

Shot characters must be a subset of the scene characters.

### StoryboardPlan

Represents the full visual decomposition of one story.

It requires:

- one storyboard scene per StoryBeat
- unique scene IDs
- unique beat mappings
- unique shot IDs across the full plan
- contiguous scene order
- identity match with StoryPlan
- exact location and character preservation from each StoryBeat
- shot durations that sum to the StoryBeat duration

A small floating-point tolerance is allowed only for arithmetic precision.

### StoryboardContext

Provides `ProjectSpec`, `CharacterBible` and `UniverseBible` context. Before a
storyboard is accepted, the underlying StoryPlan is validated against the same
canonical project and bibles.

### StoryboardEngine

Provider-neutral generation contract:

```python
storyboard = engine.generate(story, context)
```

`generate_storyboard(...)` validates both StoryPlan input and StoryboardPlan output.

## Architecture

```text
ProjectSpec
 + CharacterBible
 + UniverseBible
        |
        v
   StoryboardContext
        |
        +---- StoryPlan
                 |
                 v
          StoryboardEngine
                 |
                 v
          StoryboardPlan
             /       \
   StoryboardScene  ...
          |
      StoryboardShot[]
                 |
                 v
       Sprint 5 Prompt Compiler
```

## Duration and traceability

Every StoryBeat must map to exactly one StoryboardScene.

The sum of all shot durations in a scene must match its StoryBeat duration. This
keeps Story -> Storyboard -> later rendering timelines deterministic and auditable.

## Vertical isolation

Generic examples live under:

`extensions/content_studio/examples/`

The puppy storyboard lives under:

`verticals/kids_puppies/storyboards/`

The reusable Core contains no Toby/Luna defaults, kids-specific camera language,
or MoneyPrinterTurbo/provider configuration.

## Safety boundary

Storyboard may preserve continuity and age-appropriate decisions supplied by a
vertical, but dedicated Kids Safety remains a later independent gate. No storyboard
may bypass Safety + QA + Human Review before publication.

## ADR assessment

No new ADR is required. The design continues ADR-0001/0002/0003 and the canonical
contracts established in Sprints 1-3.
