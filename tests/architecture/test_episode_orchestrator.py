"""End-to-end episode orchestrator, checkpoint and regeneration tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from extensions.content_studio.bibles import CharacterBible, UniverseBible
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
    MediaAssemblyPlan,
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
)
from extensions.content_studio.orchestration import (
    WORKFLOW_STAGES,
    EpisodeOrchestrator,
    EpisodeReleaseCandidate,
    EpisodeStageExecutor,
    EpisodeWorkflowState,
    StageExecutionResult,
    WorkflowArtifact,
    WorkflowCheckpointStore,
    WorkflowStageRecord,
    apply_review_decision,
    build_release_candidate,
)
from extensions.content_studio.prompting import PromptPlan
from extensions.content_studio.publishing import (
    PublicationAuditTrail,
    PublicationRecord,
    PublishResult,
    PublishTargetResult,
    PublishRequest,
)
from extensions.content_studio.quality import (
    RenderQAPolicy,
    build_human_review_gate,
    evaluate_render_qa,
)
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    build_review_package,
)
from extensions.content_studio.safety import (
    SafetyAssessment,
    SafetyPolicy,
    SafetyReviewRequest,
    TextRuleSafetyReviewer,
)
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.storyboard import StoryboardPlan
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualGenerationPlan,
    VisualGenerationReport,
    VisualResult,
)
from extensions.orchestration import JsonWorkflowCheckpointStore

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _canonical_fixture() -> dict[str, object]:
    base_project = ProjectSpec.from_json(
        _load(EXAMPLES / "generic_project.json")
    )
    story = StoryPlan.from_json(
        _load(EXAMPLES / "generic_story_plan.json")
    )
    episode = story.to_episode_spec()
    project = ProjectSpec(
        project_id=base_project.project_id,
        title=base_project.title,
        language=base_project.language,
        target_platforms=base_project.target_platforms,
        aspect_ratio=base_project.aspect_ratio,
        resolution=base_project.resolution,
        characters=base_project.characters,
        episodes=(episode,),
        metadata={"orchestrator_test": True},
    )
    characters = CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(EXAMPLES / "generic_universe_bible.json")
    )
    storyboard = StoryboardPlan.from_json(
        _load(EXAMPLES / "generic_storyboard_plan.json")
    )
    prompts = PromptPlan.from_json(
        _load(EXAMPLES / "generic_prompt_plan.json")
    )
    visual_plan = VisualGenerationPlan.from_json(
        _load(EXAMPLES / "generic_visual_generation_plan.json")
    )

    visual_results = []
    for request in visual_plan.requests:
        artifact = VisualArtifact(
            asset_id=f"{request.request_id}-asset",
            request_id=request.request_id,
            shot_id=request.shot_id,
            asset_kind=request.asset_kind,
            uri=f"generated/generic/{request.request_id}.png",
            engine="offline-fixture",
            provider="offline",
            width=1080,
            height=1920,
            duration_seconds=request.duration_seconds,
        )
        visual_results.append(
            VisualResult(
                request_id=request.request_id,
                engine="offline-fixture",
                success=True,
                artifacts=(artifact,),
                cost_usd=0.01,
            )
        )
    visual_report = VisualGenerationReport(
        project_id=visual_plan.project_id,
        story_id=visual_plan.story_id,
        episode_id=visual_plan.episode_id,
        results=tuple(visual_results),
        metadata={"offline": True},
    )

    consistency_results = []
    for result in visual_report.results:
        assessment = ConsistencyAssessment(
            request_id=result.request_id,
            evaluator="offline-evaluator",
            identity_score=0.97,
            appearance_score=0.96,
            wardrobe_score=0.95,
            environment_score=0.96,
        )
        consistency_results.append(
            ConsistentVisualResult(
                request_id=result.request_id,
                accepted=True,
                attempts=(
                    ConsistencyAttempt(
                        attempt_number=1,
                        visual_result=result,
                        assessment=assessment,
                    ),
                ),
            )
        )
    consistency = ConsistencyReport(
        project_id=visual_plan.project_id,
        story_id=visual_plan.story_id,
        episode_id=visual_plan.episode_id,
        results=tuple(consistency_results),
        metadata={"offline": True},
    )

    media_plan = MediaAssemblyPlan.from_json(
        _load(EXAMPLES / "generic_media_assembly_plan.json")
    )
    media = MediaAssemblyResult(
        assembly_id=media_plan.assembly_id,
        engine="offline-media",
        success=True,
        audio=AudioArtifact(
            audio_id="generic-audio",
            uri="generated/generic/narration.wav",
            duration_seconds=30,
            engine="offline-media",
            provider="offline",
        ),
        subtitle=SubtitleArtifact(
            subtitle_id="generic-subtitles",
            uri="generated/generic/subtitles.srt",
            format="srt",
            cue_count=4,
            engine="offline-media",
            provider="offline",
        ),
        video=RenderArtifact(
            render_id="generic-render",
            uri=media_plan.output_uri,
            engine="offline-media",
            provider="offline",
            width=1080,
            height=1920,
            duration_seconds=30,
        ),
        cost_usd=0.02,
        metadata={"publication_performed": False, "offline": True},
    )

    safety_policy = SafetyPolicy.from_json(
        _load(EXAMPLES / "generic_safety_policy.json")
    )
    text_assessment = TextRuleSafetyReviewer().review(
        SafetyReviewRequest(
            request_id="generic-safety-episode-2",
            project_id=project.project_id,
            episode_id=episode.episode_id,
            script="A friendly guide explains one simple idea.",
            subtitle_text="A friendly guide explains one simple idea.",
            audio_uri=media.audio.uri,
            visual_uris=(media.video.uri,),
        ),
        safety_policy,
    )
    multimodal_assessment = SafetyAssessment(
        request_id="generic-safety-episode-2",
        reviewer="offline-multimodal-reviewer",
        reviewed_modalities=("audio", "visual"),
        findings=(),
        metadata={"offline": True},
    )
    safety_assessments = (
        text_assessment,
        multimodal_assessment,
    )
    qa_policy = RenderQAPolicy.from_json(
        _load(EXAMPLES / "generic_render_qa_policy.json")
    )
    qa = evaluate_render_qa(
        project,
        media,
        consistency,
        qa_policy,
    )
    gate = build_human_review_gate(
        project.project_id,
        episode.episode_id,
        safety_policy,
        safety_assessments,
        qa,
    )
    package = build_review_package(
        package_id="generic-review-episode-2",
        media=media,
        consistency=consistency,
        safety_assessments=safety_assessments,
        render_qa=qa,
        gate=gate,
    )

    review_audit = ReviewAuditTrail.from_json(
        _load(EXAMPLES / "generic_review_approval_audit.json")
    )
    approval = review_audit.latest
    assert approval is not None

    publish_request = PublishRequest.from_json(
        _load(EXAMPLES / "generic_publish_request.json")
    )
    publish_result = PublishResult(
        request_id=publish_request.request_id,
        publisher="offline-publisher",
        success=True,
        dry_run=True,
        outcomes=tuple(
            PublishTargetResult(
                platform=target.platform,
                account_ref=target.account_ref,
                success=True,
                metadata={
                    "validation_only": True,
                    "network_called": False,
                },
            )
            for target in publish_request.targets
        ),
        metadata={
            "network_called": False,
            "publication_performed": False,
        },
    )
    publication_record = PublicationRecord(
        record_id="generic-publication-record-1",
        idempotency_key=publish_request.idempotency_key,
        request_fingerprint=publish_request.fingerprint,
        request=publish_request,
        result=publish_result,
        recorded_at="2026-09-23T21:05:00+00:00",
        metadata={"offline": True},
    )
    publication_audit = PublicationAuditTrail(
        records=(publication_record,),
        metadata={"offline": True},
    )

    return {
        "project": project,
        "episode": episode,
        "characters": characters,
        "universe": universe,
        "story": story,
        "storyboard": storyboard,
        "prompts": prompts,
        "visual_plan": visual_plan,
        "visual_report": visual_report,
        "consistency": consistency,
        "media_plan": media_plan,
        "media": media,
        "safety_assessments": safety_assessments,
        "qa": qa,
        "gate": gate,
        "package": package,
        "approval": approval,
        "review_audit": review_audit,
        "publish_result": publish_result,
        "publication_audit": publication_audit,
    }


def _artifact(
    artifact_id: str,
    contract,
) -> WorkflowArtifact:
    return WorkflowArtifact.from_contract(artifact_id, contract)


def _stage_artifacts() -> dict[str, tuple[WorkflowArtifact, ...]]:
    f = _canonical_fixture()
    return {
        "project_episode": (
            _artifact("project", f["project"]),
            _artifact("episode", f["episode"]),
        ),
        "bibles": (
            _artifact("character-bible", f["characters"]),
            _artifact("universe-bible", f["universe"]),
        ),
        "story": (_artifact("story-plan", f["story"]),),
        "storyboard": (
            _artifact("storyboard-plan", f["storyboard"]),
        ),
        "prompts": (_artifact("prompt-plan", f["prompts"]),),
        "visuals": (
            _artifact("visual-plan", f["visual_plan"]),
            _artifact("visual-report", f["visual_report"]),
        ),
        "consistency": (
            _artifact("consistency-report", f["consistency"]),
        ),
        "media": (
            _artifact("media-plan", f["media_plan"]),
            _artifact("media-result", f["media"]),
        ),
        "safety_qa": (
            *(
                _artifact(f"safety-{index}", item)
                for index, item in enumerate(
                    f["safety_assessments"],
                    start=1,
                )
            ),
            _artifact("render-qa", f["qa"]),
            _artifact("human-review-gate", f["gate"]),
        ),
        "review_package": (
            _artifact("review-package", f["package"]),
        ),
        "publish_dry_run": (
            _artifact("publish-result", f["publish_result"]),
            _artifact(
                "publication-audit",
                f["publication_audit"],
            ),
        ),
    }


class _FixtureExecutor:
    def __init__(
        self,
        stage_name: str,
        artifacts: tuple[WorkflowArtifact, ...],
        *,
        estimate: float | None = 0.01,
        actual_cost: float | None = 0.01,
    ) -> None:
        self._stage_name = stage_name
        self._artifacts = artifacts
        self._estimate = estimate
        self._actual_cost = actual_cost
        self.calls = 0
        self.execution_keys: list[str] = []

    @property
    def stage_name(self) -> str:
        return self._stage_name

    def estimate_cost_usd(
        self,
        state: EpisodeWorkflowState,
    ) -> float | None:
        del state
        return self._estimate

    def execute(
        self,
        state: EpisodeWorkflowState,
        execution_key: str,
    ) -> StageExecutionResult:
        del state
        self.calls += 1
        self.execution_keys.append(execution_key)
        return StageExecutionResult(
            stage=self.stage_name,
            status="PASS",
            artifacts=self._artifacts,
            cost_usd=self._actual_cost,
            metadata={"offline": True},
        )


def _orchestrator(
    store: WorkflowCheckpointStore,
    *,
    estimates: dict[str, float | None] | None = None,
) -> tuple[EpisodeOrchestrator, dict[str, _FixtureExecutor]]:
    artifacts = _stage_artifacts()
    executors = {}
    for stage in WORKFLOW_STAGES:
        if stage == "human_review":
            continue
        executor = _FixtureExecutor(
            stage,
            artifacts[stage],
            estimate=(
                estimates.get(stage, 0.01)
                if estimates is not None
                else 0.01
            ),
        )
        executors[stage] = executor

    ticks = iter(
        f"2026-09-23T21:{minute:02d}:00+00:00"
        for minute in range(0, 60)
    )
    orchestrator = EpisodeOrchestrator(
        executors,
        store,
        clock=lambda: next(ticks),
    )
    return orchestrator, executors


def test_full_workflow_blocks_for_human_then_builds_release_candidate(
    tmp_path,
) -> None:
    store = JsonWorkflowCheckpointStore(tmp_path)
    orchestrator, executors = _orchestrator(store)
    state = EpisodeWorkflowState(
        workflow_id="generic-episode-2-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=1.0,
        metadata={"offline": True},
    )

    blocked = orchestrator.run_until_blocked(state)

    assert blocked.stage_status("review_package") == "PASS"
    assert blocked.stage_status("human_review") == "BLOCKED"
    assert blocked.stage_status("publish_dry_run") == "PENDING"
    assert executors["publish_dry_run"].calls == 0

    fixture = _canonical_fixture()
    approved = apply_review_decision(
        blocked,
        fixture["approval"],
        fixture["review_audit"],
        decided_at="2026-09-23T21:40:00+00:00",
    )
    store.save(approved)

    completed = orchestrator.run_until_blocked(approved)

    assert completed.complete
    assert completed.stage_status("publish_dry_run") == "PASS"
    assert executors["publish_dry_run"].calls == 1
    candidate = build_release_candidate(completed)

    assert isinstance(candidate, EpisodeReleaseCandidate)
    assert candidate.publication_status == "dry_run_validated"
    assert candidate.render_uri == "generated/generic/final.mp4"
    assert candidate.review_decision_id == "generic-approve-1"
    assert candidate.publish_request_id == "generic-publish-episode-2"
    assert candidate.metadata["publication_performed"] is False
    assert candidate.total_cost_usd > 0
    assert store.load(completed.workflow_id) == completed


def test_resume_reuses_execution_key_for_in_progress_checkpoint(
    tmp_path,
) -> None:
    artifacts = _stage_artifacts()
    executor = _FixtureExecutor(
        "project_episode",
        artifacts["project_episode"],
    )
    store = JsonWorkflowCheckpointStore(tmp_path)
    record = WorkflowStageRecord(
        record_id="project-episode-r1-a1",
        stage="project_episode",
        status="IN_PROGRESS",
        attempt=1,
        execution_key="project-episode-resume-key",
        revision=1,
        started_at="2026-09-23T21:00:00+00:00",
    )
    state = EpisodeWorkflowState(
        workflow_id="resume-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        records=(record,),
    )
    store.save(state)
    orchestrator = EpisodeOrchestrator(
        {"project_episode": executor},
        store,
        clock=lambda: "2026-09-23T21:01:00+00:00",
    )

    resumed = orchestrator.run_next(store.load("resume-workflow"))

    assert resumed.stage_status("project_episode") == "PASS"
    assert executor.execution_keys == ["project-episode-resume-key"]
    assert resumed.latest_record("project_episode").attempt == 1


def test_budget_requires_known_estimate_before_executor_call(tmp_path) -> None:
    artifacts = _stage_artifacts()
    executor = _FixtureExecutor(
        "project_episode",
        artifacts["project_episode"],
        estimate=None,
    )
    store = JsonWorkflowCheckpointStore(tmp_path)
    state = EpisodeWorkflowState(
        workflow_id="budget-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=1.0,
    )
    orchestrator = EpisodeOrchestrator(
        {"project_episode": executor},
        store,
        clock=lambda: "2026-09-23T21:00:00+00:00",
    )

    blocked = orchestrator.run_next(state)

    assert blocked.stage_status("project_episode") == "BLOCKED"
    assert executor.calls == 0
    assert "cost estimate required" in (
        blocked.latest_record("project_episode").error or ""
    )


def test_budget_blocks_estimate_over_remaining_budget(tmp_path) -> None:
    artifacts = _stage_artifacts()
    executor = _FixtureExecutor(
        "project_episode",
        artifacts["project_episode"],
        estimate=2.0,
    )
    store = JsonWorkflowCheckpointStore(tmp_path)
    state = EpisodeWorkflowState(
        workflow_id="budget-over-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=1.0,
    )
    orchestrator = EpisodeOrchestrator(
        {"project_episode": executor},
        store,
        clock=lambda: "2026-09-23T21:00:00+00:00",
    )

    blocked = orchestrator.run_next(state)

    assert blocked.stage_status("project_episode") == "BLOCKED"
    assert executor.calls == 0


def test_actual_cost_over_budget_fails_and_preserves_cost(tmp_path) -> None:
    artifacts = _stage_artifacts()
    executor = _FixtureExecutor(
        "project_episode",
        artifacts["project_episode"],
        estimate=0.5,
        actual_cost=1.5,
    )
    store = JsonWorkflowCheckpointStore(tmp_path)
    state = EpisodeWorkflowState(
        workflow_id="actual-budget-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=1.0,
    )
    orchestrator = EpisodeOrchestrator(
        {"project_episode": executor},
        store,
        clock=lambda: "2026-09-23T21:00:00+00:00",
    )

    failed = orchestrator.run_next(state)
    record = failed.latest_record("project_episode")

    assert record.status == "FAIL"
    assert record.cost_usd == pytest.approx(1.5)
    assert failed.spent_cost_usd == pytest.approx(1.5)


def _state_at_human_review(tmp_path) -> tuple[
    EpisodeWorkflowState,
    EpisodeOrchestrator,
    JsonWorkflowCheckpointStore,
]:
    store = JsonWorkflowCheckpointStore(tmp_path)
    orchestrator, _ = _orchestrator(store)
    state = EpisodeWorkflowState(
        workflow_id="regen-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=2.0,
    )
    return orchestrator.run_until_blocked(state), orchestrator, store


def test_regenerate_shot_rewinds_from_visuals_and_preserves_history(
    tmp_path,
) -> None:
    blocked, _, _ = _state_at_human_review(tmp_path)
    package = blocked.require_one("ReviewPackage")
    assert package.shot_ids
    decision = ReviewDecision(
        decision_id="regen-shot-1",
        package_id=package.package_id,
        reviewer_id="reviewer-1",
        action="regenerate_shot",
        decided_at="2026-09-23T21:45:00+00:00",
        comments="Regenerate this shot for composition.",
        target_shot_id=package.shot_ids[1],
    )
    audit = ReviewAuditTrail(
        package_id=package.package_id,
        decisions=(decision,),
    )

    rewound = apply_review_decision(
        blocked,
        decision,
        audit,
        decided_at="2026-09-23T21:45:01+00:00",
    )

    assert rewound.revision == 2
    assert rewound.next_stage == "visuals"
    assert rewound.stage_status("prompts") == "PASS"
    assert rewound.stage_status("visuals") == "PENDING"
    assert any(
        item.stage == "visuals" and item.superseded
        for item in rewound.records
    )
    assert (
        rewound.metadata["regeneration_target_shot_id"]
        == package.shot_ids[1]
    )


def test_regenerate_episode_rewinds_from_story(tmp_path) -> None:
    blocked, _, _ = _state_at_human_review(tmp_path)
    package = blocked.require_one("ReviewPackage")
    decision = ReviewDecision(
        decision_id="regen-episode-1",
        package_id=package.package_id,
        reviewer_id="reviewer-1",
        action="regenerate_episode",
        decided_at="2026-09-23T21:46:00+00:00",
        comments="Rework the full story.",
    )
    audit = ReviewAuditTrail(
        package_id=package.package_id,
        decisions=(decision,),
    )

    rewound = apply_review_decision(
        blocked,
        decision,
        audit,
        decided_at="2026-09-23T21:46:01+00:00",
    )

    assert rewound.revision == 2
    assert rewound.next_stage == "story"
    assert rewound.stage_status("bibles") == "PASS"
    assert rewound.stage_status("story") == "PENDING"


def test_reject_marks_human_review_failed(tmp_path) -> None:
    blocked, _, _ = _state_at_human_review(tmp_path)
    package = blocked.require_one("ReviewPackage")
    decision = ReviewDecision(
        decision_id="reject-1",
        package_id=package.package_id,
        reviewer_id="reviewer-1",
        action="reject",
        decided_at="2026-09-23T21:47:00+00:00",
        comments="Reject the candidate.",
    )
    audit = ReviewAuditTrail(
        package_id=package.package_id,
        decisions=(decision,),
    )

    rejected = apply_review_decision(
        blocked,
        decision,
        audit,
        decided_at="2026-09-23T21:47:01+00:00",
    )

    assert rejected.stage_status("human_review") == "FAIL"
    assert rejected.stage_status("publish_dry_run") == "PENDING"


def test_checkpoint_store_round_trip_and_invalid_file(tmp_path) -> None:
    store = JsonWorkflowCheckpointStore(tmp_path)
    state = EpisodeWorkflowState(
        workflow_id="checkpoint-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        max_cost_usd=1.0,
    )
    assert isinstance(store, WorkflowCheckpointStore)

    store.save(state)
    assert store.load(state.workflow_id) == state

    path = tmp_path / "checkpoint-workflow.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(DomainValidationError, match="invalid workflow checkpoint"):
        store.load(state.workflow_id)


@pytest.mark.parametrize(
    "contract_type",
    [
        WorkflowArtifact,
        StageExecutionResult,
        WorkflowStageRecord,
        EpisodeWorkflowState,
        EpisodeReleaseCandidate,
    ],
)
def test_orchestration_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_orchestration_core_has_no_provider_vertical_or_ui_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "orchestration.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app",
        "requests",
        "openai",
        "streamlit",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
        "extensions.human_review_ui",
        "extensions.publishing_gateway",
        "extensions.orchestration",
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


def test_stage_executor_protocol() -> None:
    executor = _FixtureExecutor(
        "project_episode",
        _stage_artifacts()["project_episode"],
    )
    assert isinstance(executor, EpisodeStageExecutor)


def test_workflow_stage_order_is_explicit_and_publish_is_last() -> None:
    assert WORKFLOW_STAGES[0] == "project_episode"
    assert WORKFLOW_STAGES[-1] == "publish_dry_run"
    assert WORKFLOW_STAGES.index("human_review") < WORKFLOW_STAGES.index(
        "publish_dry_run"
    )
