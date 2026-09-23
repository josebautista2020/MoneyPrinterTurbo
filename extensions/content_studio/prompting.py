"""Provider-neutral prompt compilation for Content Studio AI."""

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
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.storyboard import StoryboardPlan

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


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _joined(values: tuple[str, ...]) -> str:
    return ", ".join(values)


@dataclass(frozen=True, slots=True)
class ShotPrompt(JsonContract):
    """Provider-neutral compiled prompt for one storyboard shot."""

    prompt_id: str
    scene_id: str
    shot_id: str
    location_id: str
    duration_seconds: float
    character_ids: tuple[str, ...]
    visual_prompt: str
    negative_constraints: tuple[str, ...] = ()
    reference_asset_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("prompt_id", "scene_id", "shot_id", "location_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "duration_seconds",
            _positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(
            self,
            "character_ids",
            _unique_ids(self.character_ids, "character_ids"),
        )
        object.__setattr__(
            self,
            "visual_prompt",
            _require_text(self.visual_prompt, "visual_prompt"),
        )
        object.__setattr__(
            self,
            "negative_constraints",
            _unique_texts(
                self.negative_constraints,
                "negative_constraints",
            ),
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
                "prompt_id",
                "scene_id",
                "shot_id",
                "location_id",
                "duration_seconds",
                "character_ids",
                "visual_prompt",
                "negative_constraints",
                "reference_asset_ids",
                "metadata",
            },
        )
        data["character_ids"] = tuple(data.get("character_ids", ()))
        data["negative_constraints"] = tuple(
            data.get("negative_constraints", ())
        )
        data["reference_asset_ids"] = tuple(
            data.get("reference_asset_ids", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PromptPlan(JsonContract):
    """Compiled provider-neutral prompts for a complete storyboard."""

    project_id: str
    story_id: str
    episode_id: str
    prompts: tuple[ShotPrompt, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("project_id", "story_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        prompts = tuple(self.prompts)
        if not prompts or not all(
            isinstance(prompt, ShotPrompt) for prompt in prompts
        ):
            raise DomainValidationError(
                "prompts must contain at least one ShotPrompt"
            )
        prompt_ids = [prompt.prompt_id for prompt in prompts]
        if len(prompt_ids) != len(set(prompt_ids)):
            raise DomainValidationError(
                "prompt_id values must be unique within PromptPlan"
            )
        shot_ids = [prompt.shot_id for prompt in prompts]
        if len(shot_ids) != len(set(shot_ids)):
            raise DomainValidationError(
                "each shot_id must appear exactly once in PromptPlan"
            )
        object.__setattr__(self, "prompts", prompts)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["prompts"] = [prompt.to_dict() for prompt in self.prompts]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"project_id", "story_id", "episode_id", "prompts", "metadata"},
        )
        data["prompts"] = tuple(
            ShotPrompt.from_dict(item)
            for item in data.get("prompts", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def validate_storyboard(self, storyboard: StoryboardPlan) -> None:
        mismatches = []
        if self.project_id != storyboard.project_id:
            mismatches.append("project_id")
        if self.story_id != storyboard.story_id:
            mismatches.append("story_id")
        if self.episode_id != storyboard.episode_id:
            mismatches.append("episode_id")
        if mismatches:
            raise DomainValidationError(
                "PromptPlan identity does not match StoryboardPlan: "
                f"{mismatches}"
            )

        expected: dict[str, tuple[str, Any]] = {}
        for scene in storyboard.scenes:
            for shot in scene.shots:
                expected[shot.shot_id] = (scene.scene_id, (scene, shot))

        actual = {prompt.shot_id: prompt for prompt in self.prompts}
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        if missing or unknown:
            raise DomainValidationError(
                "PromptPlan shot coverage mismatch: "
                f"missing={missing}, unknown={unknown}"
            )

        for shot_id, prompt in actual.items():
            scene_id, pair = expected[shot_id]
            scene, shot = pair
            if prompt.scene_id != scene_id:
                raise DomainValidationError(
                    f"Prompt {prompt.prompt_id!r} scene_id does not match "
                    f"storyboard shot {shot_id!r}"
                )
            if prompt.location_id != scene.location_id:
                raise DomainValidationError(
                    f"Prompt {prompt.prompt_id!r} location does not match "
                    f"storyboard shot {shot_id!r}"
                )
            if set(prompt.character_ids) != set(shot.character_ids):
                raise DomainValidationError(
                    f"Prompt {prompt.prompt_id!r} characters do not match "
                    f"storyboard shot {shot_id!r}"
                )
            if (
                abs(prompt.duration_seconds - shot.duration_seconds)
                > _DURATION_TOLERANCE
            ):
                raise DomainValidationError(
                    f"Prompt {prompt.prompt_id!r} duration does not match "
                    f"storyboard shot {shot_id!r}"
                )


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Canonical context required to compile visual prompts."""

    project: ProjectSpec
    story: StoryPlan
    character_bible: CharacterBible
    universe_bible: UniverseBible

    def validate_storyboard(self, storyboard: StoryboardPlan) -> None:
        storyboard.validate_context(
            self.story,
            self.project,
            self.character_bible,
            self.universe_bible,
        )


@runtime_checkable
class PromptCompiler(Protocol):
    """Provider-neutral storyboard-to-prompt compiler contract."""

    @property
    def compiler_name(self) -> str:
        ...

    def compile(
        self,
        storyboard: StoryboardPlan,
        context: PromptContext,
    ) -> PromptPlan:
        ...


class CanonicalPromptCompiler:
    """Deterministic provider-neutral reference prompt compiler."""

    @property
    def compiler_name(self) -> str:
        return "canonical"

    def compile(
        self,
        storyboard: StoryboardPlan,
        context: PromptContext,
    ) -> PromptPlan:
        context.validate_storyboard(storyboard)
        prompts: list[ShotPrompt] = []

        for scene in storyboard.scenes:
            location = context.universe_bible.resolve(scene.location_id)

            for shot in scene.shots:
                character_profiles = [
                    context.character_bible.resolve(character_id)
                    for character_id in shot.character_ids
                ]

                clauses = [
                    f"Action: {shot.visual_action}.",
                    f"Framing: {shot.framing}.",
                    f"Location: {location.description}.",
                ]

                if shot.camera_angle:
                    clauses.append(f"Camera angle: {shot.camera_angle}.")
                if shot.camera_movement:
                    clauses.append(
                        f"Camera movement: {shot.camera_movement}."
                    )
                if location.visual_traits:
                    clauses.append(
                        "Location visual traits: "
                        f"{_joined(location.visual_traits)}."
                    )
                if location.ambience:
                    clauses.append(
                        f"Ambience: {_joined(location.ambience)}."
                    )
                if location.consistency_rules:
                    clauses.append(
                        "Location continuity: "
                        f"{_joined(location.consistency_rules)}."
                    )
                if context.universe_bible.world_rules:
                    clauses.append(
                        "World continuity: "
                        f"{_joined(context.universe_bible.world_rules)}."
                    )

                for profile in character_profiles:
                    details = []
                    if profile.signature_features:
                        details.append(
                            "signature features "
                            f"{_joined(profile.signature_features)}"
                        )
                    if profile.wardrobe:
                        details.append(
                            f"wardrobe {_joined(profile.wardrobe)}"
                        )
                    if details:
                        clauses.append(
                            f"Character {profile.character_id}: "
                            + "; ".join(details)
                            + "."
                        )

                if shot.composition_notes:
                    clauses.append(
                        "Composition: "
                        f"{_joined(shot.composition_notes)}."
                    )
                if shot.continuity_notes:
                    clauses.append(
                        "Shot continuity: "
                        f"{_joined(shot.continuity_notes)}."
                    )

                negatives = list(location.forbidden_changes)
                references = list(location.reference_asset_ids)
                for profile in character_profiles:
                    negatives.extend(profile.forbidden_changes)
                    references.extend(profile.reference_asset_ids)

                prompts.append(
                    ShotPrompt(
                        prompt_id=shot.shot_id,
                        scene_id=scene.scene_id,
                        shot_id=shot.shot_id,
                        location_id=scene.location_id,
                        duration_seconds=shot.duration_seconds,
                        character_ids=shot.character_ids,
                        visual_prompt=" ".join(clauses),
                        negative_constraints=_ordered_unique(negatives),
                        reference_asset_ids=_ordered_unique(references),
                        metadata={
                            "compiler": self.compiler_name,
                            "storyboard_scene_id": scene.scene_id,
                        },
                    )
                )

        plan = PromptPlan(
            project_id=storyboard.project_id,
            story_id=storyboard.story_id,
            episode_id=storyboard.episode_id,
            prompts=tuple(prompts),
            metadata={"compiler": self.compiler_name},
        )
        plan.validate_storyboard(storyboard)
        return plan


def compile_prompts(
    compiler: PromptCompiler,
    storyboard: StoryboardPlan,
    context: PromptContext,
) -> PromptPlan:
    """Validate input and output around an injected prompt compiler."""
    context.validate_storyboard(storyboard)
    plan = compiler.compile(storyboard, context)
    if not isinstance(plan, PromptPlan):
        raise DomainValidationError(
            "PromptCompiler must return a PromptPlan"
        )
    plan.validate_storyboard(storyboard)
    return plan
