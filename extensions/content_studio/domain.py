"""Canonical, provider-neutral domain contracts for Content Studio AI.

These dataclasses deliberately avoid imports from MoneyPrinterTurbo ``app.*`` and from
any product vertical. They are JSON-serializable contracts owned by the reusable Core.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Mapping

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ASPECT_RATIO_RE = re.compile(r"^[1-9]\d*:[1-9]\d*$")


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


def _require_language(value: str) -> str:
    value = _require_text(value, "language")
    parts = value.split("-")
    if not (2 <= len(parts[0]) <= 3 and parts[0].isalpha()):
        raise DomainValidationError("language must start with an ISO-like 2-3 letter code")
    return value


def _require_aspect_ratio(value: str) -> str:
    if not isinstance(value, str) or not _ASPECT_RATIO_RE.fullmatch(value):
        raise DomainValidationError("aspect_ratio must use positive W:H notation, e.g. '9:16'")
    return value


class JsonContract:
    """Minimal JSON round-trip behavior shared by canonical contracts."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = self.SCHEMA_VERSION
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class CharacterSpec(JsonContract):
    character_id: str
    name: str
    description: str
    traits: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_id", _require_id(self.character_id, "character_id"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        object.__setattr__(self, "traits", tuple(_require_text(v, "trait") for v in self.traits))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterSpec":
        _check_schema(payload)
        data = _without_schema(payload)
        data["traits"] = tuple(data.get("traits", ()))
        return cls(**data)


@dataclass(frozen=True)
class SceneSpec(JsonContract):
    scene_id: str
    title: str
    description: str
    duration_seconds: float
    character_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_id", _require_id(self.scene_id, "scene_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        if isinstance(self.duration_seconds, bool) or not isinstance(self.duration_seconds, (int, float)) or self.duration_seconds <= 0:
            raise DomainValidationError("duration_seconds must be a positive number")
        object.__setattr__(self, "duration_seconds", float(self.duration_seconds))
        ids = tuple(_require_id(v, "character_id") for v in self.character_ids)
        if len(ids) != len(set(ids)):
            raise DomainValidationError("character_ids must not contain duplicates")
        object.__setattr__(self, "character_ids", ids)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneSpec":
        _check_schema(payload)
        data = _without_schema(payload)
        data["character_ids"] = tuple(data.get("character_ids", ()))
        return cls(**data)


@dataclass(frozen=True)
class EpisodeSpec(JsonContract):
    episode_id: str
    title: str
    scenes: tuple[SceneSpec, ...]
    language: str = "en"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", _require_id(self.episode_id, "episode_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "language", _require_language(self.language))
        scenes = tuple(self.scenes)
        if not scenes or not all(isinstance(scene, SceneSpec) for scene in scenes):
            raise DomainValidationError("scenes must contain at least one SceneSpec")
        ids = [scene.scene_id for scene in scenes]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("scene_id values must be unique within an episode")
        object.__setattr__(self, "scenes", scenes)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def duration_seconds(self) -> float:
        return sum(scene.duration_seconds for scene in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["scenes"] = [scene.to_dict() for scene in self.scenes]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EpisodeSpec":
        _check_schema(payload)
        data = _without_schema(payload)
        data["scenes"] = tuple(SceneSpec.from_dict(v) for v in data.get("scenes", ()))
        return cls(**data)


@dataclass(frozen=True)
class ProjectSpec(JsonContract):
    project_id: str
    title: str
    episodes: tuple[EpisodeSpec, ...]
    characters: tuple[CharacterSpec, ...] = ()
    platforms: tuple[str, ...] = ()
    language: str = "en"
    aspect_ratio: str = "9:16"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _require_id(self.project_id, "project_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "language", _require_language(self.language))
        object.__setattr__(self, "aspect_ratio", _require_aspect_ratio(self.aspect_ratio))

        episodes = tuple(self.episodes)
        if not episodes or not all(isinstance(v, EpisodeSpec) for v in episodes):
            raise DomainValidationError("episodes must contain at least one EpisodeSpec")
        episode_ids = [v.episode_id for v in episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise DomainValidationError("episode_id values must be unique within a project")

        characters = tuple(self.characters)
        if not all(isinstance(v, CharacterSpec) for v in characters):
            raise DomainValidationError("characters must contain CharacterSpec values")
        character_ids = [v.character_id for v in characters]
        if len(character_ids) != len(set(character_ids)):
            raise DomainValidationError("character_id values must be unique within a project")
        known = set(character_ids)
        referenced = {cid for episode in episodes for scene in episode.scenes for cid in scene.character_ids}
        unknown = sorted(referenced - known)
        if unknown:
            raise DomainValidationError(f"scenes reference unknown character_ids: {unknown}")

        platforms = tuple(_require_text(v, "platform") for v in self.platforms)
        if len(platforms) != len(set(platforms)):
            raise DomainValidationError("platforms must not contain duplicates")

        object.__setattr__(self, "episodes", episodes)
        object.__setattr__(self, "characters", characters)
        object.__setattr__(self, "platforms", platforms)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["episodes"] = [episode.to_dict() for episode in self.episodes]
        payload["characters"] = [character.to_dict() for character in self.characters]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectSpec":
        _check_schema(payload)
        data = _without_schema(payload)
        data["episodes"] = tuple(EpisodeSpec.from_dict(v) for v in data.get("episodes", ()))
        data["characters"] = tuple(CharacterSpec.from_dict(v) for v in data.get("characters", ()))
        data["platforms"] = tuple(data.get("platforms", ()))
        return cls(**data)

    @classmethod
    def from_json(cls, payload: str) -> "ProjectSpec":
        return cls.from_dict(json.loads(payload))


def _check_schema(payload: Mapping[str, Any]) -> None:
    version = payload.get("schema_version", JsonContract.SCHEMA_VERSION)
    if version != JsonContract.SCHEMA_VERSION:
        raise DomainValidationError(
            f"unsupported schema_version {version!r}; expected {JsonContract.SCHEMA_VERSION!r}"
        )


def _without_schema(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.pop("schema_version", None)
    return data
