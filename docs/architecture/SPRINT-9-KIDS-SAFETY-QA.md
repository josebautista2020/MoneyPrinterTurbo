# Sprint 9 — Kids Safety + QA

## Objective

Create reusable safety and quality gates that prevent unsafe or technically invalid
content from advancing directly to publication.

Sprint 9 deliberately separates three concepts:

1. deterministic text preflight;
2. complete multimodal safety coverage;
3. deterministic render QA.

None of these automatically publishes content. The final outcome can only become
eligible for explicit human review.

## Safety Core

### SafetyRule

Versioned rule containing:

- stable rule ID
- category
- severity: `info`, `warning`, or `block`
- configured text terms
- human-readable description

Rules are policy data, not Core defaults.

### SafetyPolicy

Defines:

- target audience age range
- ordered policy rules
- safety modalities that must be reviewed

Default required modalities for the current workflow:

```text
script
subtitle
audio
visual
```

### SafetyReviewRequest

Carries script, subtitle text, audio URI and visual URIs to a safety reviewer.

### SafetyReviewer

Provider-neutral protocol. Future implementations may be:

- multimodal AI reviewers
- specialist third-party moderation
- human review systems
- mixed AI + human review

### TextRuleSafetyReviewer

A deterministic textual preflight only.

It can identify configured terms in script/subtitle text and generate findings, but
it explicitly marks itself as unable to review visual or audio content.

This reviewer must never be represented as a complete child-safety review.

### SafetyAssessment

Records:

- reviewer
- modalities actually reviewed
- findings
- provenance metadata

### Safety coverage

`evaluate_safety_coverage(...)` requires:

- all configured modalities covered across one or more assessments
- zero blocking findings

Warning findings can continue to human review but remain visible.

## Render QA

### RenderQAPolicy

Defines:

- minimum/maximum video duration
- audio/video duration tolerance
- audio requirement
- subtitle requirement
- consistency requirement

### evaluate_render_qa

Performs deterministic checks for:

- media assembly success
- character consistency success
- audio presence
- subtitle presence
- output resolution
- duration bounds
- audio/video duration synchronization
- confirmation that publication has not already happened

This is technical QA over known artifacts/metadata. It is not visual-semantic safety.

## Mandatory Human Review Gate

### HumanReviewGate

Combines:

- complete Safety coverage
- absence of blocking Safety findings
- passing RenderQAReport

A passing gate sets:

```text
eligible_for_human_review = True
publication_allowed = False
```

`publication_allowed=True` is rejected by the Core contract.

Therefore Sprint 9 cannot bypass the human approval boundary.

## Kids-puppies policy

Vertical-specific policies live under:

`verticals/kids_puppies/safety/`

The current child audience is 4–9.

Configured blocking preflight categories include:

- graphic violence
- sexual content
- self-harm
- substances
- gambling

Configured warning/escalation categories include:

- frightening content
- dangerous imitation
- bullying

These keyword rules are deliberately conservative and non-exhaustive. A clean text
preflight does not prove the episode is safe.

The kids-puppies Render QA target keeps the short-form episode inside 55–80 seconds,
requires narration/subtitles and requires the Character Consistency gate to pass.

## Architecture

```text
Script / Subtitle / Audio / Visual
              |
              v
       SafetyReviewer(s)
              |
              v
      SafetyAssessment(s)
              |
              +----> coverage complete?
              |          |
              |          no -> BLOCK
              v
      blocking finding?
          |        |
         yes       no
          |        |
        BLOCK      v
              RenderQAReport
                    |
                    v
             all QA checks pass?
                |          |
               no          yes
                |           |
              BLOCK         v
                      HumanReviewGate
                            |
                            v
                 eligible_for_human_review
                            |
                            v
                    HUMAN DECISION
                            |
                    publication remains
                    outside Sprint 9
```

## CI safety

Sprint 9 tests are deterministic and offline. No provider API is needed.

## Vertical isolation

Generic policy examples live under:

`extensions/content_studio/examples/`

Kids-specific safety rules live only under:

`verticals/kids_puppies/safety/`

## ADR assessment

No new ADR is required. Sprint 9 follows the existing governance rule that human
review is mandatory before publication.
