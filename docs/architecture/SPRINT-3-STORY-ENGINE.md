# Sprint 3 — Story Engine

## Objective

Create a provider-neutral Story Engine boundary that turns narrative intent plus
canonical project/bible context into a validated story plan and then into the
existing `EpisodeSpec` / `SceneSpec` model.

No LLM vendor, MoneyPrinterTurbo implementation detail, or vertical-specific
narrative rule belongs in the reusable Core.

## Core contracts

### StoryBrief

Defines the requested story scope:

- story/project/episode IDs
- title and premise
- language
- target duration
- allowed character IDs
- allowed location IDs
- tone hints
- optional lesson

It describes intent, not provider prompts.

### StoryBeat

Represents one ordered narrative beat with:

- stable beat ID and order
- narrative purpose
- summary/action
- duration
- canonical location ID
- canonical character references
- optional dialogue and emotion hints

Purposes such as hook/problem/resolution are values supplied by a vertical or
caller, not hard-coded enums in Core.

### StoryPlan

Contains one `StoryBrief` and ordered `StoryBeat` values.

It enforces:

- unique beat IDs
- contiguous order starting at 1
- no character reference outside the brief
- no location reference outside the brief

`StoryPlan.validate_context(...)` additionally verifies references against
`ProjectSpec`, `CharacterBible` and `UniverseBible`.

`StoryPlan.to_episode_spec()` compiles a validated narrative plan into the
canonical Sprint 1 episode/scene contracts without involving a rendering engine.

### StoryEngine

A provider-neutral Protocol:

```python
plan = engine.generate(brief, context)
```

The orchestration function `generate_story(...)` validates both input context
and engine output. An engine cannot silently return another brief or unknown
project references.

## Architecture

```text
ProjectSpec
   + CharacterBible
   + UniverseBible
          |
          v
     StoryContext
          |
StoryBrief -> StoryEngine -> StoryPlan
                         validation
                              |
                              v
                    EpisodeSpec / SceneSpec
                              |
                              v
                      later storyboard
```

## Vertical isolation

Generic examples live under:

`extensions/content_studio/examples/`

The puppy narrative example lives under:

`verticals/kids_puppies/stories/`

The reusable Core contains no Toby/Luna names, kids-specific beat sequence,
children's lesson defaults, or provider names.

## Safety boundary

Story Engine carries an optional lesson and respects declared universe/character
constraints, but it does not replace the dedicated Kids Safety Review gate planned
later in the roadmap. Vertical-specific child-safety constraints remain outside the
Core and final publication still requires Safety + QA + Human Review.

## ADR assessment

No new ADR is required. Sprint 3 follows ADR-0001 upstream-preserving architecture,
ADR-0002 Supervisor governance and ADR-0003 composition/anti-corruption boundaries.
A future provider-specific story generator must implement `StoryEngine` outside
the canonical domain layer.
