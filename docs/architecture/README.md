# Content Studio AI Architecture

Content Studio AI extends MoneyPrinterTurbo while preserving upstream compatibility.

## Control plane

Supervisor Agent -> Architecture/Governance, Engineering, Creative, Safety, QA, Publishing, Analytics.

## Boundary rules

1. Reusable Content Studio capabilities are vertical-agnostic.
2. `verticals/kids_puppies` may consume reusable contracts; reusable code may not depend on the vertical.
3. MoneyPrinterTurbo integration is isolated behind an anti-corruption adapter.
4. Prefer composition over modifying upstream `app/` code.
5. Publishing always requires safety/QA gates and explicit human approval.
6. Significant architecture changes require an ADR.

## Sprint 0

The foundation branch is `feat/sprint-0-foundation`. Sprint 1 remains blocked until all Sprint 0 gates are verified.
