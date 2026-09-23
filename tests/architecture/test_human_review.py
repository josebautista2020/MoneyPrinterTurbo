"""Human Review contracts, audit trail and UI boundary tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from extensions.content_studio.consistency import (
    ConsistencyAssessment,
    ConsistencyAttempt,
    ConsistencyReport,
    ConsistentVisualResult,
)
from extensions.content_studio.domain import DomainValidationError, SCHEMA_VERSION
from extensions.content_studio.media import (
    AudioArtifact,
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
)
from extensions.content_studio.quality import (
    HumanReviewGate,
    QACheck,
    RenderQAReport,
)
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewDecisionStore,
    ReviewPackage,
    build_review_package,
    validate_review_decision,
)
from extensions.content_studio.safety import SafetyAssessment
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualResult,
)
from extensions.human_review_ui.store import JsonlReviewDecisionStore

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_package() -> ReviewPackage:
    return ReviewPackage.from_json(
        _load(EXAMPLES / "generic_review_package.json")
    )


def decision(
    *,
    action: str = "approve",
    decision_id: str = "decision-1",
    decided_at: str = "2026-09-23T20:00:00+00:00",
    target_shot_id: str | None = None,
) -> ReviewDecision:
    return ReviewDecision(
        decision_id=decision_id,
        package_id="generic-review-episode-2",
        reviewer_id="reviewer-1",
        action=action,
        decided_at=decided_at,
        comments="Reviewed Safety and QA evidence.",
        target_shot_id=target_shot_id,
    )


def test_generic_review_package_round_trip() -> None:
    package = generic_package()
    restored = ReviewPackage.from_json(package.to_json())

    assert restored == package
    assert package.gate.eligible_for_human_review
    assert package.gate.publication_allowed is False
    assert json.loads(package.to_json())["schema_version"] == SCHEMA_VERSION


def test_approve_is_valid_only_for_eligible_package() -> None:
    package = generic_package()
    approved = decision(action="approve")

    validate_review_decision(package, approved)

    blocked_gate = replace(
        package.gate,
        eligible_for_human_review=False,
        render_qa_passed=False,
    )
    blocked = replace(package, gate=blocked_gate)

    with pytest.raises(DomainValidationError, match="not eligible"):
        validate_review_decision(blocked, approved)


def test_approval_has_no_publication_capability() -> None:
    approved = decision(action="approve")
    payload = approved.to_dict()

    assert approved.approved
    assert "publication_allowed" not in payload
    assert "publish" not in json.dumps(payload).lower()


def test_regenerate_shot_requires_existing_shot() -> None:
    package = generic_package()

    valid = decision(
        action="regenerate_shot",
        target_shot_id="shot-2",
    )
    validate_review_decision(package, valid)
    assert valid.requests_regeneration

    invalid = decision(
        action="regenerate_shot",
        decision_id="decision-2",
        target_shot_id="unknown-shot",
    )
    with pytest.raises(DomainValidationError, match="does not exist"):
        validate_review_decision(package, invalid)


def test_regenerate_episode_must_not_include_target_shot() -> None:
    regen = decision(action="regenerate_episode")
    assert regen.requests_regeneration

    with pytest.raises(DomainValidationError, match="only valid"):
        decision(
            action="regenerate_episode",
            decision_id="decision-2",
            target_shot_id="shot-1",
        )


def test_decision_timestamp_requires_timezone() -> None:
    with pytest.raises(DomainValidationError, match="include a timezone"):
        decision(decided_at="2026-09-23T20:00:00")


def test_audit_trail_is_ordered_and_append_only() -> None:
    first = decision(
        action="reject",
        decision_id="decision-1",
        decided_at="2026-09-23T20:00:00+00:00",
    )
    second = decision(
        action="approve",
        decision_id="decision-2",
        decided_at="2026-09-23T20:05:00+00:00",
    )
    trail = ReviewAuditTrail(
        package_id="generic-review-episode-2",
        decisions=(first,),
    ).append(second)

    assert trail.latest == second
    assert trail.decisions == (first, second)

    older = decision(
        action="reject",
        decision_id="decision-3",
        decided_at="2026-09-23T19:00:00+00:00",
    )
    with pytest.raises(DomainValidationError, match="ordered"):
        trail.append(older)


def test_jsonl_review_store_persists_and_reloads(tmp_path) -> None:
    store = JsonlReviewDecisionStore(tmp_path)
    assert isinstance(store, ReviewDecisionStore)

    first = decision(action="reject", decision_id="decision-1")
    second = decision(
        action="regenerate_shot",
        decision_id="decision-2",
        decided_at="2026-09-23T20:01:00+00:00",
        target_shot_id="shot-1",
    )

    store.append(first)
    trail = store.append(second)
    reloaded = store.list("generic-review-episode-2")

    assert trail.decisions == reloaded.decisions
    assert reloaded.latest == second

    lines = (
        tmp_path / "generic-review-episode-2.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_jsonl_store_rejects_duplicate_decision_id(tmp_path) -> None:
    store = JsonlReviewDecisionStore(tmp_path)
    item = decision()

    store.append(item)
    with pytest.raises(DomainValidationError, match="duplicate decision_id"):
        store.append(item)


def _consistency_report() -> ConsistencyReport:
    artifact = VisualArtifact(
        asset_id="asset-1",
        request_id="shot-1",
        shot_id="shot-1",
        asset_kind="video",
        uri="/generated/shot-1.mp4",
        engine="fake",
        provider="fake",
        width=1080,
        height=1920,
        duration_seconds=70,
    )
    visual = VisualResult(
        request_id="shot-1",
        engine="fake",
        success=True,
        artifacts=(artifact,),
        cost_usd=0.0,
    )
    assessment = ConsistencyAssessment(
        request_id="shot-1",
        evaluator="fake",
        identity_score=0.95,
        appearance_score=0.95,
        wardrobe_score=0.95,
        environment_score=0.95,
    )
    return ConsistencyReport(
        project_id="generic-demo",
        story_id="generic-story-2",
        episode_id="episode-2",
        results=(
            ConsistentVisualResult(
                request_id="shot-1",
                accepted=True,
                attempts=(ConsistencyAttempt(1, visual, assessment),),
            ),
        ),
    )


def _media_result() -> MediaAssemblyResult:
    return MediaAssemblyResult(
        assembly_id="assembly-1",
        engine="fake-media",
        success=True,
        audio=AudioArtifact(
            audio_id="audio-1",
            uri="/generated/audio.wav",
            duration_seconds=70,
            engine="fake-media",
            provider="fake",
        ),
        subtitle=SubtitleArtifact(
            subtitle_id="subtitle-1",
            uri="/generated/subtitles.srt",
            format="srt",
            cue_count=5,
            engine="fake-media",
            provider="fake",
        ),
        video=RenderArtifact(
            render_id="video-1",
            uri="/generated/final.mp4",
            engine="fake-media",
            provider="fake",
            width=1080,
            height=1920,
            duration_seconds=70,
        ),
        cost_usd=0.0,
        metadata={"publication_performed": False},
    )


def _qa() -> RenderQAReport:
    return RenderQAReport(
        project_id="generic-demo",
        episode_id="episode-2",
        checks=(
            QACheck("media-success", True, "media is valid"),
            QACheck("publication-not-performed", True, "not published"),
        ),
    )


def _gate() -> HumanReviewGate:
    return HumanReviewGate(
        project_id="generic-demo",
        episode_id="episode-2",
        safety_complete=True,
        safety_blocked=False,
        render_qa_passed=True,
        eligible_for_human_review=True,
        publication_allowed=False,
    )


def test_build_review_package_from_pipeline_evidence() -> None:
    package = build_review_package(
        package_id="review-1",
        media=_media_result(),
        consistency=_consistency_report(),
        safety_assessments=(
            SafetyAssessment(
                request_id="safety-1",
                reviewer="full-reviewer",
                reviewed_modalities=(
                    "script",
                    "subtitle",
                    "audio",
                    "visual",
                ),
            ),
        ),
        render_qa=_qa(),
        gate=_gate(),
    )

    assert package.render_uri == "/generated/final.mp4"
    assert package.shot_ids == ("shot-1",)
    assert package.metadata["publication_performed"] is False


@pytest.mark.parametrize(
    "contract_type",
    [ReviewPackage, ReviewDecision, ReviewAuditTrail],
)
def test_review_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_review_core_has_no_ui_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "review.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app",
        "streamlit",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
        "extensions.human_review_ui",
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


def test_review_ui_has_required_actions_and_no_publishing_imports() -> None:
    path = REPO_ROOT / "extensions" / "human_review_ui" / "app.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for required in (
        "st.video",
        '"Approve"',
        '"Reject"',
        '"Regenerate shot"',
        '"Regenerate episode"',
    ):
        assert required in source

    forbidden = (
        "app.services.upload_post",
        "extensions.mpt_adapter",
        "app.services.task",
    )
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert not [
        module
        for module in imported
        if any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in forbidden
        )
    ]
    assert "publication_performed" in source
    assert "publish(" not in source.lower()


def test_kids_puppies_review_package_is_isolated_and_valid() -> None:
    package = ReviewPackage.from_json(
        _load(KIDS / "review" / "ep0002.review-package.json")
    )

    assert package.project_id == "kids-puppies-demo"
    assert package.episode_id == "ep0002"
    assert package.gate.eligible_for_human_review
    assert package.gate.publication_allowed is False
    assert "ep0002-s02-b" in package.shot_ids


def test_generic_review_package_contains_no_vertical_defaults() -> None:
    content = _load(EXAMPLES / "generic_review_package.json").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
