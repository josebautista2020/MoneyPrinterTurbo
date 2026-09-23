"""Kids Safety + QA contracts, coverage and human-review gate tests."""

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
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
)
from extensions.content_studio.quality import (
    HumanReviewGate,
    QACheck,
    RenderQAPolicy,
    RenderQAReport,
    build_human_review_gate,
    evaluate_render_qa,
)
from extensions.content_studio.safety import (
    SafetyAssessment,
    SafetyFinding,
    SafetyPolicy,
    SafetyReviewRequest,
    SafetyReviewer,
    SafetyRule,
    TextRuleSafetyReviewer,
    evaluate_safety_coverage,
)
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def project() -> ProjectSpec:
    return ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))


def generic_policy() -> SafetyPolicy:
    return SafetyPolicy.from_json(
        _load(EXAMPLES / "generic_safety_policy.json")
    )


def qa_policy() -> RenderQAPolicy:
    return RenderQAPolicy.from_json(
        _load(EXAMPLES / "generic_render_qa_policy.json")
    )


def consistency_report() -> ConsistencyReport:
    visual = VisualArtifact(
        asset_id="asset-1",
        request_id="request-1",
        shot_id="shot-1",
        asset_kind="video",
        uri="/generated/visual.mp4",
        engine="fake",
        provider="fake",
        width=1080,
        height=1920,
        duration_seconds=70,
    )
    visual_result = VisualResult(
        request_id="request-1",
        engine="fake",
        success=True,
        artifacts=(visual,),
        cost_usd=0.0,
    )
    assessment = ConsistencyAssessment(
        request_id="request-1",
        evaluator="fake",
        identity_score=0.95,
        appearance_score=0.95,
        wardrobe_score=0.95,
        environment_score=0.95,
    )
    attempt = ConsistencyAttempt(1, visual_result, assessment)
    result = ConsistentVisualResult(
        request_id="request-1",
        accepted=True,
        attempts=(attempt,),
    )
    return ConsistencyReport(
        project_id="generic-demo",
        story_id="generic-story-2",
        episode_id="episode-2",
        results=(result,),
    )


def media_result(
    *,
    width: int = 1080,
    height: int = 1920,
    audio_duration: float = 70,
    video_duration: float = 70,
    publication_performed: bool = False,
) -> MediaAssemblyResult:
    audio = AudioArtifact(
        audio_id="audio-1",
        uri="/generated/audio.wav",
        duration_seconds=audio_duration,
        engine="fake-media",
        provider="fake",
    )
    subtitle = SubtitleArtifact(
        subtitle_id="sub-1",
        uri="/generated/subtitles.srt",
        format="srt",
        cue_count=5,
        engine="fake-media",
        provider="fake",
    )
    video = RenderArtifact(
        render_id="video-1",
        uri="/generated/final.mp4",
        engine="fake-media",
        provider="fake",
        width=width,
        height=height,
        duration_seconds=video_duration,
    )
    return MediaAssemblyResult(
        assembly_id="assembly-1",
        engine="fake-media",
        success=True,
        audio=audio,
        subtitle=subtitle,
        video=video,
        cost_usd=0.0,
        metadata={"publication_performed": publication_performed},
    )


def safe_request() -> SafetyReviewRequest:
    return SafetyReviewRequest(
        request_id="safety-1",
        project_id="generic-demo",
        episode_id="episode-2",
        script="A friendly guide explains a simple idea.",
        subtitle_text="A friendly guide explains a simple idea.",
        audio_uri="/generated/audio.wav",
        visual_uris=("/generated/final.mp4",),
    )


def test_text_preflight_is_explicitly_partial() -> None:
    reviewer = TextRuleSafetyReviewer()
    assessment = reviewer.review(safe_request(), generic_policy())

    assert isinstance(reviewer, SafetyReviewer)
    assert assessment.reviewed_modalities == ("script", "subtitle")
    assert assessment.metadata["preflight_only"] is True

    complete, missing = evaluate_safety_coverage(
        generic_policy(),
        (assessment,),
    )
    assert not complete
    assert missing == ("audio", "visual")


def test_text_preflight_detects_blocking_term() -> None:
    request = SafetyReviewRequest(
        request_id="safety-2",
        project_id="generic-demo",
        episode_id="episode-2",
        script="The scene contains explicit gore.",
    )
    assessment = TextRuleSafetyReviewer().review(
        request,
        generic_policy(),
    )

    assert assessment.has_blocking_findings
    assert assessment.findings[0].category == "graphic_violence"
    assert assessment.findings[0].severity == "block"


def test_full_safety_coverage_without_blockers_passes() -> None:
    text = TextRuleSafetyReviewer().review(
        safe_request(),
        generic_policy(),
    )
    multimodal = SafetyAssessment(
        request_id="safety-1",
        reviewer="human-multimodal-review",
        reviewed_modalities=("audio", "visual"),
    )

    complete, missing = evaluate_safety_coverage(
        generic_policy(),
        (text, multimodal),
    )

    assert complete
    assert missing == ()


