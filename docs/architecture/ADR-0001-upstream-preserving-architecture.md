# ADR-0001 — Upstream-Preserving Extension Architecture

## Status
Accepted

## Context
Content Studio AI is built on the fork `josebautista2020/MoneyPrinterTurbo`, whose upstream is `harry0703/MoneyPrinterTurbo`. Upstream evolves quickly, so extensive modifications to upstream code would increase merge conflicts, regression risk, and maintenance cost.

## Decision
Content Studio AI will minimize changes to upstream `app/` and place product-specific capabilities in additive areas such as `extensions/`, `verticals/`, `skills/`, `docs/architecture/`, and dedicated tests.

Changes to upstream-owned code require explicit justification and, when architectural, a new ADR.

## Consequences
- Upstream synchronization remains practical.
- Vertical logic cannot leak into reusable core code.
- Most platform evolution occurs through composition rather than invasive fork changes.
