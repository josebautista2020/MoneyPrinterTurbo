"""Canonical, provider-neutral domain contracts for Content Studio AI."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Mapping, Self

SCHEMA_VERSION = "1.0.0"

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ASPECT_RATIO_RE = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")
_RESOLUTION_RE = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")


class DomainValidationError(ValueError):
    """Raised when a canonical domain contract violates an invariant."""


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


def _require_optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_language(value: str) -> str:
    value = _require_text(value, "language")
    primary = value.split("-", maxsplit=1)[0]
    if not (2 <= len(primary) <= 3 and primary.isalpha()):
        raise DomainValidationError(
            "language must start with an ISO-like 2-3 letter code"
        )
    return value


def _require_positive_number(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise DomainValidationError(f"{field_name} must be a positive finite number")
    return float(value)


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DomainValidationError(f"{field_name} must be a positive integer")
    return value


def _require_unique_texts(
    values: tuple[str, ...] | list[str],
    field_name: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field_name) for value in values)
    if not allow_empty and not normalized:
        raise DomainValidationError(f"{field_name} must contain at least one value")
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _require_unique_ids(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_require_id(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _require_aspect_ratio(value: str) -> str:
    if not isinstance(value, str) or not _ASPECT_RATIO_RE.fullmatch(value):
        raise DomainValidationError(
            "aspect_ratio must use positive W:H notation, e.g. '9:16'"
        )
    return value


def _require_resolution(value: str) -> str:
    if not isinstance(value, str) or not _RESOLUTION_RE.fullmatch(value):
        raise DomainValidationError(
            "resolution must use positive WIDTHxHEIGHT notation, e.g. '1080x1920'"
        )
    return value


def _json_value(value: Any, field_name: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DomainValidationError(f"{field_name} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DomainValidationError(f"{field_name} keys must be strings")
            result[key] = _json_value(item, field_name)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item, field_name) for item in value]
    raise DomainValidationError(
        f"{field_name} must contain only JSON-compatible values"
    )


def _require_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("metadata must be a mapping")
    return _json_value(value, "metadata")


def _check_schema(payload: Mapping[str, Any]) -> None:
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise DomainValidationError(
            f"unsupported schema_version {version!r}; expected {SCHEMA_VERSION!r}"
        )


def _without_schema(
    payload: Mapping[str, Any],
    *,
    allowed_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainValidationError("payload must be a mapping")
    _check_schema(payload)
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


class JsonContract:
    """JSON round-trip and schema discovery shared by canonical contracts."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = _json_value(asdict(self), "contract")
        payload["schema_version"] = self.SCHEMA_VERSION
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DomainValidationError(f"invalid JSON: {exc.msg}") from exc
        if not isinstance(decoded, Mapping):
            raise DomainValidationError("JSON payload must be an object")
        return cls.from_dict(decoded)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        raise NotImplementedError

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        from extensions.content_studio.schemas import schema_for

        return schema_for(cls.__name__)