def test_warning_does_not_equal_block() -> None:
    warning = SafetyFinding(
        finding_id="finding-1",
        category="frightening_content",
        severity="warning",
        modality="visual",
        evidence="reviewer noticed a mildly spooky moment",
    )
    assessment = SafetyAssessment(
        request_id="safety-1",
        reviewer="reviewer",
        reviewed_modalities=("script", "subtitle", "audio", "visual"),
        findings=(warning,),
    )

    assert not assessment.has_blocking_findings
    complete, missing = evaluate_safety_coverage(
        generic_policy(),
        (assessment,),
    )
    assert complete
    assert missing == ()


def test_render_qa_passes_expected_candidate() -> None:
    report = evaluate_render_qa(
        project(),
        media_result(),
        consistency_report(),
        qa_policy(),
    )

    assert report.passed
    assert all(check.passed for check in report.checks)
    assert {check.check_id for check in report.checks} >= {
        "media-success",
        "consistency",
        "audio",
        "subtitles",
        "resolution",
        "duration",
        "audio-video-sync",
        "publication-not-performed",
    }


def test_render_qa_fails_wrong_resolution_and_sync() -> None:
    report = evaluate_render_qa(
        project(),
        media_result(
            width=1920,
            height=1080,
            audio_duration=70,
            video_duration=75,
        ),
        consistency_report(),
        RenderQAPolicy(
            minimum_duration_seconds=5,
            maximum_duration_seconds=120,
            duration_tolerance_seconds=1,
        ),
    )
    checks = {check.check_id: check.passed for check in report.checks}

    assert not report.passed
    assert checks["resolution"] is False
    assert checks["audio-video-sync"] is False


def test_render_qa_rejects_candidate_already_published() -> None:
    report = evaluate_render_qa(
        project(),
        media_result(publication_performed=True),
        consistency_report(),
        qa_policy(),
    )
    checks = {check.check_id: check.passed for check in report.checks}

    assert not report.passed
    assert checks["publication-not-performed"] is False


def test_human_review_gate_never_allows_publication_automatically() -> None:
    text = TextRuleSafetyReviewer().review(
        safe_request(),
        generic_policy(),
    )
    multimodal = SafetyAssessment(
        request_id="safety-1",
        reviewer="human-multimodal-review",
        reviewed_modalities=("audio", "visual"),
    )
    render_qa = evaluate_render_qa(
        project(),
        media_result(),
        consistency_report(),
        qa_policy(),
    )

    gate = build_human_review_gate(
        "generic-demo",
        "episode-2",
        generic_policy(),
        (text, multimodal),
        render_qa,
    )

    assert gate.safety_complete
    assert not gate.safety_blocked
    assert gate.render_qa_passed
    assert gate.eligible_for_human_review
    assert gate.publication_allowed is False
    assert gate.metadata["human_approval_required"] is True


def test_blocking_safety_finding_blocks_human_review_eligibility() -> None:
    blocking = SafetyAssessment(
        request_id="safety-1",
        reviewer="full-reviewer",
        reviewed_modalities=("script", "subtitle", "audio", "visual"),
        findings=(
            SafetyFinding(
                finding_id="finding-1",
                category="graphic_violence",
                severity="block",
                modality="visual",
                evidence="graphic content detected",
            ),
        ),
    )
    render_qa = evaluate_render_qa(
        project(),
        media_result(),
        consistency_report(),
        qa_policy(),
    )

    gate = build_human_review_gate(
        "generic-demo",
        "episode-2",
        generic_policy(),
        (blocking,),
        render_qa,
    )

    assert gate.safety_complete is False
    assert gate.safety_blocked
    assert not gate.eligible_for_human_review


def test_human_review_gate_cannot_be_constructed_as_published() -> None:
    with pytest.raises(DomainValidationError, match="must remain False"):
        HumanReviewGate(
            project_id="generic-demo",
            episode_id="episode-2",
            safety_complete=True,
            safety_blocked=False,
            render_qa_passed=True,
            eligible_for_human_review=True,
            publication_allowed=True,
        )


@pytest.mark.parametrize(
    "contract_type",
    [
        SafetyRule,
        SafetyPolicy,
        SafetyReviewRequest,
        SafetyFinding,
        SafetyAssessment,
        RenderQAPolicy,
        QACheck,
        RenderQAReport,
        HumanReviewGate,
    ],
)
def test_safety_qa_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_safety_and_quality_core_have_no_provider_or_vertical_imports() -> None:
    forbidden = (
        "app",
        "openai",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
    )
    violations = []

    for filename in ("safety.py", "quality.py"):
        path = REPO_ROOT / "extensions" / "content_studio" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
                    violations.append((filename, module))

    assert not violations


def test_kids_puppies_safety_and_qa_policies_are_valid() -> None:
    safety = SafetyPolicy.from_json(
        _load(KIDS / "safety" / "policy.json")
    )
    qa = RenderQAPolicy.from_json(
        _load(KIDS / "safety" / "render_qa_policy.json")
    )

    assert safety.audience_min_age == 4
    assert safety.audience_max_age == 9
    assert safety.metadata["human_review_required"] is True
    assert qa.minimum_duration_seconds == pytest.approx(55)
    assert qa.maximum_duration_seconds == pytest.approx(80)
    assert qa.require_consistency_pass


def test_generic_safety_examples_contain_no_vertical_defaults() -> None:
    content = _load(EXAMPLES / "generic_safety_policy.json").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
