"""Character consistency contracts, retry loop and architecture tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.consistency import (
    ConsistencyAssessment,
    ConsistencyEvaluator,
    ConsistencyPolicy,
    ConsistencyReport,
    ReferenceAsset,
    ReferenceAwareVisualGenerator,
    ReferenceCatalog,
    bind_consistency_references,
    generate_consistent_visuals,
)
from extensions.content_studio.domain import DomainValidationError, SCHEMA_VERSION
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualGenerationPlan,
    VisualRequest,
    VisualResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_plan() -> VisualGenerationPlan:
    return VisualGenerationPlan.from_json(
        _load(EXAMPLES / "generic_visual_generation_plan.json")
    )


def generic_character_bible() -> CharacterBible:
    return CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )


def generic_universe_bible() -> UniverseBible:
    return UniverseBible.from_json(
        _load(EXAMPLES / "generic_universe_bible.json")
    )


def generic_catalog() -> ReferenceCatalog:
    return ReferenceCatalog.from_json(
        _load(EXAMPLES / "generic_reference_catalog.json")
    )


def generic_policy() -> ConsistencyPolicy:
    return ConsistencyPolicy.from_json(
        _load(EXAMPLES / "generic_consistency_policy.json")
    )


def single_request_plan() -> VisualGenerationPlan:
    plan = bind_consistency_references(
        generic_plan(),
        generic_character_bible(),
        generic_universe_bible(),
    )
    return VisualGenerationPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        (plan.requests[0],),
    )


def test_reference_binding_adds_character_and_location_assets() -> None:
    plan = bind_consistency_references(
        generic_plan(),
        generic_character_bible(),
        generic_universe_bible(),
    )

    assert all(
        request.reference_asset_ids == (
            "guide-ref-v1",
            "studio-ref-v1",
        )
        for request in plan.requests
    )


def test_reference_catalog_and_policy_round_trip() -> None:
    catalog = generic_catalog()
    policy = generic_policy()

    assert ReferenceCatalog.from_json(catalog.to_json()) == catalog
    assert ConsistencyPolicy.from_json(policy.to_json()) == policy
    assert policy.minimum_overall_score == pytest.approx(0.90)
    assert policy.max_attempts == 3


class _FakeReferenceGenerator:
    def __init__(self, cost: float | None = 0.01) -> None:
        self.cost = cost
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    @property
    def engine_name(self) -> str:
        return "fake-reference"

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        del request
        return self.cost

    def generate_with_references(
        self,
        request: VisualRequest,
        references: tuple[ReferenceAsset, ...],
    ) -> VisualResult:
        self.calls.append(
            (
                request.request_id,
                tuple(ref.reference_asset_id for ref in references),
            )
        )
        artifact = VisualArtifact(
            asset_id=f"{request.request_id}.attempt",
            request_id=request.request_id,
            shot_id=request.shot_id,
            asset_kind="image",
            uri=f"file:///generated/{request.request_id}.png",
            engine=self.engine_name,
            provider="fake",
            width=1024,
            height=1536,
            duration_seconds=request.duration_seconds,
        )
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=True,
            artifacts=(artifact,),
            cost_usd=self.cost,
        )


class _SequenceEvaluator:
    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.calls = 0

    @property
    def evaluator_name(self) -> str:
        return "fake-vision"

    def evaluate(
        self,
        request: VisualRequest,
        result: VisualResult,
        references: tuple[ReferenceAsset, ...],
    ) -> ConsistencyAssessment:
        del result, references
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        return ConsistencyAssessment(
            request_id=request.request_id,
            evaluator=self.evaluator_name,
            identity_score=score,
            appearance_score=score,
            wardrobe_score=score,
            environment_score=score,
        )


def test_reference_generator_and_evaluator_protocols() -> None:
    generator = _FakeReferenceGenerator()
    evaluator = _SequenceEvaluator([1.0])

    assert isinstance(generator, ReferenceAwareVisualGenerator)
    assert isinstance(evaluator, ConsistencyEvaluator)


def test_consistency_loop_regenerates_until_threshold_passes() -> None:
    plan = single_request_plan()
    generator = _FakeReferenceGenerator(cost=0.02)
    evaluator = _SequenceEvaluator([0.70, 0.95])

    report = generate_consistent_visuals(
        generator,
        evaluator,
        plan,
        generic_catalog(),
        generic_policy(),
        max_cost_usd=0.06,
    )
    report.validate_plan(plan)

    result = report.results[0]
    assert result.accepted
    assert len(result.attempts) == 2
    assert result.final_attempt.assessment is not None
    assert result.final_attempt.assessment.overall_score == pytest.approx(0.95)
    assert report.known_cost_usd == pytest.approx(0.04)
    assert report.cost_complete
    assert len(generator.calls) == 2


def test_consistency_loop_stops_after_max_attempts() -> None:
    plan = single_request_plan()
    generator = _FakeReferenceGenerator(cost=0.01)
    evaluator = _SequenceEvaluator([0.50])

    report = generate_consistent_visuals(
        generator,
        evaluator,
        plan,
        generic_catalog(),
        ConsistencyPolicy(max_attempts=2),
    )

    assert not report.success
    assert not report.results[0].accepted
    assert len(report.results[0].attempts) == 2


def test_budget_uses_worst_case_attempt_count_before_generation() -> None:
    plan = bind_consistency_references(
        generic_plan(),
        generic_character_bible(),
        generic_universe_bible(),
    )
    generator = _FakeReferenceGenerator(cost=0.05)
    evaluator = _SequenceEvaluator([1.0])

    with pytest.raises(DomainValidationError, match="worst-case"):
        generate_consistent_visuals(
            generator,
            evaluator,
            plan,
            generic_catalog(),
            ConsistencyPolicy(max_attempts=3),
            max_cost_usd=0.50,
        )

    assert generator.calls == []


def test_budget_rejects_unknown_cost_before_generation() -> None:
    generator = _FakeReferenceGenerator(cost=None)

    with pytest.raises(DomainValidationError, match="cost estimate required"):
        generate_consistent_visuals(
            generator,
            _SequenceEvaluator([1.0]),
            single_request_plan(),
            generic_catalog(),
            generic_policy(),
            max_cost_usd=1.0,
        )

    assert generator.calls == []


def test_missing_references_for_character_fails_before_generation() -> None:
    plan = generic_plan()
    generator = _FakeReferenceGenerator()

    with pytest.raises(DomainValidationError, match="characters but no"):
        generate_consistent_visuals(
            generator,
            _SequenceEvaluator([1.0]),
            plan,
            generic_catalog(),
            generic_policy(),
        )

    assert generator.calls == []


def test_unknown_reference_id_fails_before_generation() -> None:
    plan = single_request_plan()
    request = plan.requests[0]
    broken = VisualGenerationPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        (
            VisualRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                story_id=request.story_id,
                episode_id=request.episode_id,
                scene_id=request.scene_id,
                shot_id=request.shot_id,
                prompt=request.prompt,
                aspect_ratio=request.aspect_ratio,
                resolution=request.resolution,
                duration_seconds=request.duration_seconds,
                character_ids=request.character_ids,
                negative_constraints=request.negative_constraints,
                reference_asset_ids=("missing-ref",),
                asset_kind=request.asset_kind,
                metadata=request.metadata,
            ),
        ),
    )
    generator = _FakeReferenceGenerator()

    with pytest.raises(DomainValidationError, match="unknown reference asset"):
        generate_consistent_visuals(
            generator,
            _SequenceEvaluator([1.0]),
            broken,
            generic_catalog(),
            generic_policy(),
        )

    assert generator.calls == []


def test_consistency_report_round_trip() -> None:
    plan = single_request_plan()
    report = generate_consistent_visuals(
        _FakeReferenceGenerator(cost=0.0),
        _SequenceEvaluator([1.0]),
        plan,
        generic_catalog(),
        generic_policy(),
    )
    restored = ConsistencyReport.from_json(report.to_json())

    restored.validate_plan(plan)
    assert restored == report
    assert json.loads(report.to_json())["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize(
    "contract_type",
    [
        ReferenceAsset,
        ReferenceCatalog,
        ConsistencyAssessment,
        ConsistencyPolicy,
        ConsistencyReport,
    ],
)
def test_consistency_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_consistency_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "consistency.py"
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


def test_kids_puppies_binding_uses_toby_luna_and_park_references() -> None:
    plan = VisualGenerationPlan.from_json(
        _load(KIDS / "visuals" / "ep0002.visual-plan.json")
    )
    characters = CharacterBible.from_json(
        _load(KIDS / "bibles" / "character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(KIDS / "bibles" / "universe_bible.json")
    )
    catalog = ReferenceCatalog.from_json(
        _load(KIDS / "consistency" / "reference_catalog.json")
    )
    policy = ConsistencyPolicy.from_json(
        _load(KIDS / "consistency" / "policy.json")
    )
    bound = bind_consistency_references(plan, characters, universe)

    first = bound.requests[0]
    second = bound.requests[1]

    assert first.reference_asset_ids == ("toby-ref-v1", "park-ref-v1")
    assert second.reference_asset_ids == (
        "toby-ref-v1",
        "luna-ref-v1",
        "park-ref-v1",
    )
    assert catalog.resolve("toby-ref-v1").character_id == "toby"
    assert policy.minimum_identity_score == pytest.approx(0.92)
