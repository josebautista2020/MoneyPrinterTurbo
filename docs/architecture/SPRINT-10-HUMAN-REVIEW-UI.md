# Sprint 10 — Human Review UI

## Objective

Provide a concrete human-review surface for Content Studio AI while preserving the
hard boundary between **approval** and **publication**.

The reviewer must be able to:

- preview the render candidate;
- inspect Safety findings and modality coverage;
- inspect deterministic Render QA checks;
- approve;
- reject;
- request regeneration of one shot;
- request regeneration of the whole episode;
- leave review notes;
- produce an auditable append-only decision trail.

No action in Sprint 10 publishes content.

## ReviewPackage

`ReviewPackage` is the canonical evidence bundle presented to a reviewer.

It contains:

- stable package/project/episode IDs;
- final render URI;
- Safety assessments;
- RenderQAReport;
- HumanReviewGate;
- known shot IDs;
- JSON-safe provenance metadata.

A package can be reviewed even when it is not eligible for approval. This allows a
human to inspect failures and choose rejection or regeneration.

Approval is validated separately and is allowed only when:

`HumanReviewGate.eligible_for_human_review == True`

## ReviewDecision

Supported actions:

- `approve`
- `reject`
- `regenerate_shot`
- `regenerate_episode`

Every decision requires:

- stable decision ID;
- package ID;
- reviewer ID;
- timezone-aware decision timestamp;
- non-empty reviewer comments.

`regenerate_shot` requires a target shot that exists in the ReviewPackage.

Other actions cannot carry a target shot.

A ReviewDecision deliberately has **no publication field or publishing action**.

## ReviewAuditTrail

`ReviewAuditTrail` is an ordered logical history of decisions for one package.

Properties:

- decision IDs are unique;
- package IDs must match;
- decision timestamps must remain chronological;
- append creates a new logical trail;
- latest decision is directly addressable.

## Local append-only store

`JsonlReviewDecisionStore` lives under:

`extensions/human_review_ui/store.py`

Each package is persisted as an append-only JSONL file.

Default directory:

`output/content_studio/review_audit/`

Override with:

`CONTENT_STUDIO_REVIEW_LOG_DIR`

The store:

- reloads and validates every record;
- rejects duplicate decision IDs;
- rejects package mismatches;
- flushes and fsyncs each append.

The local store is intentionally simple and single-node. A future production
workflow may replace it with a database-backed ReviewDecisionStore without changing
the Core contract.

## Streamlit Human Review UI

Standalone application:

`extensions/human_review_ui/app.py`

Run:

```bash
uv run streamlit run extensions/human_review_ui/app.py
```

The UI loads a ReviewPackage JSON and displays:

- Safety/QA status cards;
- render preview using `st.video`;
- QA check table;
- Safety findings;
- reviewed Safety modalities;
- reviewer ID and notes;
- shot selector;
- decision buttons;
- current audit trail.

The Approve button is disabled when the package is not eligible for human review.

## Regeneration semantics

Sprint 10 records regeneration requests; it does not silently execute them.

This is intentional:

```text
Human Review UI
      |
      v
ReviewDecision(action=regenerate_*)
      |
      v
Audit Trail
      |
      v
Future orchestration consumes decision
      |
      v
Prompt / Visual / Render regeneration
```

The reviewer remains the source of the regeneration decision.

## Publication boundary

Sprint 10 does not import or invoke:

- MoneyPrinterTurbo cross-posting;
- upload-post;
- publishing adapters;
- platform APIs.

Even an approved ReviewDecision only means:

`human_review_approved = True`

It does **not** mean:

`published = True`

A separate governed publishing gateway is required.

## Architecture

```text
SafetyAssessment(s) ----\
RenderQAReport ----------+----> ReviewPackage
HumanReviewGate ---------+          |
Consistency shot IDs ----/          v
                              Human Review UI
                           /       |       |       \
                     approve   reject  regen shot  regen episode
                           \       |       |       /
                                   v
                            ReviewDecision
                                   |
                                   v
                         ReviewDecisionStore
                                   |
                                   v
                          ReviewAuditTrail

Publishing: NOT CONNECTED
```

## Vertical isolation

Generic review package:

`extensions/content_studio/examples/generic_review_package.json`

Kids-puppies package:

`verticals/kids_puppies/review/ep0002.review-package.json`

Toby/Luna and child-specific evidence stay outside reusable Core defaults.

## CI safety

Sprint 10 tests are local/offline.

CI does not:

- publish;
- call provider APIs;
- invoke MoneyPrinterTurbo generation;
- invoke upload-post.

## ADR assessment

No new ADR is required. Sprint 10 implements the human-review requirement already
established by existing governance decisions.
