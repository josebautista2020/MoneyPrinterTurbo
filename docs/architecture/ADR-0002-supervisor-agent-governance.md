# ADR-0002 — Supervisor Agent Governance

## Status
Accepted

## Context
Content Studio AI coordinates architecture, engineering, creative generation, safety, QA, publishing, analytics, and cost control. Independent agents must not alter global architecture or roadmap without coordination.

## Decision
A Supervisor Agent owns global project state, roadmap gates, delegation, verification, governance, and reporting.

Specialized agents execute bounded tasks. They cannot independently change sprint gates, canonical architecture, publishing policy, or the reusable-core/vertical boundary.

The operating loop is:

`OBSERVE -> PLAN -> DELEGATE -> EXECUTE -> VERIFY -> GOVERN -> UPDATE STATE -> REPORT`

## Consequences
- Decisions are traceable.
- Sprint transitions require evidence.
- Human review remains mandatory before publication.
- Agent autonomy is bounded by architecture and safety gates.
