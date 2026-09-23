"""Storyboard Engine contract, validation and architecture tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.storyboard import (
    StoryboardContext,
    StoryboardEngine,
    StoryboardPlan,
    StoryboardScene,
    StoryboardShot,
    generate_storyboard,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generic_story() -> StoryPlan:
    return StoryPlan.from_json(_load(EXAMPLES / "generic_story_plan.json"))


def generic_board() -> StoryboardPlan:
    return StoryboardPlan.from_json(
        _load(EXAMPLES / "generic_storyboard_plan.json")
    )


def generic_context() -> StoryboardContext:
    return StoryboardContext(
        ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json")),
        CharacterBible.from_json(
            _load(EXAMPLES / "generic_character_bible.json")
        ),
        UniverseBible.from_json(
            _load(EXAMPLES / "generic_universe_bible.json")
        ),
    )


def test_storyboard_round_trip() -> None:
    board = generic_board()
    restored = StoryboardPlan.from_json(board.to_json())

    assert restored == board
    assert restored.duration_seconds == 30
    assert json.loads(board.to_json())["schema_version"] == SCHEMA_VERSION


def test_storyboard_validates_against_story_and_bibles() -> None:
    generic_context().validate_storyboard(generic_board(), generic_story())


def test_each_story_beat_has_one_storyboard_scene() -> None:
    board = generic_board()
    story = generic_story()

    assert {scene.beat_id for scene in board.scenes} == {
        beat.beat_id for beat in story.beats
    }


def test_scene_shot_duration_matches_story_beat() -> None:
    board = generic_board()
    story = generic_story()
    beats = {beat.beat_id: beat for beat in story.beats}

    for scene in board.scenes:
        assert scene.duration_seconds == pytest.approx(
            beats[scene.beat_id].duration_seconds
        )


def test_shot_character_must_be_declared_by_scene() -> None:
    shot = StoryboardShot(
        shot_id="shot-1",
        order=1,
        duration_seconds=5,
        visual_action="A character enters.",
        framing="medium",
        character_ids=("missing",),
    )

    with pytest.raises(DomainValidationError, match="outside StoryboardScene"):
        StoryboardScene(
            scene_id="scene-1",
            beat_id="scene-1",
            order=1,
            location_id="studio",
            character_ids=("guide-1",),
            shots=(shot,),
        )


def test_shot_order_must_be_contiguous() -> None:
    shots = (
        StoryboardShot(
            "shot-1",
            1,
            2,
            "First visual.",
            "wide",
        ),
        StoryboardShot(
            "shot-2",
            3,
            3,
            "Second visual.",
            "medium",
        ),
    )

    with pytest.raises(DomainValidationError, match="contiguous"):
        StoryboardScene(
            "scene-1",
            "scene-1",
            1,
            "studio",
            (),
            shots,
        )


def test_storyboard_rejects_duplicate_shot_ids_across_scenes() -> None:
    shot_a = StoryboardShot(
        "duplicate-shot",
        1,
        5,
        "First visual.",
        "wide",
    )
    shot_b = StoryboardShot(
        "duplicate-shot",
        1,
        25,
        "Second visual.",
        "wide",
    )
    scenes = (
        StoryboardScene(
            "sb-1",
            "scene-1",
            1,
            "studio",
            (),
            (shot_a,),
        ),
        StoryboardScene(
            "sb-2",
            "scene-2",
            2,
            "studio",
            (),
            (shot_b,),
        ),
    )

    with pytest.raises(DomainValidationError, match="unique across"):
        StoryboardPlan(
            "generic-story-2",
            "generic-demo",
            "episode-2",
            scenes,
        )


def test_storyboard_rejects_missing_story_beat() -> None:
    board = generic_board()
    incomplete = StoryboardPlan(
        board.story_id,
        board.project_id,
        board.episode_id,
        board.scenes[:-1],
    )

    with pytest.raises(DomainValidationError, match="coverage mismatch"):
        incomplete.validate_story(generic_story())


def test_storyboard_scene_must_preserve_story_location() -> None:
    board = generic_board()
    scene = board.scenes[0]
    changed = StoryboardScene(
        scene.scene_id,
        scene.beat_id,
        scene.order,
        "another-location",
        scene.character_ids,
        scene.shots,
    )
    altered = StoryboardPlan(
        board.story_id,
        board.project_id,
        board.episode_id,
        (changed, *board.scenes[1:]),
    )

    with pytest.raises(DomainValidationError, match="location does not match"):
        altered.validate_story(generic_story())


def test_storyboard_scene_must_preserve_story_characters() -> None:
    board = generic_board()
    scene = board.scenes[0]
    changed_shot = StoryboardShot(
        shot_id=scene.shots[0].shot_id,
        order=1,
        duration_seconds=scene.shots[0].duration_seconds,
        visual_action=scene.shots[0].visual_action,
        framing=scene.shots[0].framing,
    )
    changed = StoryboardScene(
        scene.scene_id,
        scene.beat_id,
        scene.order,
        scene.location_id,
        (),
        (changed_shot,),
    )
    altered = StoryboardPlan(
        board.story_id,
        board.project_id,
        board.episode_id,
        (changed, *board.scenes[1:]),
    )

    with pytest.raises(DomainValidationError, match="characters do not match"):
        altered.validate_story(generic_story())


def test_storyboard_scene_duration_must_match_story_beat() -> None:
    board = generic_board()
    scene = board.scenes[0]
    shot = scene.shots[0]
    changed_shot = StoryboardShot(
        shot.shot_id,
        shot.order,
        shot.duration_seconds + 1,
        shot.visual_action,
        shot.framing,
        shot.character_ids,
        shot.camera_angle,
        shot.camera_movement,
        shot.composition_notes,
        shot.continuity_notes,
        shot.metadata,
    )
    changed = StoryboardScene(
        scene.scene_id,
        scene.beat_id,
        scene.order,
        scene.location_id,
        scene.character_ids,
        (changed_shot,),
    )
    altered = StoryboardPlan(
        board.story_id,
        board.project_id,
        board.episode_id,
        (changed, *board.scenes[1:]),
    )

    with pytest.raises(DomainValidationError, match="shot duration"):
        altered.validate_story(generic_story())


class _FakeStoryboardEngine:
    def __init__(self, result: object) -> None:
        self.result = result

    @property
    def engine_name(self) -> str:
        return "fake-storyboard"

    def generate(
        self,
        story: StoryPlan,
        context: StoryboardContext,
    ) -> StoryboardPlan:
        del story, context
        return self.result  # type: ignore[return-value]


def test_storyboard_engine_protocol_and_guarded_generation() -> None:
    board = generic_board()
    engine = _FakeStoryboardEngine(board)

    assert isinstance(engine, StoryboardEngine)
    assert (
        generate_storyboard(engine, generic_story(), generic_context())
        == board
    )


def test_generate_storyboard_rejects_non_plan_result() -> None:
    engine = _FakeStoryboardEngine({"not": "a storyboard"})

    with pytest.raises(
        DomainValidationError,
        match="must return a StoryboardPlan",
    ):
        generate_storyboard(engine, generic_story(), generic_context())


@pytest.mark.parametrize(
    "contract_type",
    [StoryboardShot, StoryboardScene, StoryboardPlan],
)
def test_storyboard_json_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_storyboard_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "storyboard.py"
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


def test_kids_puppies_storyboard_is_isolated_and_valid() -> None:
    project = ProjectSpec.from_json(
        _load(KIDS / "examples" / "project.json")
    )
    characters = CharacterBible.from_json(
        _load(KIDS / "bibles" / "character_bible.json")
    )
    universe = UniverseBible.from_json(
        _load(KIDS / "bibles" / "universe_bible.json")
    )
    story = StoryPlan.from_json(
        _load(KIDS / "stories" / "ep0002.story.json")
    )
    board = StoryboardPlan.from_json(
        _load(KIDS / "storyboards" / "ep0002.storyboard.json")
    )

    board.validate_context(story, project, characters, universe)

    assert board.duration_seconds == 60
    assert len(board.scenes) == 5
    assert sum(len(scene.shots) for scene in board.scenes) == 8


def test_generic_storyboard_contains_no_vertical_defaults() -> None:
    content = _load(EXAMPLES / "generic_storyboard_plan.json").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
