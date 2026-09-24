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


SCHEMAS.update(
    {
        "ShotPrompt": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/shot-prompt/{SCHEMA_VERSION}",
            "title": "ShotPrompt",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "prompt_id",
                "scene_id",
                "shot_id",
                "location_id",
                "duration_seconds",
                "character_ids",
                "visual_prompt",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "prompt_id": {"type": "string", "pattern": _ID_PATTERN},
                "scene_id": {"type": "string", "pattern": _ID_PATTERN},
                "shot_id": {"type": "string", "pattern": _ID_PATTERN},
                "location_id": {"type": "string", "pattern": _ID_PATTERN},
                "duration_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "visual_prompt": {"type": "string", "minLength": 1},
                "negative_constraints": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "reference_asset_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "metadata": _METADATA,
            },
        },
        "PromptPlan": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/prompt-plan/{SCHEMA_VERSION}",
            "title": "PromptPlan",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "story_id",
                "episode_id",
                "prompts",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "prompts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/shot-prompt/"
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
        "VisualRequest": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/visual-request/{SCHEMA_VERSION}",
            "title": "VisualRequest",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "project_id",
                "story_id",
                "episode_id",
                "scene_id",
                "shot_id",
                "prompt",
                "aspect_ratio",
                "resolution",
                "duration_seconds",
                "asset_kind",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "scene_id": {"type": "string", "pattern": _ID_PATTERN},
                "shot_id": {"type": "string", "pattern": _ID_PATTERN},
                "prompt": {"type": "string", "minLength": 1},
                "aspect_ratio": {
                    "type": "string",
                    "pattern": _ASPECT_RATIO_PATTERN,
                },
                "resolution": {
                    "type": "string",
                    "pattern": _RESOLUTION_PATTERN,
                },
                "duration_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "character_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "negative_constraints": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "reference_asset_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                    "uniqueItems": True,
                },
                "asset_kind": {
                    "type": "string",
                    "enum": ["image", "video"],
                },
                "metadata": _METADATA,
            },
        },
        "VisualGenerationPlan": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/visual-generation-plan/{SCHEMA_VERSION}",
            "title": "VisualGenerationPlan",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "story_id",
                "episode_id",
                "requests",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "requests": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/visual-request/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
        "VisualArtifact": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/visual-artifact/{SCHEMA_VERSION}",
            "title": "VisualArtifact",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "asset_id",
                "request_id",
                "shot_id",
                "asset_kind",
                "uri",
                "engine",
                "provider",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "asset_id": {"type": "string", "pattern": _ID_PATTERN},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "shot_id": {"type": "string", "pattern": _ID_PATTERN},
                "asset_kind": {
                    "type": "string",
                    "enum": ["image", "video"],
                },
                "uri": {"type": "string", "minLength": 1},
                "engine": {"type": "string", "minLength": 1},
                "provider": {"type": "string", "minLength": 1},
                "width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                },
                "height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                },
                "duration_seconds": {
                    "type": ["number", "null"],
                    "exclusiveMinimum": 0,
                },
                "metadata": _METADATA,
            },
        },
        "VisualResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/visual-result/{SCHEMA_VERSION}",
            "title": "VisualResult",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "engine",
                "success",
                "artifacts",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "engine": {"type": "string", "minLength": 1},
                "success": {"type": "boolean"},
                "artifacts": {
                    "type": "array",
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/visual-artifact/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "error": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "cost_usd": {
                    "type": ["number", "null"],
                    "minimum": 0,
                },
                "metadata": _METADATA,
            },
        },
        "VisualGenerationReport": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/visual-generation-report/{SCHEMA_VERSION}",
            "title": "VisualGenerationReport",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "story_id",
                "episode_id",
                "results",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "results": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/visual-result/"
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
        "ReferenceAsset": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/reference-asset/{SCHEMA_VERSION}",
            "title": "ReferenceAsset",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "reference_asset_id",
                "uri",
                "media_type",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "reference_asset_id": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "uri": {"type": "string", "minLength": 1},
                "media_type": {"type": "string", "minLength": 1},
                "character_id": {
                    "type": ["string", "null"],
                    "pattern": _ID_PATTERN,
                },
                "location_id": {
                    "type": ["string", "null"],
                    "pattern": _ID_PATTERN,
                },
                "metadata": _METADATA,
            },
        },
        "ReferenceCatalog": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/reference-catalog/{SCHEMA_VERSION}",
            "title": "ReferenceCatalog",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "assets",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "assets": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/reference-asset/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
        "ConsistencyAssessment": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/consistency-assessment/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "ConsistencyAssessment",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "evaluator",
                "identity_score",
                "appearance_score",
                "wardrobe_score",
                "environment_score",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "evaluator": {"type": "string", "minLength": 1},
                "identity_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "appearance_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "wardrobe_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "environment_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "notes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "metadata": _METADATA,
            },
        },
        "ConsistencyPolicy": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/consistency-policy/{SCHEMA_VERSION}",
            "title": "ConsistencyPolicy",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "minimum_overall_score",
                "minimum_identity_score",
                "max_attempts",
                "require_references_for_characters",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "minimum_overall_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "minimum_identity_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "max_attempts": {"type": "integer", "minimum": 1},
                "require_references_for_characters": {"type": "boolean"},
                "metadata": _METADATA,
            },
        },
        "ConsistencyAttempt": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/consistency-attempt/{SCHEMA_VERSION}",
            "title": "ConsistencyAttempt",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "attempt_number",
                "visual_result",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "attempt_number": {"type": "integer", "minimum": 1},
                "visual_result": {
                    "$ref": (
                        f"{_SCHEMA_BASE}/visual-result/"
                        f"{SCHEMA_VERSION}"
                    )
                },
                "assessment": {
                    "anyOf": [
                        {
                            "$ref": (
                                f"{_SCHEMA_BASE}/consistency-assessment/"
                                f"{SCHEMA_VERSION}"
                            )
                        },
                        {"type": "null"},
                    ]
                },
                "metadata": _METADATA,
            },
        },
        "ConsistentVisualResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/consistent-visual-result/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "ConsistentVisualResult",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "accepted",
                "attempts",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "accepted": {"type": "boolean"},
                "attempts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/consistency-attempt/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "metadata": _METADATA,
            },
        },
        "ConsistencyReport": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/consistency-report/{SCHEMA_VERSION}",
            "title": "ConsistencyReport",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "story_id",
                "episode_id",
                "results",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "results": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/consistent-visual-result/"
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
        "MediaAssemblyPlan": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/media-assembly-plan/{SCHEMA_VERSION}",
            "title": "MediaAssemblyPlan",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "assembly_id", "project_id", "story_id",
                "episode_id", "script", "language", "voice_name",
                "visual_uris", "visual_kinds", "visual_durations_seconds",
                "aspect_ratio", "resolution", "output_uri"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "assembly_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "story_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "script": {"type": "string", "minLength": 1},
                "language": {"type": "string", "minLength": 1},
                "voice_name": {"type": "string", "minLength": 1},
                "visual_uris": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string", "minLength": 1}
                },
                "visual_kinds": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string", "enum": ["image", "video"]}
                },
                "visual_durations_seconds": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "number", "exclusiveMinimum": 0}
                },
                "aspect_ratio": {"type": "string", "pattern": _ASPECT_RATIO_PATTERN},
                "resolution": {"type": "string", "pattern": _RESOLUTION_PATTERN},
                "output_uri": {"type": "string", "minLength": 1},
                "voice_rate": {"type": "number", "exclusiveMinimum": 0},
                "voice_volume": {"type": "number", "exclusiveMinimum": 0},
                "subtitle_enabled": {"type": "boolean"},
                "subtitle_mode": {"type": "string", "enum": ["sentence", "word_by_word"]},
                "subtitle_position": {
                    "type": "string",
                    "enum": ["top", "bottom", "center", "custom", "two_thirds_bottom"]
                },
                "font_name": {"type": "string", "minLength": 1},
                "font_size": {"type": "integer", "minimum": 1},
                "text_color": {"type": "string", "minLength": 1},
                "background_color": {"type": ["string", "null"], "minLength": 1},
                "rounded_subtitle_background": {"type": "boolean"},
                "stroke_color": {"type": "string", "minLength": 1},
                "stroke_width": {"type": "number", "minimum": 0},
                "clip_duration_seconds": {"type": "integer", "minimum": 1},
                "fit_mode": {"type": "string", "enum": ["cover", "contain"]},
                "transition": {
                    "type": "string",
                    "enum": ["none", "fade_in", "fade_out", "slide_in", "slide_out", "zoom_in", "zoom_out", "shuffle"]
                },
                "metadata": _METADATA
            }
        },
        "AudioArtifact": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/audio-artifact/{SCHEMA_VERSION}",
            "title": "AudioArtifact",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "audio_id", "uri", "duration_seconds", "engine", "provider"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "audio_id": {"type": "string", "pattern": _ID_PATTERN},
                "uri": {"type": "string", "minLength": 1},
                "duration_seconds": {"type": "number", "exclusiveMinimum": 0},
                "engine": {"type": "string", "minLength": 1},
                "provider": {"type": "string", "minLength": 1},
                "metadata": _METADATA
            }
        },
        "SubtitleArtifact": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/subtitle-artifact/{SCHEMA_VERSION}",
            "title": "SubtitleArtifact",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "subtitle_id", "uri", "format", "cue_count", "engine", "provider"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "subtitle_id": {"type": "string", "pattern": _ID_PATTERN},
                "uri": {"type": "string", "minLength": 1},
                "format": {"type": "string", "minLength": 1},
                "cue_count": {"type": "integer", "minimum": 1},
                "engine": {"type": "string", "minLength": 1},
                "provider": {"type": "string", "minLength": 1},
                "metadata": _METADATA
            }
        },
        "RenderArtifact": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/render-artifact/{SCHEMA_VERSION}",
            "title": "RenderArtifact",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "render_id", "uri", "engine", "provider", "width", "height", "duration_seconds"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "render_id": {"type": "string", "pattern": _ID_PATTERN},
                "uri": {"type": "string", "minLength": 1},
                "engine": {"type": "string", "minLength": 1},
                "provider": {"type": "string", "minLength": 1},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "duration_seconds": {"type": "number", "exclusiveMinimum": 0},
                "metadata": _METADATA
            }
        },
        "MediaAssemblyResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/media-assembly-result/{SCHEMA_VERSION}",
            "title": "MediaAssemblyResult",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "assembly_id", "engine", "success"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "assembly_id": {"type": "string", "pattern": _ID_PATTERN},
                "engine": {"type": "string", "minLength": 1},
                "success": {"type": "boolean"},
                "audio": {"anyOf": [{"$ref": f"{_SCHEMA_BASE}/audio-artifact/{SCHEMA_VERSION}"}, {"type": "null"}]},
                "subtitle": {"anyOf": [{"$ref": f"{_SCHEMA_BASE}/subtitle-artifact/{SCHEMA_VERSION}"}, {"type": "null"}]},
                "video": {"anyOf": [{"$ref": f"{_SCHEMA_BASE}/render-artifact/{SCHEMA_VERSION}"}, {"type": "null"}]},
                "error": {"type": ["string", "null"], "minLength": 1},
                "cost_usd": {"type": ["number", "null"], "minimum": 0},
                "metadata": _METADATA
            }
        }
    }
)


