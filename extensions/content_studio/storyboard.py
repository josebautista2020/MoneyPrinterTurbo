"""Provider-neutral storyboard contracts for Content Studio AI."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.story import StoryContext, StoryPlan

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_DURATION_TOLERANCE = 0.001


def _require_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DomainValidationError(
            f"{field_name} must match {_ID_RE.pattern!r}; got {value!r}"
        )
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _positive_number(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise DomainValidationError(
            f"{field_name} must be a positive finite number"
        )
    return float(value)


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DomainValidationError(f"{field_name} must be a positive integer")
    return value


def _unique_ids(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_require_id(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _unique_texts(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("metadata must be a mapping")
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(
            "metadata must contain only JSON-compatible values"
        ) from exc
    if not isinstance(decoded, dict):
        raise DomainValidationError("metadata must serialize to a JSON object")
    return decoded


def _payload(
    payload: Mapping[str, Any],
    allowed_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainValidationError("payload must be a mapping")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise DomainValidationError(
            f"unsupported schema_version {version!r}; expected "
            f"{SCHEMA_VERSION!r}"
        )
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


@dataclass(frozen=True, slots=True)
class StoryboardShot(JsonContract):
    """One visual shot within a storyboard scene."""

    shot_id: str
    order: int
    duration_seconds: float
    visual_action: str
    framing: str
    character_ids: tuple[str, ...] = ()
    camera_angle: str | None = None
    camera_movement: str | None = None
    composition_notes: tuple[str, ...] = ()
    continuity_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "shot_id", _require_id(self.shot_id, "shot_id"))
        object.__setattr__(self, "order", _positive_int(self.order, "order"))
        object.__setattr__(
            self,
            "duration_seconds",
            _positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(
            self,
            "visual_action",
            _require_text(self.visual_action, "visual_action"),
        )
        object.__setattr__(
            self,
            "framing",
            _require_text(self.framing, "framing"),
        )
        object.__setattr__(
            self,
            "character_ids",
            _unique_ids(self.character_ids, "character_ids"),
        )
        for name in ("camera_angle", "camera_movement"):
            object.__setattr__(
                self,
                name,
                _optional_text(getattr(self, name), name),
            )
        for name in ("composition_notes", "continuity_notes"):
            object.__setattr__(
                self,
                name,
                _unique_texts(getattr(self, name), name),
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "shot_id",
                "order",
                "duration_seconds",
                "visual_action",
                "framing",
                "character_ids",
                "camera_angle",
                "camera_movement",
                "composition_notes",
                "continuity_notes",
                "metadata",
            },
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        data["composition_notes"] = tuple(
            data.get("composition_notes", ())
        )
        data["continuity_notes"] = tuple(
            data.get("continuity_notes", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class StoryboardScene(JsonContract):
    """Storyboard representation of exactly one StoryBeat."""

    scene_id: str
    beat_id: str
    order: int
    location_id: str
    character_ids: tuple[str, ...]
    shots: tuple[StoryboardShot, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("scene_id", "beat_id", "location_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        object.__setattr__(self, "order", _positive_int(self.order, "order"))
        character_ids = _unique_ids(self.character_ids, "character_ids")
        shots = tuple(self.shots)
        if not shots or not all(
            isinstance(shot, StoryboardShot) for shot in shots
        ):
            raise DomainValidationError(
                "shots must contain at least one StoryboardShot"
            )
        shot_ids = [shot.shot_id for shot in shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise DomainValidationError(
                "shot_id values must be unique within StoryboardScene"
            )
        orders = sorted(shot.order for shot in shots)
        if orders != list(range(1, len(shots) + 1)):
            raise DomainValidationError(
                "shot order values must be contiguous starting at 1"
            )
        allowed = set(character_ids)
        used = {
            character_id
            for shot in shots
            for character_id in shot.character_ids
        }
        unknown = sorted(used - allowed)
        if unknown:
            raise DomainValidationError(
                "shots reference characters outside StoryboardScene: "
                f"{unknown}"
            )

        object.__setattr__(self, "character_ids", character_ids)
        object.__setattr__(self, "shots", shots)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def duration_seconds(self) -> float:
        return sum(shot.duration_seconds for shot in self.shots)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["shots"] = [shot.to_dict() for shot in self.shots]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "scene_id",
                "beat_id",
                "order",
                "location_id",
                "character_ids",
                "shots",
                "metadata",
            },
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        data["shots"] = tuple(
            StoryboardShot.from_dict(item)
            for item in data.get("shots", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class StoryboardPlan(JsonContract):
    """Visual decomposition of a StoryPlan into scenes and shots."""

    story_id: str
    project_id: str
    episode_id: str
    scenes: tuple[StoryboardScene, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("story_id", "project_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        scenes = tuple(self.scenes)
        if not scenes or not all(
            isinstance(scene, StoryboardScene) for scene in scenes
        ):
            raise DomainValidationError(
                "scenes must contain at least one StoryboardScene"
            )
        scene_ids = [scene.scene_id for scene in scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise DomainValidationError(
                "scene_id values must be unique within StoryboardPlan"
            )
        beat_ids = [scene.beat_id for scene in scenes]
        if len(beat_ids) != len(set(beat_ids)):
            raise DomainValidationError(
                "each beat_id must appear exactly once in StoryboardPlan"
            )
        orders = sorted(scene.order for scene in scenes)
        if orders != list(range(1, len(scenes) + 1)):
            raise DomainValidationError(
                "scene order values must be contiguous starting at 1"
            )
        all_shot_ids = [
            shot.shot_id
            for scene in scenes
            for shot in scene.shots
        ]
        if len(all_shot_ids) != len(set(all_shot_ids)):
            raise DomainValidationError(
                "shot_id values must be unique across StoryboardPlan"
            )
        object.__setattr__(self, "scenes", scenes)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def duration_seconds(self) -> float:
        return sum(scene.duration_seconds for scene in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["scenes"] = [scene.to_dict() for scene in self.scenes]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "story_id",
                "project_id",
                "episode_id",
                "scenes",
                "metadata",
            },
        )
        data["scenes"] = tuple(
            StoryboardScene.from_dict(item)
            for item in data.get("scenes", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def validate_story(self, story: StoryPlan) -> None:
        brief = story.brief
        mismatches = []
        if self.story_id != brief.story_id:
            mismatches.append("story_id")
        if self.project_id != brief.project_id:
            mismatches.append("project_id")
        if self.episode_id != brief.episode_id:
            mismatches.append("episode_id")
        if mismatches:
            raise DomainValidationError(
                "StoryboardPlan identity does not match StoryPlan: "
                f"{mismatches}"
            )

        beats = {beat.beat_id: beat for beat in story.beats}
        scene_beats = {scene.beat_id for scene in self.scenes}
        expected_beats = set(beats)
        missing = sorted(expected_beats - scene_beats)
        unknown = sorted(scene_beats - expected_beats)
        if missing or unknown:
            raise DomainValidationError(
                "Storyboard beat coverage mismatch: "
                f"missing={missing}, unknown={unknown}"
            )

        for scene in self.scenes:
            beat = beats[scene.beat_id]
            if scene.order != beat.order:
                raise DomainValidationError(
                    f"Storyboard scene {scene.scene_id!r} order does not "
                    f"match StoryBeat {beat.beat_id!r}"
                )
            if scene.location_id != beat.location_id:
                raise DomainValidationError(
                    f"Storyboard scene {scene.scene_id!r} location does not "
                    f"match StoryBeat {beat.beat_id!r}"
                )
            if set(scene.character_ids) != set(beat.character_ids):
                raise DomainValidationError(
                    f"Storyboard scene {scene.scene_id!r} characters do not "
                    f"match StoryBeat {beat.beat_id!r}"
                )
            if (
                abs(scene.duration_seconds - beat.duration_seconds)
                > _DURATION_TOLERANCE
            ):
                raise DomainValidationError(
                    f"Storyboard scene {scene.scene_id!r} shot duration "
                    f"does not match StoryBeat {beat.beat_id!r}"
                )

    def validate_context(
        self,
        story: StoryPlan,
        project: ProjectSpec,
        character_bible: CharacterBible,
        universe_bible: UniverseBible,
    ) -> None:
        story.validate_context(project, character_bible, universe_bible)
        self.validate_story(story)
        for scene in self.scenes:
            universe_bible.resolve(scene.location_id)
            for character_id in scene.character_ids:
                character_bible.resolve(character_id)


@dataclass(frozen=True, slots=True)
class StoryboardContext:
    """Runtime context for storyboard generation and validation."""

    project: ProjectSpec
    character_bible: CharacterBible
    universe_bible: UniverseBible

    def story_context(self) -> StoryContext:
        return StoryContext(
            self.project,
            self.character_bible,
            self.universe_bible,
        )

    def validate_story(self, story: StoryPlan) -> None:
        self.story_context().validate_plan(story)

    def validate_storyboard(
        self,
        storyboard: StoryboardPlan,
        story: StoryPlan,
    ) -> None:
        storyboard.validate_context(
            story,
            self.project,
            self.character_bible,
            self.universe_bible,
        )


@runtime_checkable
class StoryboardEngine(Protocol):
    """Provider-neutral storyboard generator contract."""

    @property
    def engine_name(self) -> str:
        ...

    def generate(
        self,
        story: StoryPlan,
        context: StoryboardContext,
    ) -> StoryboardPlan:
        ...


def generate_storyboard(
    engine: StoryboardEngine,
    story: StoryPlan,
    context: StoryboardContext,
) -> StoryboardPlan:
    """Validate input and output around any injected storyboard engine."""
    context.validate_story(story)
    plan = engine.generate(story, context)
    if not isinstance(plan, StoryboardPlan):
        raise DomainValidationError(
            "StoryboardEngine must return a StoryboardPlan"
        )
    context.validate_storyboard(plan, story)
    return plan
