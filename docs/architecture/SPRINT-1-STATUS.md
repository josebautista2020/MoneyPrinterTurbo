# Sprint 1 Gate Status

Last supervisor update: 2026-09-21

| Gate | Status | Evidence |
| --- | --- | --- |
| S1.1 | PASS | `feat/sprint-1-domain-model` exists and is based on merged Sprint 0 `main` |
| S1.2 | IN_PROGRESS | canonical contracts implemented; awaiting CI verification |
| S1.3 | IN_PROGRESS | explicit validation, JSON round-trip and versioned JSON Schemas implemented; awaiting CI |
| S1.4 | IN_PROGRESS | project/episode/scene/character reference invariants implemented; awaiting CI |
| S1.5 | IN_PROGRESS | unit/schema/round-trip tests committed; awaiting CI |
| S1.6 | PASS | generic Core example and isolated kids-puppies example committed |
| S1.7 | IN_PROGRESS | domain provider/vertical boundary test committed; awaiting CI |
| S1.8 | PENDING | full GitHub Actions CI and upstream baseline not yet executed for Sprint 1 |
| S1.9 | PASS | Sprint 1 domain-model design documented; no new ADR required |
| S1.10 | PENDING | Sprint 1 PR not yet opened |

## Current implementation

The Core now defines `ProjectSpec`, `EpisodeSpec`, `CharacterSpec` and
`SceneSpec` without importing MoneyPrinterTurbo or vertical code.

Schema version: `1.0.0`.

The Supervisor must not promote S1.2-S1.5 or S1.7 to PASS until execution evidence
exists. Sprint 2 remains blocked.