SCHEMAS.update(
    {
        "SafetyRule": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/safety-rule/{SCHEMA_VERSION}",
            "title": "SafetyRule",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "rule_id", "category",
                "severity", "terms", "description"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "rule_id": {"type": "string", "pattern": _ID_PATTERN},
                "category": {"type": "string", "pattern": _ID_PATTERN},
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "block"]
                },
                "terms": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1}
                },
                "description": {"type": "string", "minLength": 1}
            }
        },
        "SafetyPolicy": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/safety-policy/{SCHEMA_VERSION}",
            "title": "SafetyPolicy",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "policy_id", "audience_min_age",
                "audience_max_age", "rules", "required_modalities"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "policy_id": {"type": "string", "pattern": _ID_PATTERN},
                "audience_min_age": {"type": "integer", "minimum": 0},
                "audience_max_age": {"type": "integer", "minimum": 0},
                "rules": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/safety-rule/"
                            f"{SCHEMA_VERSION}"
                        )
                    }
                },
                "required_modalities": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": ["script", "subtitle", "audio", "visual", "metadata"]
                    }
                },
                "metadata": _METADATA
            }
        },
        "SafetyReviewRequest": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/safety-review-request/{SCHEMA_VERSION}",
            "title": "SafetyReviewRequest",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "request_id", "project_id",
                "episode_id", "script"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "script": {"type": "string", "minLength": 1},
                "subtitle_text": {"type": "string"},
                "audio_uri": {"type": ["string", "null"], "minLength": 1},
                "visual_uris": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1}
                },
                "metadata": _METADATA
            }
        },
        "SafetyFinding": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/safety-finding/{SCHEMA_VERSION}",
            "title": "SafetyFinding",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "finding_id", "category",
                "severity", "modality", "evidence"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "finding_id": {"type": "string", "pattern": _ID_PATTERN},
                "category": {"type": "string", "pattern": _ID_PATTERN},
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "block"]
                },
                "modality": {
                    "type": "string",
                    "enum": ["script", "subtitle", "audio", "visual", "metadata"]
                },
                "evidence": {"type": "string", "minLength": 1},
                "rule_id": {
                    "type": ["string", "null"],
                    "pattern": _ID_PATTERN
                },
                "metadata": _METADATA
            }
        },
        "SafetyAssessment": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/safety-assessment/{SCHEMA_VERSION}",
            "title": "SafetyAssessment",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "request_id", "reviewer",
                "reviewed_modalities", "findings"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "reviewer": {"type": "string", "minLength": 1},
                "reviewed_modalities": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": ["script", "subtitle", "audio", "visual", "metadata"]
                    }
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/safety-finding/"
                            f"{SCHEMA_VERSION}"
                        )
                    }
                },
                "metadata": _METADATA
            }
        },
        "RenderQAPolicy": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/render-qa-policy/{SCHEMA_VERSION}",
            "title": "RenderQAPolicy",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "minimum_duration_seconds",
                "maximum_duration_seconds", "duration_tolerance_seconds",
                "require_audio", "require_subtitles",
                "require_consistency_pass"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "minimum_duration_seconds": {"type": "number", "minimum": 0},
                "maximum_duration_seconds": {"type": "number", "minimum": 0},
                "duration_tolerance_seconds": {"type": "number", "minimum": 0},
                "require_audio": {"type": "boolean"},
                "require_subtitles": {"type": "boolean"},
                "require_consistency_pass": {"type": "boolean"},
                "metadata": _METADATA
            }
        },
        "QACheck": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/qa-check/{SCHEMA_VERSION}",
            "title": "QACheck",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "check_id", "passed", "message"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "check_id": {"type": "string", "minLength": 1},
                "passed": {"type": "boolean"},
                "message": {"type": "string", "minLength": 1}
            }
        },
        "RenderQAReport": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/render-qa-report/{SCHEMA_VERSION}",
            "title": "RenderQAReport",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "project_id", "episode_id", "checks"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "minLength": 1},
                "episode_id": {"type": "string", "minLength": 1},
                "checks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": f"{_SCHEMA_BASE}/qa-check/{SCHEMA_VERSION}"
                    }
                },
                "metadata": _METADATA
            }
        },
        "HumanReviewGate": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/human-review-gate/{SCHEMA_VERSION}",
            "title": "HumanReviewGate",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "project_id", "episode_id",
                "safety_complete", "safety_blocked",
                "render_qa_passed", "eligible_for_human_review",
                "publication_allowed", "missing_safety_modalities"
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "project_id": {"type": "string", "minLength": 1},
                "episode_id": {"type": "string", "minLength": 1},
                "safety_complete": {"type": "boolean"},
                "safety_blocked": {"type": "boolean"},
                "render_qa_passed": {"type": "boolean"},
                "eligible_for_human_review": {"type": "boolean"},
                "publication_allowed": {"const": False},
                "missing_safety_modalities": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": ["script", "subtitle", "audio", "visual", "metadata"]
                    }
                },
                "metadata": _METADATA
            }
        }
    }
)


