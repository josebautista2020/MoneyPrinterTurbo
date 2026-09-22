import json

import pytest

from extensions.content_studio.domain import (
    CharacterSpec,
    DomainValidationError,
    EpisodeSpec,
    ProjectSpec,
    SceneSpec,
)


def sample_project() -> ProjectSpec:
    character = CharacterSpec(
        character_id="guide-1",
        name="Guide",
        description="A generic narrator used only for contract testing.",
        traits=("calm", "clear"),
    )
    scene = SceneSpec(
        scene_id="scene-1",
        title="Opening",
        description="Introduce the topic.",
        duration_seconds=12.5,
        character_ids=(character.character_id,),
    )
    episode = EpisodeSpec(
        episode_id="episode-1",
        title="Pilot",
        scenes=(scene,),
        language="en-US",
    )
    return ProjectSpec(
        project_id="project-1",
        title="Generic Core Example",
        episodes=(episode,),
        characters=(character,),
        platforms=("short-video",),
        language="en-US",
        aspect_ratio="9:16",
    )


def test_project_round_trip_json() -> None:
    project = sample_project()
    restored = ProjectSpec.from_json(project.to_json())
    assert restored == project
    assert restored.episodes[0].duration_seconds == 12.5
    assert json.loads(project.to_json())["schema_version"] == "1.0"


def test_unknown_character_reference_is_rejected() -> None:
    scene = SceneSpec("scene-1", "Scene", "Description", 1, ("missing",))
    episode = EpisodeSpec("episode-1", "Episode", (scene,))
    with pytest.raises(DomainValidationError, match="unknown character_ids"):
        ProjectSpec("project-1", "Project", (episode,))


def test_duplicate_scene_ids_are_rejected() -> None:
    scene = SceneSpec("scene-1", "Scene", "Description", 1)
    with pytest.raises(DomainValidationError, match="scene_id values must be unique"):
        EpisodeSpec("episode-1", "Episode", (scene, scene))


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration", 0), ("duration", -1), ("aspect_ratio", "vertical")],
)
def test_invalid_media_constraints_are_rejected(field: str, value: object) -> None:
    if field == "duration":
        with pytest.raises(DomainValidationError):
            SceneSpec("scene-1", "Scene", "Description", value)  # type: ignore[arg-type]
    else:
        episode = EpisodeSpec(
            "episode-1", "Episode", (SceneSpec("scene-1", "Scene", "Description", 1),)
        )
        with pytest.raises(DomainValidationError):
            ProjectSpec("project-1", "Project", (episode,), aspect_ratio=value)  # type: ignore[arg-type]


def test_unsupported_schema_version_is_rejected() -> None:
    payload = sample_project().to_dict()
    payload["schema_version"] = "2.0"
    with pytest.raises(DomainValidationError, match="unsupported schema_version"):
        ProjectSpec.from_dict(payload)
