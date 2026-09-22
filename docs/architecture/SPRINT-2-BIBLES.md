# Sprint 2 — Character Bible + Universe Bible

## Objective

Add persistent, provider-neutral consistency contracts on top of the canonical
Sprint 1 domain model.

The bibles describe identity and world continuity. They do not describe provider
requests and they do not import MoneyPrinterTurbo.

## Contracts

### CharacterProfile

References one canonical `CharacterSpec.character_id` and adds persistence
constraints such as:

- aliases
- signature visual features
- wardrobe continuity
- personality notes
- voice consistency notes
- forbidden changes
- reference asset IDs
- JSON-safe metadata

It does not duplicate the full `CharacterSpec`.

### CharacterBible

A project-scoped collection of CharacterProfiles.

`validate_project(ProjectSpec)` requires exact coverage of characters declared by
the project. Unknown or missing character profiles fail validation.

Aliases are case-insensitive during resolution and cannot be ambiguous.

### LocationProfile

Defines a stable `location_id`, aliases, description, visual traits, ambience,
consistency rules, forbidden changes, reference asset IDs and metadata.

### UniverseBible

A project-scoped collection of LocationProfiles plus provider-neutral world rules.

`validate_project(ProjectSpec)` verifies that every `SceneSpec.location` can be
resolved by canonical location ID or alias.

Location aliases are case-insensitive and ambiguity is rejected.

## Relationship to Sprint 1

```text
ProjectSpec
  ├── CharacterSpec[] <── CharacterBible / CharacterProfile
  └── EpisodeSpec[]
       └── SceneSpec.location <── UniverseBible / LocationProfile
```

The bibles reference canonical IDs rather than replacing canonical specs.

## Serialization and schemas

All four Bible contracts use the existing canonical `SCHEMA_VERSION = 1.0.0`,
support JSON round-trip behavior through `JsonContract`, and expose JSON Schemas
through the existing `schema_for()` registry.

No new schema framework or third-party dependency is introduced.

## Vertical isolation

Generic examples live under:

`extensions/content_studio/examples/`

Kids-puppies examples live under:

`verticals/kids_puppies/bibles/`

Toby, Luna, the park, children's safety-specific world rules, and any other
vertical concepts are never defaults in the reusable Core.

## Architecture decision

No new ADR is required. Sprint 2 follows ADR-0001 and ADR-0003:

- additive extension architecture
- composition over upstream modification
- provider-neutral Core
- MoneyPrinterTurbo behind `mpt_adapter`

A future decision to make Bible contracts provider-specific, model-specific, or
asset-store-specific would require a new ADR.
