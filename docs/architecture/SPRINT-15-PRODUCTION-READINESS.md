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
Do not change the committed example catalog to refer to private local assets;
use a local, uncommitted catalog and runtime profile for the pilot.

An operator can validate those files offline, without a credential or a paid
call, from the repository root:

```bash
uv run python -m extensions.operator_console.cli preflight-references \
  --plan <visual-plan.json> --catalog <local-reference-catalog.json>
```

This validation does not establish image ownership or artistic quality. Those
require an explicit asset review and the Human Review gate on the resulting
episode. No provider call or publication is part of this implementation.

## Media preflight

Before invoking TTS, the MPT media adapter verifies that every visual input
exists and is nonempty. Image inputs must also decode successfully. A missing
visual late in the episode now fails with `provider_called=false` and zero
reported cost, before narration starts. This preflight does not verify video
decoding or artistic quality.

The committed Kids Puppies profile uses `kids-demo-voice`. It remains a
default-deny example; enabling its media provider for external calls with that
placeholder voice is rejected by the runtime registry. An operator must
select a real configured MPT voice for the pilot. Offline capability inspection
of the guarded example remains available.
