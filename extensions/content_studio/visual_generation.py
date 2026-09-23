"""Provider-neutral visual generation contracts and orchestration."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.prompting import PromptPlan

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_RESOLUTION_RE = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")
_ASPECT_RATIO_RE = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")


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


def _non_negative_number(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise DomainValidationError(
            f"{field_name} must be a non-negative finite number"
        )
    return float(value)


def _optional_non_negative_number(
    value: float | None,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _non_negative_number(value, field_name)


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
class VisualRequest(JsonContract):
    """One provider-neutral generation request derived from a ShotPrompt."""

    request_id: str
    project_id: str
    story_id: str
    episode_id: str
    scene_id: str
    shot_id: str
    prompt: str
    aspect_ratio: str
    resolution: str
    duration_seconds: float
    character_ids: tuple[str, ...] = ()
    negative_constraints: tuple[str, ...] = ()
    reference_asset_ids: tuple[str, ...] = ()
    asset_kind: str = "image"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "project_id",
            "story_id",
            "episode_id",
            "scene_id",
            "shot_id",
        ):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        if (
            not isinstance(self.aspect_ratio, str)
            or not _ASPECT_RATIO_RE.fullmatch(self.aspect_ratio)
        ):
            raise DomainValidationError(
                "aspect_ratio must use positive W:H notation"
            )
        if (
            not isinstance(self.resolution, str)
            or not _RESOLUTION_RE.fullmatch(self.resolution)
        ):
            raise DomainValidationError(
                "resolution must use positive WIDTHxHEIGHT notation"
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
        if self.asset_kind not in {"image", "video"}:
            raise DomainValidationError(
                "asset_kind must be 'image' or 'video'"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
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
                "character_ids",
                "negative_constraints",
                "reference_asset_ids",
                "asset_kind",
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
class VisualGenerationPlan(JsonContract):
    """One-to-one generation requests for a complete PromptPlan."""

    project_id: str
    story_id: str
    episode_id: str
    requests: tuple[VisualRequest, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("project_id", "story_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        requests = tuple(self.requests)
        if not requests or not all(
            isinstance(request, VisualRequest) for request in requests
        ):
            raise DomainValidationError(
                "requests must contain at least one VisualRequest"
            )
        request_ids = [request.request_id for request in requests]
        if len(request_ids) != len(set(request_ids)):
            raise DomainValidationError(
                "request_id values must be unique within VisualGenerationPlan"
            )
        shot_ids = [request.shot_id for request in requests]
        if len(shot_ids) != len(set(shot_ids)):
            raise DomainValidationError(
                "each shot_id must appear exactly once in VisualGenerationPlan"
            )
        for request in requests:
            if request.project_id != self.project_id:
                raise DomainValidationError(
                    "VisualRequest project_id does not match plan"
                )
            if request.story_id != self.story_id:
                raise DomainValidationError(
                    "VisualRequest story_id does not match plan"
                )
            if request.episode_id != self.episode_id:
                raise DomainValidationError(
                    "VisualRequest episode_id does not match plan"
                )
        object.__setattr__(self, "requests", requests)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["requests"] = [
            request.to_dict() for request in self.requests
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"project_id", "story_id", "episode_id", "requests", "metadata"},
        )
        data["requests"] = tuple(
            VisualRequest.from_dict(item)
            for item in data.get("requests", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def validate_prompt_plan(self, prompt_plan: PromptPlan) -> None:
        mismatches = []
        if self.project_id != prompt_plan.project_id:
            mismatches.append("project_id")
        if self.story_id != prompt_plan.story_id:
            mismatches.append("story_id")
        if self.episode_id != prompt_plan.episode_id:
            mismatches.append("episode_id")
        if mismatches:
            raise DomainValidationError(
                "VisualGenerationPlan identity does not match PromptPlan: "
                f"{mismatches}"
            )

        expected = {prompt.shot_id: prompt for prompt in prompt_plan.prompts}
        actual = {request.shot_id: request for request in self.requests}
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        if missing or unknown:
            raise DomainValidationError(
                "VisualGenerationPlan shot coverage mismatch: "
                f"missing={missing}, unknown={unknown}"
            )

        for shot_id, request in actual.items():
            prompt = expected[shot_id]
            if request.scene_id != prompt.scene_id:
                raise DomainValidationError(
                    f"VisualRequest {request.request_id!r} scene_id does not "
                    f"match ShotPrompt {shot_id!r}"
                )
            if set(request.character_ids) != set(prompt.character_ids):
                raise DomainValidationError(
                    f"VisualRequest {request.request_id!r} characters do not "
                    f"match ShotPrompt {shot_id!r}"
                )
            if (
                abs(request.duration_seconds - prompt.duration_seconds)
                > 0.001
            ):
                raise DomainValidationError(
                    f"VisualRequest {request.request_id!r} duration does not "
                    f"match ShotPrompt {shot_id!r}"
                )


@dataclass(frozen=True, slots=True)
class VisualArtifact(JsonContract):
    """Generated visual artifact with traceability back to a request."""

    asset_id: str
    request_id: str
    shot_id: str
    asset_kind: str
    uri: str
    engine: str
    provider: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("asset_id", "request_id", "shot_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        if self.asset_kind not in {"image", "video"}:
            raise DomainValidationError(
                "asset_kind must be 'image' or 'video'"
            )
        object.__setattr__(self, "uri", _require_text(self.uri, "uri"))
        object.__setattr__(self, "engine", _require_text(self.engine, "engine"))
        object.__setattr__(
            self,
            "provider",
            _require_text(self.provider, "provider"),
        )
        for name in ("width", "height"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise DomainValidationError(
                    f"{name} must be a positive integer when provided"
                )
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _positive_number(
                    self.duration_seconds,
                    "duration_seconds",
                ),
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "asset_id",
                "request_id",
                "shot_id",
                "asset_kind",
                "uri",
                "engine",
                "provider",
                "width",
                "height",
                "duration_seconds",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class VisualResult(JsonContract):
    """Result of exactly one VisualRequest."""

    request_id: str
    engine: str
    success: bool
    artifacts: tuple[VisualArtifact, ...] = ()
    error: str | None = None
    cost_usd: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _require_id(self.request_id, "request_id"),
        )
        object.__setattr__(self, "engine", _require_text(self.engine, "engine"))
        if not isinstance(self.success, bool):
            raise DomainValidationError("success must be a boolean")
        artifacts = tuple(self.artifacts)
        if not all(
            isinstance(artifact, VisualArtifact) for artifact in artifacts
        ):
            raise DomainValidationError(
                "artifacts must contain VisualArtifact values"
            )
        for artifact in artifacts:
            if artifact.request_id != self.request_id:
                raise DomainValidationError(
                    "VisualArtifact request_id does not match VisualResult"
                )
        error = _optional_text(self.error, "error")
        cost = _optional_non_negative_number(self.cost_usd, "cost_usd")
        if self.success and not artifacts:
            raise DomainValidationError(
                "successful VisualResult must contain at least one artifact"
            )
        if self.success and error is not None:
            raise DomainValidationError(
                "successful VisualResult cannot contain an error"
            )
        if not self.success and artifacts:
            raise DomainValidationError(
                "failed VisualResult cannot contain artifacts"
            )
        if not self.success and error is None:
            raise DomainValidationError(
                "failed VisualResult must contain an error"
            )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "error", error)
        object.__setattr__(self, "cost_usd", cost)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["artifacts"] = [
            artifact.to_dict() for artifact in self.artifacts
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "engine",
                "success",
                "artifacts",
                "error",
                "cost_usd",
                "metadata",
            },
        )
        data["artifacts"] = tuple(
            VisualArtifact.from_dict(item)
            for item in data.get("artifacts", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class VisualGenerationReport(JsonContract):
    """Batch result with explicit known/unknown cost visibility."""

    project_id: str
    story_id: str
    episode_id: str
    results: tuple[VisualResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("project_id", "story_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        results = tuple(self.results)
        if not results or not all(
            isinstance(result, VisualResult) for result in results
        ):
            raise DomainValidationError(
                "results must contain at least one VisualResult"
            )
        request_ids = [result.request_id for result in results]
        if len(request_ids) != len(set(request_ids)):
            raise DomainValidationError(
                "request_id values must be unique within VisualGenerationReport"
            )
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def success(self) -> bool:
        return all(result.success for result in self.results)

    @property
    def known_cost_usd(self) -> float:
        return sum(result.cost_usd or 0.0 for result in self.results)

    @property
    def cost_complete(self) -> bool:
        return all(result.cost_usd is not None for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["results"] = [result.to_dict() for result in self.results]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"project_id", "story_id", "episode_id", "results", "metadata"},
        )
        data["results"] = tuple(
            VisualResult.from_dict(item)
            for item in data.get("results", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def validate_plan(self, plan: VisualGenerationPlan) -> None:
        if (
            self.project_id != plan.project_id
            or self.story_id != plan.story_id
            or self.episode_id != plan.episode_id
        ):
            raise DomainValidationError(
                "VisualGenerationReport identity does not match plan"
            )
        expected = {request.request_id for request in plan.requests}
        actual = {result.request_id for result in self.results}
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            raise DomainValidationError(
                "VisualGenerationReport request coverage mismatch: "
                f"missing={missing}, unknown={unknown}"
            )


@runtime_checkable
class VisualGenerator(Protocol):
    """Provider-neutral visual generation engine."""

    @property
    def engine_name(self) -> str:
        ...

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        ...

    def generate(self, request: VisualRequest) -> VisualResult:
        ...


def build_visual_generation_plan(
    prompt_plan: PromptPlan,
    project: ProjectSpec,
    *,
    asset_kind: str = "image",
) -> VisualGenerationPlan:
    """Compile one generation request per ShotPrompt."""
    if prompt_plan.project_id != project.project_id:
        raise DomainValidationError(
            "PromptPlan project_id does not match ProjectSpec"
        )
    requests = tuple(
        VisualRequest(
            request_id=prompt.prompt_id,
            project_id=prompt_plan.project_id,
            story_id=prompt_plan.story_id,
            episode_id=prompt_plan.episode_id,
            scene_id=prompt.scene_id,
            shot_id=prompt.shot_id,
            prompt=prompt.visual_prompt,
            aspect_ratio=project.aspect_ratio,
            resolution=project.resolution,
            duration_seconds=prompt.duration_seconds,
            character_ids=prompt.character_ids,
            negative_constraints=prompt.negative_constraints,
            reference_asset_ids=prompt.reference_asset_ids,
            asset_kind=asset_kind,
            metadata={
                "source_prompt_id": prompt.prompt_id,
                "location_id": prompt.location_id,
            },
        )
        for prompt in prompt_plan.prompts
    )
    plan = VisualGenerationPlan(
        project_id=prompt_plan.project_id,
        story_id=prompt_plan.story_id,
        episode_id=prompt_plan.episode_id,
        requests=requests,
        metadata={"source": "PromptPlan"},
    )
    plan.validate_prompt_plan(prompt_plan)
    return plan


def generate_visuals(
    generator: VisualGenerator,
    plan: VisualGenerationPlan,
    *,
    max_cost_usd: float | None = None,
    fail_fast: bool = False,
) -> VisualGenerationReport:
    """Generate a plan sequentially with an optional preflight cost ceiling."""
    budget = _optional_non_negative_number(max_cost_usd, "max_cost_usd")
    if budget is not None:
        estimates = []
        for request in plan.requests:
            estimate = generator.estimate_cost_usd(request)
            if estimate is None:
                raise DomainValidationError(
                    "cost estimate required before budget-controlled generation"
                )
            estimates.append(
                _non_negative_number(estimate, "estimated_cost_usd")
            )
        projected = sum(estimates)
        if projected > budget:
            raise DomainValidationError(
                f"projected visual generation cost {projected:.6f} USD "
                f"exceeds budget {budget:.6f} USD"
            )

    results = []
    for request in plan.requests:
        result = generator.generate(request)
        if not isinstance(result, VisualResult):
            raise DomainValidationError(
                "VisualGenerator must return a VisualResult"
            )
        if result.request_id != request.request_id:
            raise DomainValidationError(
                "VisualGenerator returned a result for a different request"
            )
        results.append(result)
        if fail_fast and not result.success:
            break

    report = VisualGenerationReport(
        project_id=plan.project_id,
        story_id=plan.story_id,
        episode_id=plan.episode_id,
        results=tuple(results),
        metadata={"engine": generator.engine_name},
    )
    if not fail_fast or len(results) == len(plan.requests):
        report.validate_plan(plan)
    return report
