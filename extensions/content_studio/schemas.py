"""JSON Schema definitions for canonical Content Studio contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from extensions.content_studio.domain import SCHEMA_VERSION

_SCHEMA_BASE = "https://content-studio.ai/schemas"

_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$"
_ASPECT_RATIO_PATTERN = r"^[1-9]\\d*:[1-9]\\d*$"
_RESOLUTION_PATTERN = r"^[1-9]\\d*x[1-9]\\d*$"

_METADATA = {
    "type": "object",
    "additionalProperties": True,
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "CharacterSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_SCHEMA_BASE}/character-spec/{SCHEMA_VERSION}",
        "title": "CharacterSpec",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "character_id",
            "name",
            "description",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "character_id": {"type": "string", "pattern": _ID_PATTERN},
            "name": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
            "visual_traits": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "personality_traits": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "voice_hint": {
                "type": ["string", "null"],
                "minLength": 1,
            },
            "metadata": _METADATA,
        },
    },
    "SceneSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_SCHEMA_BASE}/scene-spec/{SCHEMA_VERSION}",
        "title": "SceneSpec",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "scene_id",
            "order",
            "duration_seconds",
            "location",
            "action",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "scene_id": {"type": "string", "pattern": _ID_PATTERN},
            "order": {"type": "integer", "minimum": 1},
            "duration_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "location": {"type": "string", "minLength": 1},
            "action": {"type": "string", "minLength": 1},
            "character_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": _ID_PATTERN},
                "uniqueItems": True,
            },
            "dialogue": {"type": ["string", "null"], "minLength": 1},
            "camera": {"type": ["string", "null"], "minLength": 1},
            "emotion": {"type": ["string", "null"], "minLength": 1},
            "transition": {"type": ["string", "null"], "minLength": 1},
            "metadata": _METADATA,
        },
    },
    "EpisodeSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_SCHEMA_BASE}/episode-spec/{SCHEMA_VERSION}",
        "title": "EpisodeSpec",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "episode_id",
            "project_id",
            "title",
            "language",
            "duration_target_seconds",
            "scenes",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "episode_id": {"type": "string", "pattern": _ID_PATTERN},
            "project_id": {"type": "string", "pattern": _ID_PATTERN},
            "title": {"type": "string", "minLength": 1},
            "language": {"type": "string", "minLength": 2},
            "duration_target_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "scenes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "$ref": (
                        f"{_SCHEMA_BASE}/scene-spec/"
                        f"{SCHEMA_VERSION}"
                    )
                },
            },
            "character_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": _ID_PATTERN},
                "uniqueItems": True,
            },
            "lesson": {"type": ["string", "null"], "minLength": 1},
            "metadata": _METADATA,
        },
    },
    "ProjectSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_SCHEMA_BASE}/project-spec/{SCHEMA_VERSION}",
        "title": "ProjectSpec",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "project_id",
            "title",
            "language",
            "target_platforms",
            "aspect_ratio",
            "resolution",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "project_id": {"type": "string", "pattern": _ID_PATTERN},
            "title": {"type": "string", "minLength": 1},
            "language": {"type": "string", "minLength": 2},
            "target_platforms": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "aspect_ratio": {
                "type": "string",
                "pattern": _ASPECT_RATIO_PATTERN,
            },
            "resolution": {
                "type": "string",
                "pattern": _RESOLUTION_PATTERN,
            },
            "characters": {
                "type": "array",
                "items": {
                    "$ref": (
                        f"{_SCHEMA_BASE}/character-spec/"
                        f"{SCHEMA_VERSION}"
                    )
                },
            },
            "episodes": {
                "type": "array",
                "items": {
                    "$ref": (
                        f"{_SCHEMA_BASE}/episode-spec/"
                        f"{SCHEMA_VERSION}"
                    )
                },
            },
            "metadata": _METADATA,
        },
    },
}


def schema_for(contract_name: str) -> dict[str, Any]:
    """Return an isolated JSON-compatible schema for a canonical contract."""
    try:
        schema = SCHEMAS[contract_name]
    except KeyError as exc:
        raise KeyError(f"unknown canonical contract: {contract_name}") from exc
    return deepcopy(schema)
