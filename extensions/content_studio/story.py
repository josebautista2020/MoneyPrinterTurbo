"""Provider-neutral story planning and validation for Content Studio AI."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    EpisodeSpec,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
    SceneSpec,
)

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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
    *,
    required: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(_require_id(value, field_name) for value in values)
    if required and not normalized:
        raise DomainValidationError(f"{field_name} must contain at least one value")
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
class StoryBrief(JsonContract):
    """Intent and allowed narrative scope for one episode story."""

    story_id: str
    project_id: str
    episode_id: str
    title: str
    premise: str
    language: str
    duration_target_seconds: float
    location_ids: tuple[str, ...]
    character_ids: tuple[str, ...] = ()
    tone: tuple[str, ...] = ()
    lesson: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("story_id", "project_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        for name in ("title", "premise", "language"):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "duration_target_seconds",
            _positive_number(
                self.duration_target_seconds,
                "duration_target_seconds",
            ),
        )
        object.__setattr__(
            self,
            "location_ids",
            _unique_ids(
                self.location_ids,
                "location_ids",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "character_ids",
            _unique_ids(self.character_ids, "character_ids"),
        )
        object.__setattr__(
            self,
            "tone",
            _unique_texts(self.tone, "tone"),
        )
        object.__setattr__(
            self,
            "lesson",
            _optional_text(self.lesson, "lesson"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "story_id",
                "project_id",
                "episode_id",
                "title",
                "premise",
                "language",
                "duration_target_seconds",
                "location_ids",
                "character_ids",
                "tone",
                "lesson",
                "metadata",
            },
        )
        data["location_ids"] = tuple(data.get("location_ids", ()))
        data["character_ids"] = tuple(data.get("character_ids", ()))
        data["tone"] = tuple(data.get("tone", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class StoryBeat(JsonContract):
    """One ordered narrative beat that can compile into a scene."""

    beat_id: str
    order: int
    purpose: str
    summary: str
    duration_seconds: float
    location_id: str
    character_ids: tuple[str, ...] = ()
    dialogue_hint: str | None = None
    emotion: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "beat_id", _require_id(self.beat_id, "beat_id"))
        object.__setattr__(self, "order", _positive_int(self.order, "order"))
        for name in ("purpose", "summary"):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "duration_seconds",
            _positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(
            self,
            "location_id",
            _require_id(self.location_id, "location_id"),
        )
        object.__setattr__(
            self,
            "character_ids",
            _unique_ids(self.character_ids, "character_ids"),
        )
        object.__setattr__(
            self,
            "dialogue_hint",
            _optional_text(self.dialogue_hint, "dialogue_hint"),
        )
        object.__setattr__(
            self,
            "emotion",
            _optional_text(self.emotion, "emotion"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "beat_id",
                "order",
                "purpose",
                "summary",
                "duration_seconds",
                "location_id",
                "character_ids",
                "dialogue_hint",
                "emotion",
                "metadata",
            },
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class StoryPlan(JsonContract):
    """Validated narrative plan that compiles into an EpisodeSpec."""

    brief: StoryBrief
    beats: tuple[StoryBeat, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.brief, StoryBrief):
            raise DomainValidationError("brief must be a StoryBrief")
        beats = tuple(self.beats)
        if not beats or not all(isinstance(beat, StoryBeat) for beat in beats):
            raise DomainValidationError(
                "beats must contain at least one StoryBeat"
            )
        beat_ids = [beat.beat_id for beat in beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise DomainValidationError(
                "beat_id values must be unique within StoryPlan"
            )
        orders = sorted(beat.order for beat in beats)
        if orders != list(range(1, len(beats) + 1)):
            raise DomainValidationError(
                "beat order values must be contiguous starting at 1"
            )

        allowed_characters = set(self.brief.character_ids)
        used_characters = {
            character_id
            for beat in beats
            for character_id in beat.character_ids
        }
        unknown_characters = sorted(used_characters - allowed_characters)
        if unknown_characters:
            raise DomainValidationError(
                "beats reference characters outside StoryBrief: "
                f"{unknown_characters}"
            )

        allowed_locations = set(self.brief.location_ids)
        unknown_locations = sorted(
            {
                beat.location_id
                for beat in beats
                if beat.location_id not in allowed_locations
            }
        )
        if unknown_locations:
            raise DomainValidationError(
                "beats reference locations outside StoryBrief: "
                f"{unknown_locations}"
            )

        object.__setattr__(self, "beats", beats)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def duration_seconds(self) -> float:
        return sum(beat.duration_seconds for beat in self.beats)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["brief"] = self.brief.to_dict()
        payload["beats"] = [beat.to_dict() for beat in self.beats]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"brief", "beats", "metadata"})
        try:
            data["brief"] = StoryBrief.from_dict(data["brief"])
        except KeyError as exc:
            raise DomainValidationError("brief is required") from exc
        data["beats"] = tuple(
            StoryBeat.from_dict(item) for item in data.get("beats", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def validate_context(
        self,
        project: ProjectSpec,
        character_bible: CharacterBible,
        universe_bible: UniverseBible,
    ) -> None:
        brief = self.brief
        if project.project_id != brief.project_id:
            raise DomainValidationError(
                "StoryBrief project_id does not match ProjectSpec"
            )
        if character_bible.project_id != project.project_id:
            raise DomainValidationError(
                "CharacterBible project_id does not match ProjectSpec"
            )
        if universe_bible.project_id != project.project_id:
            raise DomainValidationError(
                "UniverseBible project_id does not match ProjectSpec"
            )

        project_characters = {
            character.character_id for character in project.characters
        }
        unknown_characters = sorted(
            set(brief.character_ids) - project_characters
        )
        if unknown_characters:
            raise DomainValidationError(
                "StoryBrief references unknown project characters: "
                f"{unknown_characters}"
            )
        for character_id in brief.character_ids:
            character_bible.resolve(character_id)

        for location_id in brief.location_ids:
            universe_bible.resolve(location_id)

    def to_episode_spec(self) -> EpisodeSpec:
        scenes = tuple(
            SceneSpec(
                scene_id=beat.beat_id,
                order=beat.order,
                duration_seconds=beat.duration_seconds,
                location=beat.location_id,
                action=beat.summary,
                character_ids=beat.character_ids,
                dialogue=beat.dialogue_hint,
                emotion=beat.emotion,
                metadata={
                    "story_id": self.brief.story_id,
                    "story_purpose": beat.purpose,
                },
            )
            for beat in self.beats
        )
        metadata = dict(self.metadata)
        metadata["story_id"] = self.brief.story_id
        metadata["premise"] = self.brief.premise
        metadata["tone"] = list(self.brief.tone)

        return EpisodeSpec(
            episode_id=self.brief.episode_id,
            project_id=self.brief.project_id,
            title=self.brief.title,
            language=self.brief.language,
            duration_target_seconds=self.brief.duration_target_seconds,
            scenes=scenes,
            character_ids=self.brief.character_ids,
            lesson=self.brief.lesson,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class StoryContext:
    """Non-serialized runtime context used to validate story generation."""

    project: ProjectSpec
    character_bible: CharacterBible
    universe_bible: UniverseBible

    def validate_brief(self, brief: StoryBrief) -> None:
        empty_plan = StoryPlan(
            brief=brief,
            beats=(
                StoryBeat(
                    beat_id="validation",
                    order=1,
                    purpose="validation",
                    summary="Validation placeholder.",
                    duration_seconds=1,
                    location_id=brief.location_ids[0],
                    character_ids=(),
                ),
            ),
        )
        empty_plan.validate_context(
            self.project,
            self.character_bible,
            self.universe_bible,
        )

    def validate_plan(self, plan: StoryPlan) -> None:
        plan.validate_context(
            self.project,
            self.character_bible,
            self.universe_bible,
        )


@runtime_checkable
class StoryEngine(Protocol):
    """Provider-neutral story generator contract."""

    @property
    def engine_name(self) -> str:
        ...

    def generate(
        self,
        brief: StoryBrief,
        context: StoryContext,
    ) -> StoryPlan:
        ...


def generate_story(
    engine: StoryEngine,
    brief: StoryBrief,
    context: StoryContext,
) -> StoryPlan:
    """Validate input and output around any injected story engine."""
    context.validate_brief(brief)
    plan = engine.generate(brief, context)
    if not isinstance(plan, StoryPlan):
        raise DomainValidationError("StoryEngine must return a StoryPlan")
    if plan.brief != brief:
        raise DomainValidationError(
            "StoryEngine returned a plan for a different StoryBrief"
        )
    context.validate_plan(plan)
    return plan
