"""Story Engine contract, validation and architecture tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    EpisodeSpec,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.story import (
    StoryBeat,
    StoryBrief,
    StoryContext,
    StoryEngine,
    StoryPlan,
    generate_story,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_context() -> StoryContext:
    project = ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))
    characters = CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(EXAMPLES / "generic_universe_bible.json")
    )
    return StoryContext(project, characters, universe)


def generic_plan() -> StoryPlan:
    return StoryPlan.from_json(_load(EXAMPLES / "generic_story_plan.json"))


def test_story_plan_round_trip() -> None:
    plan = generic_plan()
    restored = StoryPlan.from_json(plan.to_json())

    assert restored == plan
    assert restored.duration_seconds == 30
    assert json.loads(plan.to_json())["schema_version"] == SCHEMA_VERSION


def test_story_plan_validates_against_project_and_bibles() -> None:
    plan = generic_plan()
    context = generic_context()

    context.validate_plan(plan)


def test_story_plan_compiles_to_episode_spec() -> None:
    plan = generic_plan()
    episode = plan.to_episode_spec()

    assert isinstance(episode, EpisodeSpec)
    assert episode.episode_id == "episode-2"
    assert episode.duration_seconds == 30
    assert [scene.scene_id for scene in episode.scenes] == [
        "scene-1",
        "scene-2",
        "scene-3",
    ]
    assert episode.metadata["story_id"] == "generic-story-2"
    assert episode.scenes[0].metadata["story_purpose"] == "hook"


def test_beat_character_must_be_allowed_by_brief() -> None:
    brief = StoryBrief(
        story_id="story-1",
        project_id="generic-demo",
        episode_id="episode-2",
        title="Story",
        premise="A simple story.",
        language="en",
        duration_target_seconds=10,
        location_ids=("studio",),
    )
    beat = StoryBeat(
        beat_id="scene-1",
        order=1,
        purpose="hook",
        summary="A character enters.",
        duration_seconds=10,
        location_id="studio",
        character_ids=("unknown",),
    )

    with pytest.raises(DomainValidationError, match="outside StoryBrief"):
        StoryPlan(brief, (beat,))


def test_beat_location_must_be_allowed_by_brief() -> None:
    brief = generic_plan().brief
    beat = StoryBeat(
        beat_id="scene-1",
        order=1,
        purpose="hook",
        summary="Open elsewhere.",
        duration_seconds=5,
        location_id="unknown-place",
        character_ids=("guide-1",),
    )

    with pytest.raises(DomainValidationError, match="locations outside"):
        StoryPlan(brief, (beat,))


def test_beat_order_must_be_contiguous() -> None:
    brief = generic_plan().brief
    beats = (
        StoryBeat(
            "scene-1",
            1,
            "hook",
            "Open the story.",
            5,
            "studio",
            ("guide-1",),
        ),
        StoryBeat(
            "scene-2",
            3,
            "payoff",
            "Close the story.",
            25,
            "studio",
            ("guide-1",),
        ),
    )

    with pytest.raises(DomainValidationError, match="contiguous"):
        StoryPlan(brief, beats)


def test_context_rejects_unknown_project_character() -> None:
    context = generic_context()
    brief = StoryBrief(
        story_id="story-1",
        project_id="generic-demo",
        episode_id="episode-2",
        title="Story",
        premise="A simple story.",
        language="en",
        duration_target_seconds=10,
        location_ids=("studio",),
        character_ids=("missing",),
    )

    with pytest.raises(DomainValidationError, match="unknown project characters"):
        context.validate_brief(brief)


def test_context_rejects_unknown_universe_location() -> None:
    context = generic_context()
    brief = StoryBrief(
        story_id="story-1",
        project_id="generic-demo",
        episode_id="episode-2",
        title="Story",
        premise="A simple story.",
        language="en",
        duration_target_seconds=10,
        location_ids=("unknown-place",),
        character_ids=("guide-1",),
    )

    with pytest.raises(DomainValidationError, match="unknown location"):
        context.validate_brief(brief)


class _FakeEngine:
    def __init__(self, plan: object) -> None:
        self.plan = plan

    @property
    def engine_name(self) -> str:
        return "fake"

    def generate(
        self,
        brief: StoryBrief,
        context: StoryContext,
    ) -> StoryPlan:
        del brief, context
        return self.plan  # type: ignore[return-value]


def test_story_engine_protocol_and_guarded_generation() -> None:
    plan = generic_plan()
    context = generic_context()
    engine = _FakeEngine(plan)

    assert isinstance(engine, StoryEngine)
    assert generate_story(engine, plan.brief, context) == plan


def test_generate_story_rejects_non_plan_result() -> None:
    plan = generic_plan()
    engine = _FakeEngine({"not": "a plan"})

    with pytest.raises(DomainValidationError, match="must return a StoryPlan"):
        generate_story(engine, plan.brief, generic_context())


def test_generate_story_rejects_different_brief() -> None:
    plan = generic_plan()
    different = StoryBrief(
        story_id="different-story",
        project_id=plan.brief.project_id,
        episode_id=plan.brief.episode_id,
        title=plan.brief.title,
        premise=plan.brief.premise,
        language=plan.brief.language,
        duration_target_seconds=plan.brief.duration_target_seconds,
        location_ids=plan.brief.location_ids,
        character_ids=plan.brief.character_ids,
    )
    changed = StoryPlan(different, plan.beats)
    engine = _FakeEngine(changed)

    with pytest.raises(DomainValidationError, match="different StoryBrief"):
        generate_story(engine, plan.brief, generic_context())


@pytest.mark.parametrize("contract_type", [StoryBrief, StoryBeat, StoryPlan])
def test_story_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_story_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "story.py"
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


def test_kids_puppies_story_is_isolated_and_valid() -> None:
    project = ProjectSpec.from_json(
        _load(KIDS / "examples" / "project.json")
    )
    characters = CharacterBible.from_json(
        _load(KIDS / "bibles" / "character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(KIDS / "bibles" / "universe_bible.json")
    )
    plan = StoryPlan.from_json(
        _load(KIDS / "stories" / "ep0002.story.json")
    )

    plan.validate_context(project, characters, universe)
    episode = plan.to_episode_spec()

    assert episode.project_id == "kids-puppies-demo"
    assert episode.episode_id == "ep0002"
    assert episode.duration_seconds == 60
    assert episode.lesson is not None


def test_generic_story_contains_no_vertical_defaults() -> None:
    content = _load(EXAMPLES / "generic_story_plan.json").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
