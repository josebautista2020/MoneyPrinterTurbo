import json

import pytest

from extensions.content_studio.domain import (
    CharacterSpec,
    DomainValidationError,
    EpisodeSpec,
    ProjectSpec,
    SCHEMA_VERSION,
    SceneSpec,
)


def sample_project() -> ProjectSpec:
    character = CharacterSpec(
        character_id="guide-1",
        name="Guide",
        description="A neutral presenter used for contract testing.",
        visual_traits=("blue jacket",),
        personality_traits=("calm", "clear"),
        voice_hint="clear adult voice",
    )
    first_scene = SceneSpec(
        scene_id="scene-1",
        order=1,
        duration_seconds=10,
        location="studio",
        action="The guide introduces the topic.",
        character_ids=(character.character_id,),
        dialogue="Welcome.",
        camera="medium shot",
        emotion="friendly",
        transition="cut",
    )
    second_scene = SceneSpec(
        scene_id="scene-2",
        order=2,
        duration_seconds=20,
        location="studio",
        action="The guide explains the main idea.",
        character_ids=(character.character_id,),
    )
    episode = EpisodeSpec(
        episode_id="episode-1",
        project_id="project-1",
        title="Pilot",
        language="en-US",
        duration_target_seconds=30,
        scenes=(first_scene, second_scene),
        character_ids=(character.character_id,),
    )
    return ProjectSpec(
        project_id="project-1",
        title="Generic Core Example",
        language="en-US",
        target_platforms=("short-video",),
        aspect_ratio="9:16",
        resolution="1080x1920",
        characters=(character,),
        episodes=(episode,),
    )


def test_project_round_trip_json() -> None:
    project = sample_project()
    restored = ProjectSpec.from_json(project.to_json())

    assert restored == project
    assert restored.episodes[0].duration_seconds == 30
    assert json.loads(project.to_json())["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize(
    "contract",
    [
        CharacterSpec(
            "guide-1",
            "Guide",
            "A neutral presenter.",
        ),
        SceneSpec(
            "scene-1",
            1,
            5,
            "studio",
            "Introduce the topic.",
        ),
    ],
)
def test_individual_contracts_round_trip(contract: object) -> None:
    restored = type(contract).from_json(contract.to_json())
    assert restored == contract


def test_scene_reference_must_be_declared_by_episode() -> None:
    scene = SceneSpec(
        "scene-1",
        1,
        5,
        "studio",
        "Introduce the topic.",
        ("missing",),
    )
    with pytest.raises(DomainValidationError, match="undeclared episode"):
        EpisodeSpec(
            "episode-1",
            "project-1",
            "Episode",
            "en",
            5,
            (scene,),
        )


def test_episode_reference_must_exist_in_project() -> None:
    scene = SceneSpec(
        "scene-1",
        1,
        5,
        "studio",
        "Introduce the topic.",
        ("guide-1",),
    )
    episode = EpisodeSpec(
        "episode-1",
        "project-1",
        "Episode",
        "en",
        5,
        (scene,),
        ("guide-1",),
    )
    with pytest.raises(DomainValidationError, match="unknown project"):
        ProjectSpec(
            project_id="project-1",
            title="Project",
            language="en",
            target_platforms=("short-video",),
            aspect_ratio="9:16",
            resolution="1080x1920",
            episodes=(episode,),
        )


def test_episode_project_reference_must_match_parent() -> None:
    scene = SceneSpec(
        "scene-1",
        1,
        5,
        "studio",
        "Introduce the topic.",
    )
    episode = EpisodeSpec(
        "episode-1",
        "another-project",
        "Episode",
        "en",
        5,
        (scene,),
    )
    with pytest.raises(DomainValidationError, match="different project_id"):
        ProjectSpec(
            project_id="project-1",
            title="Project",
            language="en",
            target_platforms=("short-video",),
            aspect_ratio="9:16",
            resolution="1080x1920",
            episodes=(episode,),
        )


def test_scene_order_must_be_contiguous() -> None:
    scenes = (
        SceneSpec("scene-1", 1, 5, "studio", "First action."),
        SceneSpec("scene-2", 3, 5, "studio", "Second action."),
    )
    with pytest.raises(DomainValidationError, match="contiguous"):
        EpisodeSpec(
            "episode-1",
            "project-1",
            "Episode",
            "en",
            10,
            scenes,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution", "vertical"),
        ("aspect_ratio", "vertical"),
        ("duration", 0),
    ],
)
def test_invalid_media_constraints_are_rejected(
    field: str,
    value: object,
) -> None:
    if field == "duration":
        with pytest.raises(DomainValidationError):
            SceneSpec(
                "scene-1",
                1,
                value,  # type: ignore[arg-type]
                "studio",
                "Action.",
            )
        return

    kwargs = {
        "project_id": "project-1",
        "title": "Project",
        "language": "en",
        "target_platforms": ("short-video",),
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
    }
    kwargs[field] = value
    with pytest.raises(DomainValidationError):
        ProjectSpec(**kwargs)  # type: ignore[arg-type]


def test_metadata_must_be_json_compatible() -> None:
    with pytest.raises(DomainValidationError, match="JSON-compatible"):
        CharacterSpec(
            "guide-1",
            "Guide",
            "A presenter.",
            metadata={"bad": object()},
        )


def test_schema_version_is_required_and_versioned() -> None:
    payload = sample_project().to_dict()
    payload["schema_version"] = "2.0.0"

    with pytest.raises(DomainValidationError, match="unsupported schema_version"):
        ProjectSpec.from_dict(payload)

    payload.pop("schema_version")
    with pytest.raises(DomainValidationError, match="unsupported schema_version"):
        ProjectSpec.from_dict(payload)


def test_unknown_fields_are_rejected() -> None:
    payload = sample_project().to_dict()
    payload["provider"] = "moneyprinterturbo"

    with pytest.raises(DomainValidationError, match="unknown fields"):
        ProjectSpec.from_dict(payload)
