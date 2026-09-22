# Sprint 1 — Canonical Domain Model

## Objective

Define provider-neutral, vertical-agnostic contracts that describe a Content Studio
project before any execution engine is selected.

The canonical contracts are:

- `ProjectSpec`
- `EpisodeSpec`
- `CharacterSpec`
- `SceneSpec`

They live under `extensions/content_studio/` and must never import MoneyPrinterTurbo
`app.*`, `extensions.mpt_adapter`, or any vertical.

## Schema version

The initial canonical schema version is `1.0.0`.

Serialized payloads must explicitly contain `schema_version`. Missing or unsupported
versions are rejected instead of being guessed. Unknown fields are rejected so that
forward-incompatible payloads fail visibly.

## Identity and references

### ProjectSpec

Owns:

- `project_id`
- language
- target platforms
- aspect ratio
- resolution
- project characters
- project episodes

Every episode embedded in a project must reference the same `project_id`.

### EpisodeSpec

Owns:

- `episode_id`
- `project_id`
- language
- target duration
- declared `character_ids`
- ordered scenes

Scene order values must be unique and contiguous starting at 1.

Every character referenced by a scene must first be declared by the episode.

### CharacterSpec

Defines reusable identity, description, visual traits, personality traits and an
optional provider-neutral voice hint. It contains no provider model names or engine
configuration.

### SceneSpec

Defines an independently regenerable scene using:

- location
- action
- duration
- character references
- optional dialogue/camera/emotion/transition

It contains no MoneyPrinterTurbo parameters.

## Serialization

Contracts support:

```python
payload = project.to_dict()
encoded = project.to_json()
restored = ProjectSpec.from_json(encoded)
schema = ProjectSpec.json_schema()
```

Metadata is allowed only when it remains JSON-compatible.

## JSON Schema

`extensions/content_studio/schemas.py` exposes Draft 2020-12 compatible,
versioned schemas for all four contracts. Runtime contract validation remains the
authoritative cross-reference validator because JSON Schema alone does not express
all project/episode/scene reference invariants cleanly.

## Vertical isolation

Generic examples belong under:

`extensions/content_studio/examples/`

Vertical examples belong under:

`verticals/<vertical>/examples/`

The kids-puppies example may reference Toby, Luna and vertical-specific educational
content. None of those values are defaults in the Core.

## Architecture decision

No new ADR is required for Sprint 1. The implementation follows ADR-0001
(upstream-preserving extension architecture) and ADR-0003 (composition over fork
modification). If later schema evolution introduces compatibility or migration
semantics beyond explicit semantic versioning, that change requires a new ADR.