SCHEMAS.update(
    {
        "ReviewPackage": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/review-package/{SCHEMA_VERSION}",
            "title": "ReviewPackage",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "package_id",
                "project_id",
                "episode_id",
                "render_uri",
                "safety_assessments",
                "render_qa",
                "gate",
                "shot_ids",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "package_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "render_uri": {"type": "string", "minLength": 1},
                "safety_assessments": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/safety-assessment/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "render_qa": {
                    "$ref": f"{_SCHEMA_BASE}/render-qa-report/{SCHEMA_VERSION}"
                },
                "gate": {
                    "$ref": f"{_SCHEMA_BASE}/human-review-gate/{SCHEMA_VERSION}"
                },
                "shot_ids": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": _ID_PATTERN},
                },
                "metadata": _METADATA,
            },
        },
        "ReviewDecision": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/review-decision/{SCHEMA_VERSION}",
            "title": "ReviewDecision",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "decision_id",
                "package_id",
                "reviewer_id",
                "action",
                "decided_at",
                "comments",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "decision_id": {"type": "string", "pattern": _ID_PATTERN},
                "package_id": {"type": "string", "pattern": _ID_PATTERN},
                "reviewer_id": {"type": "string", "pattern": _ID_PATTERN},
                "action": {
                    "type": "string",
                    "enum": [
                        "approve",
                        "reject",
                        "regenerate_shot",
                        "regenerate_episode",
                    ],
                },
                "decided_at": {
                    "type": "string",
                    "format": "date-time",
                },
                "comments": {"type": "string", "minLength": 1},
                "target_shot_id": {
                    "type": ["string", "null"],
                    "pattern": _ID_PATTERN,
                },
                "metadata": _METADATA,
            },
        },
        "ReviewAuditTrail": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/review-audit-trail/{SCHEMA_VERSION}",
            "title": "ReviewAuditTrail",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "package_id",
                "decisions",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "package_id": {"type": "string", "pattern": _ID_PATTERN},
                "decisions": {
                    "type": "array",
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/review-decision/"
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
        "PublishGrant": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publish-grant/{SCHEMA_VERSION}",
            "title": "PublishGrant",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "platform", "account_ref"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "platform": {"type": "string", "pattern": _ID_PATTERN},
                "account_ref": {"type": "string", "minLength": 1},
            },
        },
        "PublishTarget": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publish-target/{SCHEMA_VERSION}",
            "title": "PublishTarget",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "platform",
                "account_ref",
                "privacy_level",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "platform": {"type": "string", "pattern": _ID_PATTERN},
                "account_ref": {"type": "string", "minLength": 1},
                "privacy_level": {"type": "string", "minLength": 1},
                "youtube_privacy_status": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "youtube_made_for_kids": {
                    "type": ["boolean", "null"],
                },
                "metadata": _METADATA,
            },
        },
        "PublishingPolicy": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publishing-policy/{SCHEMA_VERSION}",
            "title": "PublishingPolicy",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "policy_id",
                "allowed_targets",
                "live_publish_enabled",
                "max_targets_per_request",
                "max_live_publications_per_hour",
                "require_latest_approval",
                "require_explicit_youtube_audience",
                "require_synthetic_media_declaration",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "policy_id": {"type": "string", "pattern": _ID_PATTERN},
                "allowed_targets": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/publish-grant/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "live_publish_enabled": {"type": "boolean"},
                "max_targets_per_request": {
                    "type": "integer",
                    "minimum": 1,
                },
                "max_live_publications_per_hour": {
                    "type": "integer",
                    "minimum": 1,
                },
                "require_latest_approval": {"type": "boolean"},
                "require_explicit_youtube_audience": {"type": "boolean"},
                "require_synthetic_media_declaration": {"type": "boolean"},
                "metadata": _METADATA,
            },
        },
        "PublishRequest": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publish-request/{SCHEMA_VERSION}",
            "title": "PublishRequest",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "package_id",
                "decision_id",
                "video_uri",
                "title",
                "targets",
                "idempotency_key",
                "contains_synthetic_media",
                "dry_run",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "package_id": {"type": "string", "pattern": _ID_PATTERN},
                "decision_id": {"type": "string", "pattern": _ID_PATTERN},
                "video_uri": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "targets": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/publish-target/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "idempotency_key": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "description": {"type": "string"},
                "tags": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
                "contains_synthetic_media": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
                "metadata": _METADATA,
            },
        },
        "PublishTargetResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/publish-target-result/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "PublishTargetResult",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "platform",
                "account_ref",
                "success",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "platform": {"type": "string", "pattern": _ID_PATTERN},
                "account_ref": {"type": "string", "minLength": 1},
                "success": {"type": "boolean"},
                "external_request_id": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "error": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "metadata": _METADATA,
            },
        },
        "PublishResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publish-result/{SCHEMA_VERSION}",
            "title": "PublishResult",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "request_id",
                "publisher",
                "success",
                "dry_run",
                "outcomes",
                "idempotent_replay",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "request_id": {"type": "string", "pattern": _ID_PATTERN},
                "publisher": {"type": "string", "minLength": 1},
                "success": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
                "outcomes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/publish-target-result/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "idempotent_replay": {"type": "boolean"},
                "error": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "metadata": _METADATA,
            },
        },
        "PublicationRecord": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/publication-record/{SCHEMA_VERSION}",
            "title": "PublicationRecord",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "record_id",
                "idempotency_key",
                "request_fingerprint",
                "request",
                "result",
                "recorded_at",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "record_id": {"type": "string", "pattern": _ID_PATTERN},
                "idempotency_key": {
                    "type": "string",
                    "pattern": _ID_PATTERN,
                },
                "request_fingerprint": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "request": {
                    "$ref": f"{_SCHEMA_BASE}/publish-request/{SCHEMA_VERSION}"
                },
                "result": {
                    "$ref": f"{_SCHEMA_BASE}/publish-result/{SCHEMA_VERSION}"
                },
                "recorded_at": {
                    "type": "string",
                    "format": "date-time",
                },
                "metadata": _METADATA,
            },
        },
        "PublicationAuditTrail": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": (
                f"{_SCHEMA_BASE}/publication-audit-trail/"
                f"{SCHEMA_VERSION}"
            ),
            "title": "PublicationAuditTrail",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "records"],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "records": {
                    "type": "array",
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/publication-record/"
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
        "WorkflowArtifact": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/workflow-artifact/{SCHEMA_VERSION}",
            "title": "WorkflowArtifact",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "artifact_id",
                "artifact_type",
                "payload",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "artifact_id": {"type": "string", "pattern": _ID_PATTERN},
                "artifact_type": {"type": "string", "minLength": 1},
                "payload": {"type": "object"},
                "uri": {"type": ["string", "null"], "minLength": 1},
                "metadata": _METADATA,
            },
        },
        "StageExecutionResult": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/stage-execution-result/{SCHEMA_VERSION}",
            "title": "StageExecutionResult",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "stage",
                "status",
                "artifacts",
                "cost_usd",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "stage": {
                    "type": "string",
                    "enum": ["project_episode","bibles","story","storyboard","prompts","visuals","consistency","media","safety_qa","review_package","human_review","publish_dry_run"],
                },
                "status": {
                    "type": "string",
                    "enum": ["PASS", "FAIL", "BLOCKED"],
                },
                "artifacts": {
                    "type": "array",
                    "items": {
                        "$ref": f"{_SCHEMA_BASE}/workflow-artifact/{SCHEMA_VERSION}"
                    },
                },
                "cost_usd": {
                    "type": ["number", "null"],
                    "minimum": 0,
                },
                "error": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "metadata": _METADATA,
            },
        },
        "WorkflowStageRecord": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/workflow-stage-record/{SCHEMA_VERSION}",
            "title": "WorkflowStageRecord",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "record_id",
                "stage",
                "status",
                "attempt",
                "execution_key",
                "revision",
                "started_at",
                "artifacts",
                "cost_usd",
                "superseded",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "record_id": {"type": "string", "pattern": _ID_PATTERN},
                "stage": {
                    "type": "string",
                    "enum": ["project_episode","bibles","story","storyboard","prompts","visuals","consistency","media","safety_qa","review_package","human_review","publish_dry_run"],
                },
                "status": {
                    "type": "string",
                    "enum": ["PENDING","IN_PROGRESS","BLOCKED","PASS","FAIL","WAIVED_BY_ADR"],
                },
                "attempt": {"type": "integer", "minimum": 1},
                "execution_key": {"type": "string", "pattern": _ID_PATTERN},
                "revision": {"type": "integer", "minimum": 1},
                "started_at": {"type": "string", "format": "date-time"},
                "finished_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                },
                "artifacts": {
                    "type": "array",
                    "items": {
                        "$ref": f"{_SCHEMA_BASE}/workflow-artifact/{SCHEMA_VERSION}"
                    },
                },
                "cost_usd": {
                    "type": ["number", "null"],
                    "minimum": 0,
                },
                "error": {
                    "type": ["string", "null"],
                    "minLength": 1,
                },
                "superseded": {"type": "boolean"},
                "metadata": _METADATA,
            },
        },
        "EpisodeWorkflowState": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/episode-workflow-state/{SCHEMA_VERSION}",
            "title": "EpisodeWorkflowState",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "workflow_id",
                "project_id",
                "episode_id",
                "revision",
                "records",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "workflow_id": {"type": "string", "pattern": _ID_PATTERN},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "revision": {"type": "integer", "minimum": 1},
                "records": {
                    "type": "array",
                    "items": {
                        "$ref": (
                            f"{_SCHEMA_BASE}/workflow-stage-record/"
                            f"{SCHEMA_VERSION}"
                        )
                    },
                },
                "max_cost_usd": {
                    "type": ["number", "null"],
                    "minimum": 0,
                },
                "metadata": _METADATA,
            },
        },
        "EpisodeReleaseCandidate": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{_SCHEMA_BASE}/episode-release-candidate/{SCHEMA_VERSION}",
            "title": "EpisodeReleaseCandidate",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "workflow_id",
                "revision",
                "project_id",
                "episode_id",
                "render_uri",
                "review_decision_id",
                "publish_request_id",
                "publication_record_id",
                "total_cost_usd",
                "publication_status",
            ],
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "workflow_id": {"type": "string", "pattern": _ID_PATTERN},
                "revision": {"type": "integer", "minimum": 1},
                "project_id": {"type": "string", "pattern": _ID_PATTERN},
                "episode_id": {"type": "string", "pattern": _ID_PATTERN},
                "render_uri": {"type": "string", "minLength": 1},
                "review_decision_id": {"type": "string", "pattern": _ID_PATTERN},
                "publish_request_id": {"type": "string", "pattern": _ID_PATTERN},
                "publication_record_id": {"type": "string", "pattern": _ID_PATTERN},
                "total_cost_usd": {"type": "number", "minimum": 0},
                "publication_status": {"const": "dry_run_validated"},
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
