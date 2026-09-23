"""Media assembly core contract, traceability and budget tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.consistency import (
    ConsistencyAssessment,
    ConsistencyAttempt,
    ConsistencyReport,
    ConsistentVisualResult,
)
from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.media import (
    AudioArtifact,
    MediaAssembler,
    MediaAssemblyPlan,
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
    assemble_media,
    build_media_assembly_plan,
)
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_project() -> ProjectSpec:
    return ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))


def accepted_report() -> ConsistencyReport:
    results = []
    for idx, (kind, duration) in enumerate(
        (("image", 5.0), ("video", 7.0)),
        start=1,
    ):
        request_id = f"shot-{idx}"
        artifact = VisualArtifact(
            asset_id=f"asset-{idx}",
            request_id=request_id,
            shot_id=request_id,
            asset_kind=kind,
            uri=f"/generated/visual-{idx}.{'png' if kind == 'image' else 'mp4'}",
            engine="fake-reference",
            provider="fake",
            width=1080,
            height=1920,
            duration_seconds=duration,
        )
        visual = VisualResult(
            request_id=request_id,
            engine="fake-reference",
            success=True,
            artifacts=(artifact,),
            cost_usd=0.01,
        )
        assessment = ConsistencyAssessment(
            request_id=request_id,
            evaluator="fake-evaluator",
            identity_score=0.95,
            appearance_score=0.95,
            wardrobe_score=0.95,
            environment_score=0.95,
        )
        attempt = ConsistencyAttempt(1, visual, assessment)
        results.append(
            ConsistentVisualResult(
                request_id=request_id,
                accepted=True,
                attempts=(attempt,),
            )
        )
    return ConsistencyReport(
        project_id="generic-demo",
        story_id="generic-story-2",
        episode_id="episode-2",
        results=tuple(results),
    )


def build_plan() -> MediaAssemblyPlan:
    return build_media_assembly_plan(
        generic_project(),
        accepted_report(),
        assembly_id="assembly-1",
        script="A short narration for the generic example.",
        language="en-US",
        voice_name="test-voice",
        output_uri="/generated/final.mp4",
    )


def test_build_media_plan_requires_accepted_consistency() -> None:
    plan = build_plan()

    assert plan.visual_uris == (
        "/generated/visual-1.png",
        "/generated/visual-2.mp4",
    )
    assert plan.visual_kinds == ("image", "video")
    assert plan.visual_durations_seconds == (5.0, 7.0)
    assert plan.aspect_ratio == "9:16"
    assert plan.resolution == "1080x1920"


def test_media_plan_allows_reused_visual_uri() -> None:
    plan = build_plan()
    duplicated = MediaAssemblyPlan(
        assembly_id=plan.assembly_id,
        project_id=plan.project_id,
        story_id=plan.story_id,
        episode_id=plan.episode_id,
        script=plan.script,
        language=plan.language,
        voice_name=plan.voice_name,
        visual_uris=("/same.png", "/same.png"),
        visual_kinds=("image", "image"),
        visual_durations_seconds=(5.0, 5.0),
        aspect_ratio=plan.aspect_ratio,
        resolution=plan.resolution,
        output_uri=plan.output_uri,
    )

    assert duplicated.visual_uris[0] == duplicated.visual_uris[1]


def test_media_plan_round_trip() -> None:
    plan = build_plan()
    restored = MediaAssemblyPlan.from_json(plan.to_json())

    assert restored == plan
    assert json.loads(plan.to_json())["schema_version"] == SCHEMA_VERSION


class _FakeAssembler:
    def __init__(self, estimate: float | None = 0.03) -> None:
        self.estimate = estimate
        self.calls = 0

    @property
    def engine_name(self) -> str:
        return "fake-media"

    def estimate_cost_usd(self, plan: MediaAssemblyPlan) -> float | None:
        del plan
        return self.estimate

    def assemble(self, plan: MediaAssemblyPlan) -> MediaAssemblyResult:
        self.calls += 1
        audio = AudioArtifact(
            audio_id="audio-1",
            uri="/generated/audio.wav",
            duration_seconds=12,
            engine=self.engine_name,
            provider="fake",
        )
        subtitle = (
            SubtitleArtifact(
                subtitle_id="sub-1",
                uri="/generated/subtitles.srt",
                format="srt",
                cue_count=2,
                engine=self.engine_name,
                provider="fake",
            )
            if plan.subtitle_enabled
            else None
        )
        video = RenderArtifact(
            render_id="video-1",
            uri=plan.output_uri,
            engine=self.engine_name,
            provider="fake",
            width=1080,
            height=1920,
            duration_seconds=12,
        )
        return MediaAssemblyResult(
            assembly_id=plan.assembly_id,
            engine=self.engine_name,
            success=True,
            audio=audio,
            subtitle=subtitle,
            video=video,
            cost_usd=self.estimate,
        )


def test_media_assembler_protocol_and_budgeted_success() -> None:
    assembler = _FakeAssembler(estimate=0.03)
    plan = build_plan()

    assert isinstance(assembler, MediaAssembler)

    result = assemble_media(assembler, plan, max_cost_usd=0.05)
    assert result.success
    assert result.cost_usd == pytest.approx(0.03)
    assert assembler.calls == 1


def test_media_budget_blocks_before_assembly() -> None:
    assembler = _FakeAssembler(estimate=0.10)

    with pytest.raises(DomainValidationError, match="exceeds budget"):
        assemble_media(assembler, build_plan(), max_cost_usd=0.05)

    assert assembler.calls == 0


def test_media_budget_rejects_unknown_cost_before_assembly() -> None:
    assembler = _FakeAssembler(estimate=None)

    with pytest.raises(DomainValidationError, match="cost estimate required"):
        assemble_media(assembler, build_plan(), max_cost_usd=1.0)

    assert assembler.calls == 0


def test_failed_consistency_report_cannot_be_rendered() -> None:
    report = accepted_report()
    bad_first = ConsistentVisualResult(
        request_id=report.results[0].request_id,
        accepted=False,
        attempts=report.results[0].attempts,
    )
    failed = ConsistencyReport(
        report.project_id,
        report.story_id,
        report.episode_id,
        (bad_first, *report.results[1:]),
    )

    with pytest.raises(DomainValidationError, match="rejected visual"):
        build_media_assembly_plan(
            generic_project(),
            failed,
            assembly_id="assembly-1",
            script="Test",
            language="en-US",
            voice_name="test-voice",
            output_uri="/generated/final.mp4",
        )


@pytest.mark.parametrize(
    "contract_type",
    [
        MediaAssemblyPlan,
        AudioArtifact,
        SubtitleArtifact,
        RenderArtifact,
        MediaAssemblyResult,
    ],
)
def test_media_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_media_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "media.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app",
        "openai",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
    )
    violations = []

    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

        for module in modules:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(module)

    assert not violations
