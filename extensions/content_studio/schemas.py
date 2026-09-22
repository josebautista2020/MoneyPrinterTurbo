"""JSON Schema definitions for canonical Content Studio contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from extensions.content_studio.domain import SCHEMA_VERSION

_SCHEMA_BASE = "https://content-studio.ai/schemas"

_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$"
_ASPECT_RATIO_PATTERN = r"^[1-9][0-9]*:[1-9][0-9]*$"
_RESOLUTION_PATTERN = r"^[1-9][0-9]*x[1-9][0-9]*$"

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


SCHEMAS.update(
    {
        "CharacterProfile": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/character-profile/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "CharacterProfile",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "character_id",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "character_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "signature_features": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "wardrobe": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "personality_notes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "voice_consistency": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "forbidden_changes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "reference_asset_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": _ID_PATTERN,
                    },
                    "uniqueItems": True,
                },
                "notes": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "metadata": _METADATA,
            },
        },
        "CharacterBible": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/character-bible/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "CharacterBible",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "profiles",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "profiles": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/character-profile/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
        "LocationProfile": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/location-profile/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "LocationProfile",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "location_id",
                "description",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "location_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "description": {
                    "type": "string",
                    "minLength": 1,
                },
                "visual_traits": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "ambience": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "consistency_rules": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "forbidden_changes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "reference_asset_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": _ID_PATTERN,
                    },
                    "uniqueItems": True,
                },
                "metadata": _METADATA,
            },
        },
        "UniverseBible": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/universe-bible/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "UniverseBible",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "locations",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "locations": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/location-profile/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "world_rules": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "metadata": _METADATA,
            },
        },
    }
)



SCHEMAS.update(
    {
        "StoryBrief": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/story-brief/{SCHEMA_VERSION}",
            "title": "StoryBrief",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "story_id",
                "project_id",
                "episode_id",
                "title",
                "premise",
                "language",
                "duration_target_seconds",
                "location_ids",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "title": {"type": "string", "minLength": 1},
                "premise": {"type": "string", "minLength": 1},
                "language": {"type": "string", "minLength": 1},
                "duration_target_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "location_ids": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "tone": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "lesson": {"type": ["string", "null"], "minLength": 1},
                "metadata": _METADATA,
            },
        },
        "StoryBeat": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/story-beat/{SCHEMA_VERSION}",
            "title": "StoryBeat",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "beat_id",
                "order",
                "purpose",
                "summary",
                "duration_seconds",
                "location_id",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "beat_id": {"type": "string", "pattern": _ID_PATTERN},
                "order": {"type": "integer", "minimum": 1},
                "purpose": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1},
                "duration_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "location_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "dialogue_hint": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "emotion": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "metadata": _METADATA,
            },
        },
        "StoryPlan": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/story-plan/{SCHEMA_VERSION}",
            "title": "StoryPlan",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "brief", "beats"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "brief": {
                    "$ref": (
                        f"{_SCHEMA_BASE}/story-brief/"
                        f"{SCHEMA_VERSION}"
                    )
                },
                "beats": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/story-beat/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
    }
)


SCHEMAS.update(
    {
        "StoryboardShot": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/storyboard-shot/{SCHEMA_VERSION}",
            "title": "StoryboardShot",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "shot_id",
                "order",
                "duration_seconds",
                "visual_action",
                "framing",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "shot_id": {"type": "string", "pattern": _ID_PATTERN},
                "order": {"type": "integer", "minimum": 1},
                "duration_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "visual_action": {"type": "string", "minLength": 1},
                "framing": {"type": "string", "minLength": 1},
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "camera_angle": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "camera_movement": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "composition_notes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "continuity_notes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "metadata": _METADATA,
            },
        },
        "StoryboardScene": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/storyboard-scene/{SCHEMA_VERSION}",
            "title": "StoryboardScene",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "scene_id",
                "beat_id",
                "order",
                "location_id",
                "character_ids",
                "shots",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "scene_id": {"type": "string", "pattern": _ID_PATTERN},
                "beat_id": {"type": "string", "pattern": _ID_PATTERN},
                "order": {"type": "integer", "minimum": 1},
                "location_id": {"type": "string", "pattern": _ID_PATTERN},
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "shots": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/storyboard-shot/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
        "StoryboardPlan": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/storyboard-plan/{SCHEMA_VERSION}",
            "title": "StoryboardPlan",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "story_id",
                "project_id",
                "episode_id",
                "scenes",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "scenes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/storyboard-scene/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
    }
)

def schema_for(contract_name: str) -> dict[str, Any]:
    """Return an isolated JSON-compatible schema for a canonical contract."""
    try:
        schema = SCHEMAS[contract_name]
    except KeyError as exc:
        raise KeyError(f"unknown canonical contract: {contract_name}") from exc
    return deepcopy(schema)
