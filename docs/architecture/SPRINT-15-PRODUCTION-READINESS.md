# Sprint 15 — Production Readiness

## Objective

Make a single Kids Puppies episode eligible for a controlled provider-backed
pilot. Passing offline CI is not evidence that a provider has generated an
episode or that the episode may be published.

## Gates

| Gate | Acceptance criterion |
| --- | --- |
| S15.1 | Dedicated branch from the merged Sprint 14 commit |
| S15.2 | All referenced images are materialized, rights reviewed, and traceable to their approved character/location |
| S15.3 | Validate the entire reference batch before the first paid request |
| S15.4 | Confirm provider and voice/model configuration against available capabilities and budget |
| S15.5 | Run one controlled episode with explicit external/paid authorization and a recorded cost ceiling |
| S15.6 | Validate real outputs for identity continuity, audio, subtitles, render integrity, and child safety |
| S15.7 | Obtain an audited human decision on the actual render |
| S15.8 | Complete a governed publish dry-run against that approved render; keep live publication separately authorized |
| S15.9 | CI and operational evidence tied to exact commit and episode artifacts |
| S15.10 | Reviewable PR with traceability, risks, and no automatic merge |

## First implementation: reference-image preflight

The `openai-reference-image` runtime now validates **every** referenced asset
in the plan before it sends any generation request. It rejects:

- `asset://` placeholders or catalogs marked as placeholders;
- missing, empty, oversized, corrupt, or mislabeled local images;
- unsupported media types and URI schemes that cannot be verified offline;
- unresolved reference IDs and mismatched project IDs.

For the first pilot, references must be local PNG, JPEG or WebP files. A local
path is interpreted relative to the process working directory, just as in the
adapter. `file://` paths are also accepted. Remote HTTPS and OpenAI file IDs
need a separate verification mechanism before they can be used for a paid run.
Private local assets must use an uncommitted catalog. The Kids Puppies pilot
instead uses approved project-original assets committed under the vertical;
its catalog records provenance, dimensions, review status, and SHA-256.

An operator can validate those files offline, without a credential or a paid
call, from the repository root:

```bash
uv run python -m extensions.operator_console.cli preflight-references \
  --plan <visual-plan.json> --catalog <local-reference-catalog.json> \
  --character-bible <character-bible.json> \
  --universe-bible <universe-bible.json>
```

Both Bible arguments are supplied together to bind the current character and
location reference IDs. An unbound plan with zero references fails explicitly.
The runtime reference-image executor applies the same binding to workflow
artifacts before its complete-batch preflight. A zero-reference PASS is not
evidence of readiness.

This validation does not establish image ownership or artistic quality. Those
require an explicit asset review and the Human Review gate on the resulting
episode. No provider call or publication is part of this implementation.

## Approved pilot references

The Sprint 15 asset review selected Toby, Parque, and the upright-ear Luna
variant. Upright ears give Luna a silhouette that remains recognizable next to
Toby's floppy ears. The rejected Luna variant is not committed. Character
Bibles now treat those ear shapes as identity constraints, while the reference
catalog provides durable repository paths and content hashes.

## Media preflight

Before invoking TTS, the MPT media adapter verifies that every visual input
exists and is nonempty. Image inputs must also decode successfully. A missing
visual late in the episode now fails with `provider_called=false` and zero
reported cost, before narration starts. This preflight does not verify video
decoding or artistic quality.

The Kids Puppies profile uses the bundled Colombian Spanish voice
`es-CO-SalomeNeural-Female`. Offline capability inspection of the guarded
profile remains available.

## Pilot provider configuration

The guarded pilot profile now selects:

- OpenAI Responses model `gpt-6-astra`;
- image model `gpt-image-2.5-sunburst`;
- explicit `low` quality and `1024x1536` output;
- `env:OPENAI_API_KEY` as the only visual-provider secret reference;
- Microsoft Edge TTS voice `es-CO-SalomeNeural-Female`;
- a $5 maximum visual-stage and total pilot ceiling.

The committed profile remains default-deny: external and paid calls are false,
and live publication is false. The voice is present in MPT's bundled voice
catalog. The image model and explicit quality/size settings were verified
against the official OpenAI image-generation guide on 2026-09-26. S15.4 passed
after GitHub Actions confirmed the repository secret and authenticated access
to the selected model through a metadata-only smoke request. Secret values must
never be committed.

## Guarded ep0002 pilot workflow

The manual GitHub Actions workflow
`.github/workflows/kids-puppies-ep0002-pilot.yml` prepares the ep0002 state
from committed project assets, applies deterministic stages through prompts,
performs the reference preflight, creates a temporary runtime profile, and only
then runs the visual provider.

The workflow requires the operator to type exactly:

```text
RUN_EP0002_PAID_UNDER_5_USD
```

The `max_cost_usd` input must be greater than zero and no more than 5. The
temporary profile exists only inside the Actions runner and flips external and
paid calls on for the visual stage only. The committed profile remains
default-deny. The workflow uploads generated visual artifacts and operator
state for audit. It does not perform live publication or approve the episode.

## Guarded ep0002 pilot evidence

S15.5 passed on 2026-09-26 through GitHub Actions run `36242164777` for commit
`1fae2d766e95865a8ca3ad7c63c4e4d19b08e7f9`.

- Confirmation phrase: `RUN_EP0002_PAID_UNDER_5_USD`.
- Maximum configured pilot cost: `$5.00`.
- Actual recorded visual-stage estimate: `$0.80`.
- Visual requests completed: 8 of 8.
- Provider: OpenAI `openai-reference-image` with `gpt-image-2.5-sunburst`, low quality, `1024x1536`.
- Artifact: `kids-puppies-ep0002-guarded-visual-pilot`, artifact ID `10905962676`, SHA-256 digest `4c730ab8bf82e0cb1a0ee3b844519930ad84ab2eb57b0d5c4637d2218052a138`, retained until 2026-10-10.
- Workflow summary after the pilot: `next_stage=consistency`, `complete=false`, `live_publication_enabled=false`.

The pilot proves paid visual generation under the approved budget. It does not
prove final episode readiness. S15.6 must review the retained visual artifacts
for identity continuity, render integrity, audio/subtitle readiness, and child
safety before any human approval or publish dry-run.
