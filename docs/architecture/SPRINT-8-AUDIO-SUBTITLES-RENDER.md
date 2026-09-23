# Sprint 8 — Audio, Subtitles and Final Render

## Objective

Assemble accepted visual assets into a narration-led final video while reusing
MoneyPrinterTurbo voice, subtitle and render services behind the anti-corruption
layer.

Publication is explicitly outside this Sprint.

## Core contracts

### MediaAssemblyPlan

Defines the complete final-media intent:

- project/story/episode/assembly IDs
- narration script and language
- voice name/rate/volume
- ordered visual URIs, kinds and durations
- aspect ratio and resolution
- subtitle enablement/mode/style
- render fit/transition settings
- output URI

Visual kinds are explicit (`image` or `video`) so adapters do not infer media type
from filenames. Reusing the same visual URI in multiple shots is allowed.

### AudioArtifact / SubtitleArtifact / RenderArtifact

Canonical output artifacts containing provider/engine provenance and measurable
properties such as duration, cue count, dimensions and output URI.

### MediaAssemblyResult

Represents a complete assembly outcome.

A successful result requires audio and final video. If subtitles are enabled by
the plan, a SubtitleArtifact is mandatory.

### MediaAssembler

Provider-neutral protocol:

```python
estimate = assembler.estimate_cost_usd(plan)
result = assembler.assemble(plan)
```

`assemble_media(...)` performs fail-closed cost preflight before invoking the
adapter whenever `max_cost_usd` is supplied.

## Upstream flow

`build_media_assembly_plan(...)` accepts only a successful `ConsistencyReport`.

Rejected or failed visual consistency results cannot advance into final rendering.

Traceability:

```text
ConsistencyReport
      |
      v
MediaAssemblyPlan
      |
      v
MediaAssembler
  /      |       \
audio subtitles render
      |
      v
MediaAssemblyResult
```

## MoneyPrinterTurbo adapter

`extensions/mpt_adapter/media.py` implements `MPTMediaAssembler`.

It reuses real MPT services:

1. `voice.tts(...)`
2. `voice.create_subtitle(...)` using TTS timing data
3. `video.render_image_zoom_video(...)` for image visuals
4. `video.combine_videos(...)`
5. `video.generate_video(...)`

Using TTS timing avoids an unnecessary Whisper transcription pass when MPT already
has speech timing metadata.

### Fail-closed generation

External TTS generation is disabled by default.

```python
MPTMediaAssembler(allow_external_generation=False)
```

must be explicitly changed to `True` before invoking MPT TTS.

When a budget is supplied, assembly is blocked before the first external call if
the configured estimate is unknown or exceeds the budget.

## Render behavior

- visual ordering is sequential
- images are converted to short video clips using MPT
- video inputs are reused directly
- visual track length is combined against narration duration
- subtitles are optional
- final output resolution derives from the canonical aspect ratio
- background music is disabled in this Sprint's adapter path
- no cross-posting or publication service is invoked

## CI safety

All adapter tests monkeypatch:

- TTS
- subtitle creation
- image-to-video conversion
- video combining
- final render

CI does not contact TTS providers and does not execute expensive MoviePy/FFmpeg
render workloads.

## Vertical isolation

Generic example:

`extensions/content_studio/examples/generic_media_assembly_plan.json`

Kids-puppies example:

`verticals/kids_puppies/media/ep0002.media-plan.json`

Voice IDs in examples are placeholders and do not select a production provider.

## Safety boundary

Sprint 8 produces a render candidate only.

Kids Safety + Render QA + Human Review remain required before publication.

## ADR assessment

No new ADR is required. MPT-specific behavior remains inside the ADR-0003
anti-corruption layer.
