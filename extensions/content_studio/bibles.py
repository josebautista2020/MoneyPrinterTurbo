"""Provider-neutral Character Bible and Universe Bible contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Self

from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
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


def _require_optional_text(
    value: str | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _unique_texts(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_require_text(item, field_name) for item in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _unique_ids(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(_require_id(item, field_name) for item in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _json_safe(value: Any, field_name: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise DomainValidationError(
                f"{field_name} contains a non-finite number"
            )
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DomainValidationError(
                    f"{field_name} keys must be strings"
                )
            result[key] = _json_safe(item, field_name)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, field_name) for item in value]
    raise DomainValidationError(
        f"{field_name} must contain only JSON-compatible values"
    )


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("metadata must be a mapping")
    result = _json_safe(value)
    json.dumps(result, allow_nan=False)
    return result


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


def _register_aliases(
    canonical_id: str,
    aliases: tuple[str, ...],
    index: dict[str, str],
    kind: str,
) -> None:
    for value in (canonical_id, *aliases):
        key = value.casefold()
        owner = index.get(key)
        if owner is not None and owner != canonical_id:
            raise DomainValidationError(
                f"ambiguous {kind} alias {value!r}: "
                f"{owner!r} and {canonical_id!r}"
            )
        index[key] = canonical_id


@dataclass(frozen=True, slots=True)
class CharacterProfile(JsonContract):
    """Persistent consistency constraints for one canonical character."""

    character_id: str
    aliases: tuple[str, ...] = ()
    signature_features: tuple[str, ...] = ()
    wardrobe: tuple[str, ...] = ()
    personality_notes: tuple[str, ...] = ()
    voice_consistency: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    reference_asset_ids: tuple[str, ...] = ()
    notes: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "character_id",
            _require_id(self.character_id, "character_id"),
        )
        for name in (
            "aliases",
            "signature_features",
            "wardrobe",
            "personality_notes",
            "voice_consistency",
            "forbidden_changes",
        ):
            object.__setattr__(
                self,
                name,
                _unique_texts(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "reference_asset_ids",
            _unique_ids(
                self.reference_asset_ids,
                "reference_asset_ids",
            ),
        )
        object.__setattr__(
            self,
            "notes",
            _require_optional_text(self.notes, "notes"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "character_id",
                "aliases",
                "signature_features",
                "wardrobe",
                "personality_notes",
                "voice_consistency",
                "forbidden_changes",
                "reference_asset_ids",
                "notes",
                "metadata",
            },
        )
        for name in (
            "aliases",
            "signature_features",
            "wardrobe",
            "personality_notes",
            "voice_consistency",
            "forbidden_changes",
            "reference_asset_ids",
        ):
            data[name] = tuple(data.get(name, ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class CharacterBible(JsonContract):
    """Project-scoped persistent character consistency bible."""

    project_id: str
    profiles: tuple[CharacterProfile, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_id",
            _require_id(self.project_id, "project_id"),
        )
        profiles = tuple(self.profiles)
        if not profiles or not all(
            isinstance(profile, CharacterProfile) for profile in profiles
        ):
            raise DomainValidationError(
                "profiles must contain at least one CharacterProfile"
            )
        ids = [profile.character_id for profile in profiles]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(
                "character_id values must be unique within CharacterBible"
            )
        alias_index: dict[str, str] = {}
        for profile in profiles:
            _register_aliases(
                profile.character_id,
                profile.aliases,
                alias_index,
                "character",
            )
        object.__setattr__(self, "profiles", profiles)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["profiles"] = [
            profile.to_dict() for profile in self.profiles
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"project_id", "profiles", "metadata"},
        )
        data["profiles"] = tuple(
            CharacterProfile.from_dict(item)
            for item in data.get("profiles", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def resolve(self, character_ref: str) -> CharacterProfile:
        ref = _require_text(character_ref, "character_ref").casefold()
        for profile in self.profiles:
            if profile.character_id.casefold() == ref:
                return profile
            if ref in {alias.casefold() for alias in profile.aliases}:
                return profile
        raise DomainValidationError(
            f"unknown character reference: {character_ref!r}"
        )

    def validate_project(self, project: ProjectSpec) -> None:
        if project.project_id != self.project_id:
            raise DomainValidationError(
                "CharacterBible project_id does not match ProjectSpec"
            )
        expected = {character.character_id for character in project.characters}
        actual = {profile.character_id for profile in self.profiles}
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            raise DomainValidationError(
                "CharacterBible coverage mismatch: "
                f"missing={missing}, unknown={unknown}"
            )


@dataclass(frozen=True, slots=True)
class LocationProfile(JsonContract):
    """Persistent visual/narrative constraints for one universe location."""

    location_id: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    visual_traits: tuple[str, ...] = ()
    ambience: tuple[str, ...] = ()
    consistency_rules: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    reference_asset_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "location_id",
            _require_id(self.location_id, "location_id"),
        )
        object.__setattr__(
            self,
            "description",
            _require_text(self.description, "description"),
        )
        for name in (
            "aliases",
            "visual_traits",
            "ambience",
            "consistency_rules",
            "forbidden_changes",
        ):
            object.__setattr__(
                self,
                name,
                _unique_texts(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "reference_asset_ids",
            _unique_ids(
                self.reference_asset_ids,
                "reference_asset_ids",
            ),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "location_id",
                "aliases",
                "description",
                "visual_traits",
                "ambience",
                "consistency_rules",
                "forbidden_changes",
                "reference_asset_ids",
                "metadata",
            },
        )
        for name in (
            "aliases",
            "visual_traits",
            "ambience",
            "consistency_rules",
            "forbidden_changes",
            "reference_asset_ids",
        ):
            data[name] = tuple(data.get(name, ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class UniverseBible(JsonContract):
    """Project-scoped location and world consistency bible."""

    project_id: str
    locations: tuple[LocationProfile, ...]
    world_rules: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_id",
            _require_id(self.project_id, "project_id"),
        )
        locations = tuple(self.locations)
        if not locations or not all(
            isinstance(location, LocationProfile)
            for location in locations
        ):
            raise DomainValidationError(
                "locations must contain at least one LocationProfile"
            )
        ids = [location.location_id for location in locations]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(
                "location_id values must be unique within UniverseBible"
            )
        alias_index: dict[str, str] = {}
        for location in locations:
            _register_aliases(
                location.location_id,
                location.aliases,
                alias_index,
                "location",
            )
        object.__setattr__(self, "locations", locations)
        object.__setattr__(
            self,
            "world_rules",
            _unique_texts(self.world_rules, "world_rules"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["locations"] = [
            location.to_dict() for location in self.locations
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"project_id", "locations", "world_rules", "metadata"},
        )
        data["locations"] = tuple(
            LocationProfile.from_dict(item)
            for item in data.get("locations", ())
        )
        data["world_rules"] = tuple(data.get("world_rules", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def resolve(self, location_ref: str) -> LocationProfile:
        ref = _require_text(location_ref, "location_ref").casefold()
        for location in self.locations:
            if location.location_id.casefold() == ref:
                return location
            if ref in {alias.casefold() for alias in location.aliases}:
                return location
        raise DomainValidationError(
            f"unknown location reference: {location_ref!r}"
        )

    def validate_project(self, project: ProjectSpec) -> None:
        if project.project_id != self.project_id:
            raise DomainValidationError(
                "UniverseBible project_id does not match ProjectSpec"
            )
        unresolved: set[str] = set()
        for episode in project.episodes:
            for scene in episode.scenes:
                try:
                    self.resolve(scene.location)
                except DomainValidationError:
                    unresolved.add(scene.location)
        if unresolved:
            raise DomainValidationError(
                "UniverseBible cannot resolve scene locations: "
                f"{sorted(unresolved)}"
            )
