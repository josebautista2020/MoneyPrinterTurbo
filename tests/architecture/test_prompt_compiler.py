"""Prompt Compiler contract, compilation and architecture tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.bibles import (
    CharacterBible,
    CharacterProfile,
    LocationProfile,
    UniverseBible,
)
from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.prompting import (
    CanonicalPromptCompiler,
    PromptCompiler,
    PromptContext,
    PromptPlan,
    ShotPrompt,
    compile_prompts,
)
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.storyboard import StoryboardPlan

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_project() -> ProjectSpec:
    return ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))


def generic_story() -> StoryPlan:
    return StoryPlan.from_json(_load(EXAMPLES / "generic_story_plan.json"))


def generic_storyboard() -> StoryboardPlan:
    return StoryboardPlan.from_json(
        _load(EXAMPLES / "generic_storyboard_plan.json")
    )


def generic_character_bible() -> CharacterBible:
    return CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )


def generic_universe_bible() -> UniverseBible:
    return UniverseBible.from_json(
        _load(EXAMPLES / "generic_universe_bible.json")
    )


def generic_context() -> PromptContext:
    return PromptContext(
        generic_project(),
        generic_story(),
        generic_character_bible(),
        generic_universe_bible(),
    )


def test_canonical_compiler_generates_one_prompt_per_shot() -> None:
    board = generic_storyboard()
    plan = CanonicalPromptCompiler().compile(board, generic_context())

    shot_ids = [
        shot.shot_id
        for scene in board.scenes
        for shot in scene.shots
    ]
    assert [prompt.shot_id for prompt in plan.prompts] == shot_ids
    assert len(plan.prompts) == 4
    plan.validate_storyboard(board)


def test_compiled_prompt_contains_visual_and_consistency_context() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    prompt = plan.prompts[0]

    assert "blue jacket" in prompt.visual_prompt
    assert "clean background" in prompt.visual_prompt
    assert "keep the guide centered" in prompt.visual_prompt
    assert "provider-neutral and brand-neutral" in prompt.visual_prompt
    assert "do not introduce branded elements" in prompt.negative_constraints
    assert (
        "do not change jacket color without an explicit project revision"
        in prompt.negative_constraints
    )


def test_compiler_aggregates_reference_assets_without_duplicates() -> None:
    project = generic_project()
    story = generic_story()
    board = generic_storyboard()

    characters = CharacterBible(
        project_id="generic-demo",
        profiles=(
            CharacterProfile(
                character_id="guide-1",
                signature_features=("blue jacket",),
                reference_asset_ids=("guide-ref", "shared-ref"),
            ),
        ),
    )
    universe = UniverseBible(
        project_id="generic-demo",
        locations=(
            LocationProfile(
                location_id="studio",
                description="A neutral studio.",
                reference_asset_ids=("studio-ref", "shared-ref"),
            ),
        ),
    )
    context = PromptContext(project, story, characters, universe)
    plan = CanonicalPromptCompiler().compile(board, context)

    assert plan.prompts[0].reference_asset_ids == (
        "studio-ref",
        "shared-ref",
        "guide-ref",
    )


def test_prompt_plan_round_trip() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    restored = PromptPlan.from_json(plan.to_json())

    assert restored == plan
    assert json.loads(plan.to_json())["schema_version"] == SCHEMA_VERSION


def test_committed_generic_prompt_example_is_valid() -> None:
    plan = PromptPlan.from_json(
        _load(EXAMPLES / "generic_prompt_plan.json")
    )
    plan.validate_storyboard(generic_storyboard())

    assert len(plan.prompts) == 4


def test_prompt_plan_rejects_missing_storyboard_shot() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    incomplete = PromptPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        plan.prompts[:-1],
    )

    with pytest.raises(DomainValidationError, match="coverage mismatch"):
        incomplete.validate_storyboard(generic_storyboard())


def test_prompt_must_preserve_storyboard_location() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    prompt = plan.prompts[0]
    changed = ShotPrompt(
        prompt.prompt_id,
        prompt.scene_id,
        prompt.shot_id,
        "another-location",
        prompt.duration_seconds,
        prompt.character_ids,
        prompt.visual_prompt,
        prompt.negative_constraints,
        prompt.reference_asset_ids,
        prompt.metadata,
    )
    altered = PromptPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        (changed, *plan.prompts[1:]),
    )

    with pytest.raises(DomainValidationError, match="location does not match"):
        altered.validate_storyboard(generic_storyboard())


def test_prompt_must_preserve_storyboard_characters() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    prompt = plan.prompts[0]
    changed = ShotPrompt(
        prompt.prompt_id,
        prompt.scene_id,
        prompt.shot_id,
        prompt.location_id,
        prompt.duration_seconds,
        (),
        prompt.visual_prompt,
        prompt.negative_constraints,
        prompt.reference_asset_ids,
        prompt.metadata,
    )
    altered = PromptPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        (changed, *plan.prompts[1:]),
    )

    with pytest.raises(DomainValidationError, match="characters do not match"):
        altered.validate_storyboard(generic_storyboard())


def test_prompt_must_preserve_storyboard_duration() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    prompt = plan.prompts[0]
    changed = ShotPrompt(
        prompt.prompt_id,
        prompt.scene_id,
        prompt.shot_id,
        prompt.location_id,
        prompt.duration_seconds + 1,
        prompt.character_ids,
        prompt.visual_prompt,
        prompt.negative_constraints,
        prompt.reference_asset_ids,
        prompt.metadata,
    )
    altered = PromptPlan(
        plan.project_id,
        plan.story_id,
        plan.episode_id,
        (changed, *plan.prompts[1:]),
    )

    with pytest.raises(DomainValidationError, match="duration does not match"):
        altered.validate_storyboard(generic_storyboard())


class _FakeCompiler:
    def __init__(self, result: object) -> None:
        self.result = result

    @property
    def compiler_name(self) -> str:
        return "fake"

    def compile(
        self,
        storyboard: StoryboardPlan,
        context: PromptContext,
    ) -> PromptPlan:
        del storyboard, context
        return self.result  # type: ignore[return-value]


def test_prompt_compiler_protocol_and_guarded_compilation() -> None:
    board = generic_storyboard()
    expected = CanonicalPromptCompiler().compile(board, generic_context())
    compiler = _FakeCompiler(expected)

    assert isinstance(compiler, PromptCompiler)
    assert compile_prompts(compiler, board, generic_context()) == expected


def test_compile_prompts_rejects_non_plan_result() -> None:
    compiler = _FakeCompiler({"not": "a prompt plan"})

    with pytest.raises(
        DomainValidationError,
        match="must return a PromptPlan",
    ):
        compile_prompts(
            compiler,
            generic_storyboard(),
            generic_context(),
        )


@pytest.mark.parametrize("contract_type", [ShotPrompt, PromptPlan])
def test_prompt_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_prompt_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "prompting.py"
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


def test_canonical_prompt_output_has_no_provider_specific_syntax() -> None:
    plan = CanonicalPromptCompiler().compile(
        generic_storyboard(),
        generic_context(),
    )
    encoded = plan.to_json().lower()

    for provider in (
        "moneyprinterturbo",
        "openai",
        "gemini",
        "runway",
        "veo",
        "kling",
        "midjourney",
    ):
        assert provider not in encoded


def test_kids_puppies_prompt_example_and_compilation_are_valid() -> None:
    project = ProjectSpec.from_json(
        _load(KIDS / "examples" / "project.json")
    )
    story = StoryPlan.from_json(
        _load(KIDS / "stories" / "ep0002.story.json")
    )
    board = StoryboardPlan.from_json(
        _load(KIDS / "storyboards" / "ep0002.storyboard.json")
    )
    characters = CharacterBible.from_json(
        _load(KIDS / "bibles" / "character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(KIDS / "bibles" / "universe_bible.json")
    )
    context = PromptContext(project, story, characters, universe)

    committed = PromptPlan.from_json(
        _load(KIDS / "prompts" / "ep0002.prompt-plan.json")
    )
    committed.validate_storyboard(board)

    compiled = CanonicalPromptCompiler().compile(board, context)
    compiled.validate_storyboard(board)

    assert len(compiled.prompts) == 8
    assert any("golden fur" in p.visual_prompt for p in compiled.prompts)
    assert any("purple bandana" in p.visual_prompt for p in compiled.prompts)
    assert all(
        "no frightening environmental hazards" in p.negative_constraints
        for p in compiled.prompts
    )


def test_generic_prompt_example_contains_no_vertical_defaults() -> None:
    content = _load(EXAMPLES / "generic_prompt_plan.json").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