@dataclass(frozen=True, slots=True)
class CharacterSpec(JsonContract):
    """Reusable character identity and presentation contract."""

    character_id: str
    name: str
    description: str
    visual_traits: tuple[str, ...] = ()
    personality_traits: tuple[str, ...] = ()
    voice_hint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "character_id",
            _require_id(self.character_id, "character_id"),
        )
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(
            self,
            "description",
            _require_text(self.description, "description"),
        )
        object.__setattr__(
            self,
            "visual_traits",
            _require_unique_texts(self.visual_traits, "visual_traits"),
        )
        object.__setattr__(
            self,
            "personality_traits",
            _require_unique_texts(
                self.personality_traits,
                "personality_traits",
            ),
        )
        object.__setattr__(
            self,
            "voice_hint",
            _require_optional_text(self.voice_hint, "voice_hint"),
        )
        object.__setattr__(self, "metadata", _require_metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _without_schema(
            payload,
            allowed_fields={
                "character_id",
                "name",
                "description",
                "visual_traits",
                "personality_traits",
                "voice_hint",
                "metadata",
            },
        )
        data["visual_traits"] = tuple(data.get("visual_traits", ()))
        data["personality_traits"] = tuple(
            data.get("personality_traits", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SceneSpec(JsonContract):
    """One ordered, independently regenerable scene."""

    scene_id: str
    order: int
    duration_seconds: float
    location: str
    action: str
    character_ids: tuple[str, ...] = ()
    dialogue: str | None = None
    camera: str | None = None
    emotion: str | None = None
    transition: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scene_id",
            _require_id(self.scene_id, "scene_id"),
        )
        object.__setattr__(self, "order", _require_positive_int(self.order, "order"))
        object.__setattr__(
            self,
            "duration_seconds",
            _require_positive_number(
                self.duration_seconds,
                "duration_seconds",
            ),
        )
        object.__setattr__(
            self,
            "location",
            _require_text(self.location, "location"),
        )
        object.__setattr__(self, "action", _require_text(self.action, "action"))
        object.__setattr__(
            self,
            "character_ids",
            _require_unique_ids(self.character_ids, "character_ids"),
        )
        for name in ("dialogue", "camera", "emotion", "transition"):
            object.__setattr__(
                self,
                name,
                _require_optional_text(getattr(self, name), name),
            )
        object.__setattr__(self, "metadata", _require_metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _without_schema(
            payload,
            allowed_fields={
                "scene_id",
                "order",
                "duration_seconds",
                "location",
                "action",
                "character_ids",
                "dialogue",
                "camera",
                "emotion",
                "transition",
                "metadata",
            },
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class EpisodeSpec(JsonContract):
    """Episode contract that references its project and declared characters."""

    episode_id: str
    project_id: str
    title: str
    language: str
    duration_target_seconds: float
    scenes: tuple[SceneSpec, ...]
    character_ids: tuple[str, ...] = ()
    lesson: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "episode_id",
            _require_id(self.episode_id, "episode_id"),
        )
        object.__setattr__(
            self,
            "project_id",
            _require_id(self.project_id, "project_id"),
        )
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "language", _require_language(self.language))
        object.__setattr__(
            self,
            "duration_target_seconds",
            _require_positive_number(
                self.duration_target_seconds,
                "duration_target_seconds",
            ),
        )

        scenes = tuple(self.scenes)
        if not scenes or not all(isinstance(scene, SceneSpec) for scene in scenes):
            raise DomainValidationError(
                "scenes must contain at least one SceneSpec"
            )

        scene_ids = [scene.scene_id for scene in scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise DomainValidationError(
                "scene_id values must be unique within an episode"
            )

        orders = [scene.order for scene in scenes]
        if sorted(orders) != list(range(1, len(scenes) + 1)):
            raise DomainValidationError(
                "scene order values must be contiguous starting at 1"
            )

        character_ids = _require_unique_ids(
            self.character_ids,
            "character_ids",
        )
        referenced = {
            character_id
            for scene in scenes
            for character_id in scene.character_ids
        }
        unknown = sorted(referenced - set(character_ids))
        if unknown:
            raise DomainValidationError(
                f"scenes reference undeclared episode character_ids: {unknown}"
            )

        object.__setattr__(self, "scenes", scenes)
        object.__setattr__(self, "character_ids", character_ids)
        object.__setattr__(
            self,
            "lesson",
            _require_optional_text(self.lesson, "lesson"),
        )
        object.__setattr__(self, "metadata", _require_metadata(self.metadata))

    @property
    def duration_seconds(self) -> float:
        return sum(scene.duration_seconds for scene in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["scenes"] = [scene.to_dict() for scene in self.scenes]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _without_schema(
            payload,
            allowed_fields={
                "episode_id",
                "project_id",
                "title",
                "language",
                "duration_target_seconds",
                "scenes",
                "character_ids",
                "lesson",
                "metadata",
            },
        )
        data["scenes"] = tuple(
            SceneSpec.from_dict(item)
            for item in data.get("scenes", ())
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ProjectSpec(JsonContract):
    """Top-level project contract independent of execution providers."""

    project_id: str
    title: str
    language: str
    target_platforms: tuple[str, ...]
    aspect_ratio: str
    resolution: str
    characters: tuple[CharacterSpec, ...] = ()
    episodes: tuple[EpisodeSpec, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_id",
            _require_id(self.project_id, "project_id"),
        )
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "language", _require_language(self.language))
        object.__setattr__(
            self,
            "target_platforms",
            _require_unique_texts(
                self.target_platforms,
                "target_platforms",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "aspect_ratio",
            _require_aspect_ratio(self.aspect_ratio),
        )
        object.__setattr__(
            self,
            "resolution",
            _require_resolution(self.resolution),
        )

        characters = tuple(self.characters)
        if not all(isinstance(item, CharacterSpec) for item in characters):
            raise DomainValidationError(
                "characters must contain CharacterSpec values"
            )
        character_ids = [item.character_id for item in characters]
        if len(character_ids) != len(set(character_ids)):
            raise DomainValidationError(
                "character_id values must be unique within a project"
            )

        episodes = tuple(self.episodes)
        if not all(isinstance(item, EpisodeSpec) for item in episodes):
            raise DomainValidationError(
                "episodes must contain EpisodeSpec values"
            )
        episode_ids = [item.episode_id for item in episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise DomainValidationError(
                "episode_id values must be unique within a project"
            )

        wrong_project = sorted(
            episode.episode_id
            for episode in episodes
            if episode.project_id != self.project_id
        )
        if wrong_project:
            raise DomainValidationError(
                "episodes reference a different project_id: "
                f"{wrong_project}"
            )

        known_characters = set(character_ids)
        referenced_characters = {
            character_id
            for episode in episodes
            for character_id in episode.character_ids
        }
        unknown = sorted(referenced_characters - known_characters)
        if unknown:
            raise DomainValidationError(
                f"episodes reference unknown project character_ids: {unknown}"
            )

        object.__setattr__(self, "characters", characters)
        object.__setattr__(self, "episodes", episodes)
        object.__setattr__(self, "metadata", _require_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["characters"] = [
            character.to_dict() for character in self.characters
        ]
        payload["episodes"] = [
            episode.to_dict() for episode in self.episodes
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _without_schema(
            payload,
            allowed_fields={
                "project_id",
                "title",
                "language",
                "target_platforms",
                "aspect_ratio",
                "resolution",
                "characters",
                "episodes",
                "metadata",
            },
        )
        data["target_platforms"] = tuple(
            data.get("target_platforms", ())
        )
        data["characters"] = tuple(
            CharacterSpec.from_dict(item)
            for item in data.get("characters", ())
        )
        data["episodes"] = tuple(
            EpisodeSpec.from_dict(item)
            for item in data.get("episodes", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc
