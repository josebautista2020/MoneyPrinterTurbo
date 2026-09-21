# ADR-0003 — Composition over Fork Modification

## Status
Accepted

## Context
MoneyPrinterTurbo already provides substantial generation, TTS, subtitle, media, rendering, and workflow capabilities. Reimplementing those capabilities in Content Studio AI would duplicate upstream behavior and increase maintenance cost.

## Decision
Content Studio AI will prefer composition over modification.

Provider-neutral domain and execution contracts will sit in Content Studio AI. Direct integration with MoneyPrinterTurbo is isolated behind `extensions/mpt_adapter/`, acting as an anti-corruption layer.

Only the MPT adapter may initially depend on MoneyPrinterTurbo implementation details. Other extensions depend on provider-neutral interfaces.

Publishing remains behind Content Studio safety, QA, and human-review gates even if upstream offers direct publishing.

## Consequences
- MoneyPrinterTurbo can be upgraded or replaced with lower impact.
- Content Studio domain models remain reusable.
- Upstream changes are localized to the adapter.
- Duplicate functionality is avoided unless explicitly justified by ADR.
