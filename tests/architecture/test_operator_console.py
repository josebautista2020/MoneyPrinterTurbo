"""Operator Console service, CLI and governance tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import DomainValidationError, ProjectSpec
from extensions.content_studio.orchestration import (
    EpisodeWorkflowState,
    StageExecutionResult,
    WorkflowArtifact,
    WorkflowStageRecord,
)
from extensions.content_studio.publishing import PublishingPolicy, PublishRequest
from extensions.content_studio.review import ReviewPackage
from extensions.operator_console.cli import main as cli_main
from extensions.operator_console.service import (
    OperatorConsoleService,
    WorkflowSummary,
)
from extensions.orchestration import JsonWorkflowCheckpointStore

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _service(tmp_path: Path) -> OperatorConsoleService:
    return OperatorConsoleService(
        workflow_dir=tmp_path / "workflows",
        review_audit_dir=tmp_path / "reviews",
        publication_audit_dir=tmp_path / "publications",
    )


def _artifact(artifact_id: str, contract) -> WorkflowArtifact:
    return WorkflowArtifact.from_contract(artifact_id, contract)


def _project_stage_result() -> StageExecutionResult:
    project = ProjectSpec.from_json(
        _load(EXAMPLES / "generic_project.json")
    )
    episode = project.episodes[0]
    return StageExecutionResult(
        stage="project_episode",
        status="PASS",
        artifacts=(
            _artifact("generic-project", project),
            _artifact("generic-episode-1", episode),
        ),
        cost_usd=0.0,
        metadata={"offline": True},
    )


def _bibles_stage_result() -> StageExecutionResult:
    characters = CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(EXAMPLES / "generic_universe_bible.json")
    )
    return StageExecutionResult(
        stage="bibles",
        status="PASS",
        artifacts=(
            _artifact("generic-character-bible", characters),
            _artifact("generic-universe-bible", universe),
        ),
        cost_usd=0.0,
        metadata={"offline": True},
    )


def _pass_record(
    stage: str,
    order: int,
    *,
    artifacts: tuple[WorkflowArtifact, ...] = (),
) -> WorkflowStageRecord:
    return WorkflowStageRecord(
        record_id=f"{stage}-pass-{order}",
        stage=stage,
        status="PASS",
        attempt=1,
        execution_key=f"{stage}-key-{order}",
        revision=1,
        started_at=f"2026-09-23T20:{order:02d}:00+00:00",
        finished_at=f"2026-09-23T20:{order:02d}:30+00:00",
        artifacts=artifacts,
        cost_usd=0.0,
    )


def _review_ready_state(
    *,
    package: ReviewPackage | None = None,
) -> EpisodeWorkflowState:
    package = package or ReviewPackage.from_json(
        _load(EXAMPLES / "generic_review_package.json")
    )
    stages = (
        "project_episode",
        "bibles",
        "story",
        "storyboard",
        "prompts",
        "visuals",
        "consistency",
        "media",
        "safety_qa",
        "review_package",
    )
    records = []
    for index, stage in enumerate(stages, start=1):
        artifacts = ()
        if stage == "review_package":
            artifacts = (
                _artifact("generic-review-package", package),
            )
        records.append(
            _pass_record(stage, index, artifacts=artifacts)
        )
    return EpisodeWorkflowState(
        workflow_id="generic-review-workflow",
        project_id="generic-demo",
        episode_id="episode-2",
        records=tuple(records),
        max_cost_usd=1.0,
    )


def _save_review_ready(
    service: OperatorConsoleService,
    *,
    package: ReviewPackage | None = None,
) -> EpisodeWorkflowState:
    state = _review_ready_state(package=package)
    service.workflow_store.save(state)
    return state


def test_create_list_load_and_summary(tmp_path) -> None:
    service = _service(tmp_path)

    created = service.create_workflow(
        workflow_id="operator-workflow",
        project_id="generic-demo",
        episode_id="episode-1",
        max_cost_usd=2.5,
    )

    assert service.list_workflow_ids() == ("operator-workflow",)
    assert service.load_workflow(created.workflow_id) == created
    summary = service.summarize(created.workflow_id)
    assert isinstance(summary, WorkflowSummary)
    assert summary.next_stage == "project_episode"
    assert summary.spent_cost_usd == 0.0
    assert summary.max_cost_usd == 2.5
    assert len(summary.stage_rows) == 12
    assert summary.stage_rows[0]["status"] == "PENDING"

    with pytest.raises(DomainValidationError, match="already exists"):
        service.create_workflow(
            workflow_id="operator-workflow",
            project_id="generic-demo",
            episode_id="episode-1",
        )


def test_apply_stage_result_uses_orchestrator_and_checkpoint(tmp_path) -> None:
    service = _service(tmp_path)
    service.create_workflow(
        workflow_id="operator-workflow",
        project_id="generic-demo",
        episode_id="episode-1",
        max_cost_usd=1.0,
    )

    updated = service.apply_stage_result(
        "operator-workflow",
        _project_stage_result(),
    )

    assert updated.stage_status("project_episode") == "PASS"
    assert updated.next_stage == "bibles"
    reloaded = service.load_workflow("operator-workflow")
    assert reloaded == updated
    assert service.active_artifacts("operator-workflow")


def test_apply_bundle_processes_sequential_results(tmp_path) -> None:
    service = _service(tmp_path)
    service.create_workflow(
        workflow_id="bundle-workflow",
        project_id="generic-demo",
        episode_id="episode-1",
        max_cost_usd=1.0,
    )

    updated = service.apply_stage_results(
        "bundle-workflow",
        (
            _project_stage_result(),
            _bibles_stage_result(),
        ),
    )

    assert updated.stage_status("project_episode") == "PASS"
    assert updated.stage_status("bibles") == "PASS"
    assert updated.next_stage == "story"


def test_resume_preserves_in_progress_execution_key(tmp_path) -> None:
    service = _service(tmp_path)
    in_progress = WorkflowStageRecord(
        record_id="project-episode-r1-a1",
        stage="project_episode",
        status="IN_PROGRESS",
        attempt=1,
        execution_key="operator-resume-key",
        revision=1,
        started_at="2026-09-23T20:00:00+00:00",
    )
    state = EpisodeWorkflowState(
        workflow_id="resume-workflow",
        project_id="generic-demo",
        episode_id="episode-1",
        records=(in_progress,),
        max_cost_usd=1.0,
    )
    service.workflow_store.save(state)

    updated = service.apply_stage_result(
        "resume-workflow",
        _project_stage_result(),
    )

    record = updated.latest_record("project_episode")
    assert record is not None
    assert record.status == "PASS"
    assert record.attempt == 1
    assert record.execution_key == "operator-resume-key"


@pytest.mark.parametrize("stage", ["human_review", "publish_dry_run"])
def test_manual_stage_result_cannot_bypass_governed_stages(
    tmp_path,
    stage,
) -> None:
    service = _service(tmp_path)
    state = _review_ready_state()
    if stage == "publish_dry_run":
        service.workflow_store.save(state)
        service.record_review_decision(
            state.workflow_id,
            reviewer_id="reviewer-1",
            action="approve",
            comments="Approved for governed dry-run.",
            decision_id="generic-approve-1",
            decided_at="2026-09-23T21:00:00+00:00",
        )
    else:
        service.workflow_store.save(state)

    result = StageExecutionResult(
        stage=stage,
        status="BLOCKED",
        error="manual injection attempt",
        cost_usd=0.0,
    )
    with pytest.raises(DomainValidationError, match="governed operator action"):
        service.apply_stage_result(state.workflow_id, result)


def test_valid_approval_is_audited_and_applied(tmp_path) -> None:
    service = _service(tmp_path)
    state = _save_review_ready(service)

    approved = service.record_review_decision(
        state.workflow_id,
        reviewer_id="reviewer-1",
        action="approve",
        comments="Safety and QA reviewed.",
        decision_id="generic-approve-1",
        decided_at="2026-09-23T21:00:00+00:00",
    )

    assert approved.stage_status("human_review") == "PASS"
    assert approved.next_stage == "publish_dry_run"
    package = approved.require_one("ReviewPackage")
    audit = service.review_store.list(package.package_id)
    assert audit.latest is not None
    assert audit.latest.decision_id == "generic-approve-1"
    assert audit.latest.action == "approve"


def test_invalid_approval_is_not_persisted(tmp_path) -> None:
    service = _service(tmp_path)
    package = ReviewPackage.from_json(
        _load(EXAMPLES / "generic_review_package.json")
    )
    blocked_gate = replace(
        package.gate,
        eligible_for_human_review=False,
        render_qa_passed=False,
    )
    blocked_package = replace(package, gate=blocked_gate)
    state = _save_review_ready(service, package=blocked_package)

    with pytest.raises(DomainValidationError, match="not eligible"):
        service.record_review_decision(
            state.workflow_id,
            reviewer_id="reviewer-1",
            action="approve",
            comments="Should not persist.",
            decision_id="invalid-approve-1",
            decided_at="2026-09-23T21:00:00+00:00",
        )

    audit = service.review_store.list(blocked_package.package_id)
    assert audit.decisions == ()


def test_regenerate_shot_rewinds_workflow(tmp_path) -> None:
    service = _service(tmp_path)
    state = _save_review_ready(service)
    package = state.require_one("ReviewPackage")

    rewound = service.record_review_decision(
        state.workflow_id,
        reviewer_id="reviewer-1",
        action="regenerate_shot",
        comments="Regenerate shot composition.",
        target_shot_id=package.shot_ids[0],
        decision_id="operator-regen-shot-1",
        decided_at="2026-09-23T21:01:00+00:00",
    )

    assert rewound.revision == 2
    assert rewound.next_stage == "visuals"
    assert rewound.metadata["regeneration_target_shot_id"] == package.shot_ids[0]


def _approve_for_publish(
    service: OperatorConsoleService,
) -> EpisodeWorkflowState:
    state = _save_review_ready(service)
    return service.record_review_decision(
        state.workflow_id,
        reviewer_id="reviewer-1",
        action="approve",
        comments="Approved for dry-run.",
        decision_id="generic-approve-1",
        decided_at="2026-09-23T21:00:00+00:00",
    )


def test_publish_dry_run_completes_release_candidate_without_network(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    approved = _approve_for_publish(service)
    request = PublishRequest.from_json(
        _load(EXAMPLES / "generic_publish_request.json")
    )
    policy = PublishingPolicy.from_json(
        _load(EXAMPLES / "generic_publishing_policy.json")
    )

    completed = service.prepare_publish_dry_run(
        approved.workflow_id,
        request=request,
        policy=policy,
        recorded_at="2026-09-23T21:05:00+00:00",
    )

    assert completed.complete
    result = completed.require_one("PublishResult")
    assert result.success
    assert result.dry_run
    assert result.metadata["network_called"] is False
    assert result.metadata["publication_performed"] is False

    candidate = service.build_release_candidate(completed.workflow_id)
    assert candidate.publication_status == "dry_run_validated"
    assert candidate.metadata["publication_performed"] is False
    assert candidate.review_decision_id == "generic-approve-1"

    ledger = service._publication_ledger(completed.workflow_id)
    assert len(ledger.trail().records) == 1
    assert ledger.trail().records[0].request.dry_run is True


def test_operator_console_rejects_live_request_and_live_policy(tmp_path) -> None:
    service = _service(tmp_path)
    approved = _approve_for_publish(service)
    request = PublishRequest.from_json(
        _load(EXAMPLES / "generic_publish_request.json")
    )
    policy = PublishingPolicy.from_json(
        _load(EXAMPLES / "generic_publishing_policy.json")
    )

    with pytest.raises(DomainValidationError, match="dry_run=True"):
        service.prepare_publish_dry_run(
            approved.workflow_id,
            request=replace(request, dry_run=False),
            policy=policy,
        )

    with pytest.raises(DomainValidationError, match="live_publish_enabled=False"):
        service.prepare_publish_dry_run(
            approved.workflow_id,
            request=request,
            policy=replace(policy, live_publish_enabled=True),
        )

    ledger = service._publication_ledger(approved.workflow_id)
    assert ledger.trail().records == ()


def test_checkpoint_store_lists_validated_workflows(tmp_path) -> None:
    store = JsonWorkflowCheckpointStore(tmp_path)
    store.save(
        EpisodeWorkflowState(
            workflow_id="b-workflow",
            project_id="generic-demo",
            episode_id="episode-1",
        )
    )
    store.save(
        EpisodeWorkflowState(
            workflow_id="a-workflow",
            project_id="generic-demo",
            episode_id="episode-1",
        )
    )

    assert store.list_workflow_ids() == (
        "a-workflow",
        "b-workflow",
    )

    (tmp_path / "wrong-name.json").write_text(
        EpisodeWorkflowState(
            workflow_id="different-id",
            project_id="generic-demo",
            episode_id="episode-1",
        ).to_json(),
        encoding="utf-8",
    )
    with pytest.raises(DomainValidationError, match="filename"):
        store.list_workflow_ids()


def test_cli_create_list_and_show(tmp_path, capsys) -> None:
    common = [
        "--workflow-dir",
        str(tmp_path / "workflows"),
        "--review-dir",
        str(tmp_path / "reviews"),
        "--publication-dir",
        str(tmp_path / "publications"),
    ]

    assert cli_main(
        [
            *common,
            "create",
            "--workflow-id",
            "cli-workflow",
            "--project-id",
            "generic-demo",
            "--episode-id",
            "episode-1",
            "--max-cost-usd",
            "3.5",
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["workflow_id"] == "cli-workflow"

    assert cli_main([*common, "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["workflows"] == ["cli-workflow"]

    assert cli_main(
        [*common, "show", "--workflow-id", "cli-workflow"]
    ) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["next_stage"] == "project_episode"
    assert shown["max_cost_usd"] == 3.5


def test_operator_surfaces_have_no_live_publish_or_mpt_imports() -> None:
    paths = (
        REPO_ROOT / "extensions" / "operator_console" / "service.py",
        REPO_ROOT / "extensions" / "operator_console" / "cli.py",
        REPO_ROOT / "extensions" / "operator_console" / "app.py",
    )
    forbidden_imports = (
        "app.services.upload_post",
        "extensions.mpt_adapter",
        "requests",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
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
                for prefix in forbidden_imports
            )
        ]
        assert "allow_live_publish=True" not in source
        assert "publish-live" not in source.lower()

    ui_source = paths[2].read_text(encoding="utf-8")
    assert '"Run publish dry-run"' in ui_source
    assert "Live publication is not available" in ui_source
