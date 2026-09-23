"""Visual generation core contract, budget and architecture tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.prompting import PromptPlan
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualGenerationPlan,
    VisualGenerationReport,
    VisualGenerator,
    VisualRequest,
    VisualResult,
    build_visual_generation_plan,
    generate_visuals,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_project() -> ProjectSpec:
    return ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))


def generic_prompt_plan() -> PromptPlan:
    return PromptPlan.from_json(_load(EXAMPLES / "generic_prompt_plan.json"))


def generic_visual_plan() -> VisualGenerationPlan:
    return VisualGenerationPlan.from_json(
        _load(EXAMPLES / "generic_visual_generation_plan.json")
    )


def test_build_visual_plan_generates_one_request_per_prompt() -> None:
    prompt_plan = generic_prompt_plan()
    plan = build_visual_generation_plan(prompt_plan, generic_project())

    assert len(plan.requests) == len(prompt_plan.prompts) == 4
    assert [request.shot_id for request in plan.requests] == [
        prompt.shot_id for prompt in prompt_plan.prompts
    ]
    assert all(request.asset_kind == "image" for request in plan.requests)
    assert all(request.aspect_ratio == "9:16" for request in plan.requests)
    assert all(request.resolution == "1080x1920" for request in plan.requests)
    plan.validate_prompt_plan(prompt_plan)


def test_committed_visual_plan_is_valid_and_round_trips() -> None:
    plan = generic_visual_plan()
    plan.validate_prompt_plan(generic_prompt_plan())

    restored = VisualGenerationPlan.from_json(plan.to_json())
    assert restored == plan
    assert json.loads(plan.to_json())["schema_version"] == SCHEMA_VERSION


class _FakeGenerator:
    def __init__(
        self,
        *,
        cost: float | None = 0.01,
        fail_request_id: str | None = None,
        wrong_request_id: bool = False,
    ) -> None:
        self.cost = cost
        self.fail_request_id = fail_request_id
        self.wrong_request_id = wrong_request_id
        self.calls: list[str] = []

    @property
    def engine_name(self) -> str:
        return "fake-visual"

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        del request
        return self.cost

    def generate(self, request: VisualRequest) -> VisualResult:
        self.calls.append(request.request_id)
        if request.request_id == self.fail_request_id:
            return VisualResult(
                request_id=request.request_id,
                engine=self.engine_name,
                success=False,
                error="simulated failure",
                cost_usd=0.0,
            )

        result_id = (
            "different-request"
            if self.wrong_request_id
            else request.request_id
        )
        artifact = VisualArtifact(
            asset_id=result_id,
            request_id=result_id,
            shot_id=request.shot_id,
            asset_kind=request.asset_kind,
            uri=f"file:///generated/{request.shot_id}.png",
            engine=self.engine_name,
            provider="fake",
            width=1024,
            height=1536,
            duration_seconds=request.duration_seconds,
        )
        return VisualResult(
            request_id=result_id,
            engine=self.engine_name,
            success=True,
            artifacts=(artifact,),
            cost_usd=self.cost,
        )


def test_visual_generator_protocol_and_successful_report() -> None:
    generator = _FakeGenerator(cost=0.02)
    plan = build_visual_generation_plan(
        generic_prompt_plan(),
        generic_project(),
    )

    assert isinstance(generator, VisualGenerator)

    report = generate_visuals(generator, plan, max_cost_usd=0.08)
    report.validate_plan(plan)

    assert report.success
    assert report.cost_complete
    assert report.known_cost_usd == pytest.approx(0.08)
    assert len(report.results) == 4


def test_budget_gate_runs_before_any_generation() -> None:
    generator = _FakeGenerator(cost=0.05)
    plan = build_visual_generation_plan(
        generic_prompt_plan(),
        generic_project(),
    )

    with pytest.raises(DomainValidationError, match="exceeds budget"):
        generate_visuals(generator, plan, max_cost_usd=0.10)

    assert generator.calls == []


def test_budget_gate_rejects_unknown_cost_before_generation() -> None:
    generator = _FakeGenerator(cost=None)
    plan = generic_visual_plan()

    with pytest.raises(DomainValidationError, match="cost estimate required"):
        generate_visuals(generator, plan, max_cost_usd=1.0)

    assert generator.calls == []


def test_fail_fast_stops_after_first_failed_result() -> None:
    plan = generic_visual_plan()
    generator = _FakeGenerator(
        cost=0.0,
        fail_request_id=plan.requests[1].request_id,
    )

    report = generate_visuals(generator, plan, fail_fast=True)

    assert not report.success
    assert len(report.results) == 2
    assert len(generator.calls) == 2


def test_generator_cannot_return_result_for_another_request() -> None:
    generator = _FakeGenerator(cost=0.0, wrong_request_id=True)

    with pytest.raises(DomainValidationError, match="different request"):
        generate_visuals(generator, generic_visual_plan())


def test_visual_result_requires_artifact_on_success() -> None:
    with pytest.raises(DomainValidationError, match="at least one artifact"):
        VisualResult(
            request_id="request-1",
            engine="fake",
            success=True,
        )


def test_visual_report_round_trip_and_cost_visibility() -> None:
    plan = generic_visual_plan()
    report = generate_visuals(_FakeGenerator(cost=0.03), plan)
    restored = VisualGenerationReport.from_json(report.to_json())

    assert restored == report
    assert restored.known_cost_usd == pytest.approx(0.12)
    assert restored.cost_complete


@pytest.mark.parametrize(
    "contract_type",
    [
        VisualRequest,
        VisualGenerationPlan,
        VisualArtifact,
        VisualResult,
        VisualGenerationReport,
    ],
)
def test_visual_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_visual_core_has_no_provider_or_vertical_imports() -> None:
    path = (
        REPO_ROOT
        / "extensions"
        / "content_studio"
        / "visual_generation.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = ("app", "verticals", "extensions.mpt_adapter")
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


def test_kids_puppies_visual_plan_is_isolated_and_valid() -> None:
    project = ProjectSpec.from_json(
        _load(KIDS / "examples" / "project.json")
    )
    prompt_plan = PromptPlan.from_json(
        _load(KIDS / "prompts" / "ep0002.prompt-plan.json")
    )
    committed = VisualGenerationPlan.from_json(
        _load(KIDS / "visuals" / "ep0002.visual-plan.json")
    )

    committed.validate_prompt_plan(prompt_plan)
    built = build_visual_generation_plan(prompt_plan, project)

    assert len(committed.requests) == len(built.requests) == 8
    assert all(request.asset_kind == "image" for request in committed.requests)
    assert {request.shot_id for request in committed.requests} == {
        request.shot_id for request in built.requests
    }


def test_generic_visual_example_contains_no_vertical_defaults() -> None:
    content = _load(
        EXAMPLES / "generic_visual_generation_plan.json"
    ).lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
