from __future__ import annotations

import pytest
from pathlib import Path

from extensions.content_studio.orchestration import StageExecutionResult
from extensions.content_studio.runtime import RuntimeProfile
from extensions.operator_console.service import OperatorConsoleService
from scripts.kids_puppies_ep0002_pilot import (
    build_initial_bundle,
    build_paid_profile,
)


def test_ep0002_initial_bundle_advances_to_visuals(tmp_path):
    service = OperatorConsoleService(
        workflow_dir=tmp_path / "workflows",
        review_audit_dir=tmp_path / "review",
        publication_audit_dir=tmp_path / "publication",
    )
    service.create_workflow(
        workflow_id="kids-ep0002-workflow",
        project_id="kids-puppies-demo",
        episode_id="ep0002",
        max_cost_usd=5,
    )
    results = tuple(
        StageExecutionResult.from_dict(item)
        for item in build_initial_bundle()
    )

    state = service.apply_stage_results("kids-ep0002-workflow", results)

    assert state.next_stage == "visuals"
    assert state.spent_cost_usd == 0
    assert state.max_cost_usd == 5


def test_ep0002_paid_profile_only_enables_visual_provider(tmp_path):
    source = "verticals/kids_puppies/runtime/profile-guarded.json"
    payload = build_paid_profile(source=Path(source), max_cost_usd=5)
    profile = RuntimeProfile.from_dict(payload)

    visual = profile.provider_for_stage("visuals")
    media = profile.provider_for_stage("media")

    assert visual.external_calls_enabled is True
    assert visual.paid_calls_enabled is True
    assert visual.max_stage_cost_usd == 5
    assert media.external_calls_enabled is False
    assert media.paid_calls_enabled is False


def test_ep0002_paid_profile_rejects_budget_above_ceiling():
    source = Path("verticals/kids_puppies/runtime/profile-guarded.json")

    with pytest.raises(SystemExit, match="max_cost_usd"):
        build_paid_profile(source=source, max_cost_usd=5.01)
