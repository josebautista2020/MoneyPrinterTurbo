"""Reference-aware character consistency contracts and orchestration."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    SCHEMA_VERSION,
)
from extensions.content_studio.visual_generation import (
    VisualGenerationPlan,
    VisualRequest,
    VisualResult,
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


def _score(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        raise DomainValidationError(
            f"{field_name} must be a finite number between 0 and 1"
        )
    return float(value)


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DomainValidationError(f"{field_name} must be a positive integer")
    return value


def _non_negative(value: float, field_name: str) -> float:
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


def _optional_non_negative(
    value: float | None,
    field_name: str,
) -> float | None:
    return None if value is None else _non_negative(value, field_name)


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
class ReferenceAsset(JsonContract):
    """Reference image or other visual asset used for consistency."""

    reference_asset_id: str
    uri: str
    media_type: str = "image/png"
    character_id: str | None = None
    location_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_asset_id",
            _require_id(self.reference_asset_id, "reference_asset_id"),
        )
        object.__setattr__(self, "uri", _require_text(self.uri, "uri"))
        object.__setattr__(
            self,
            "media_type",
            _require_text(self.media_type, "media_type"),
        )
        for name in ("character_id", "location_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _require_id(value, name))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "reference_asset_id",
                "uri",
                "media_type",
                "character_id",
                "location_id",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ReferenceCatalog(JsonContract):
    """Project-scoped registry that resolves logical reference asset IDs."""

    project_id: str
    assets: tuple[ReferenceAsset, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_id",
            _require_id(self.project_id, "project_id"),
        )
        assets = tuple(self.assets)
        if not assets or not all(
            isinstance(asset, ReferenceAsset) for asset in assets
        ):
            raise DomainValidationError(
                "assets must contain at least one ReferenceAsset"
            )
        ids = [asset.reference_asset_id for asset in assets]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(
                "reference_asset_id values must be unique within ReferenceCatalog"
            )
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["assets"] = [asset.to_dict() for asset in self.assets]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"project_id", "assets", "metadata"})
        data["assets"] = tuple(
            ReferenceAsset.from_dict(item)
            for item in data.get("assets", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc

    def resolve(self, reference_asset_id: str) -> ReferenceAsset:
        ref = _require_id(reference_asset_id, "reference_asset_id")
        for asset in self.assets:
            if asset.reference_asset_id == ref:
                return asset
        raise DomainValidationError(
            f"unknown reference asset: {reference_asset_id!r}"
        )

    def resolve_many(
        self,
        reference_asset_ids: tuple[str, ...],
    ) -> tuple[ReferenceAsset, ...]:
        return tuple(self.resolve(asset_id) for asset_id in reference_asset_ids)


@dataclass(frozen=True, slots=True)
class ConsistencyAssessment(JsonContract):
    """Measured visual consistency for one generated request."""

    request_id: str
    evaluator: str
    identity_score: float
    appearance_score: float
    wardrobe_score: float
    environment_score: float
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _require_id(self.request_id, "request_id"),
        )
        object.__setattr__(
            self,
            "evaluator",
            _require_text(self.evaluator, "evaluator"),
        )
        for name in (
            "identity_score",
            "appearance_score",
            "wardrobe_score",
            "environment_score",
        ):
            object.__setattr__(self, name, _score(getattr(self, name), name))
        object.__setattr__(
            self,
            "notes",
            _unique_texts(self.notes, "notes"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def overall_score(self) -> float:
        return (
            0.40 * self.identity_score
            + 0.25 * self.appearance_score
            + 0.20 * self.wardrobe_score
            + 0.15 * self.environment_score
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "evaluator",
                "identity_score",
                "appearance_score",
                "wardrobe_score",
                "environment_score",
                "notes",
                "metadata",
            },
        )
        data["notes"] = tuple(data.get("notes", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ConsistencyPolicy(JsonContract):
    """Acceptance and retry policy for visual consistency."""

    minimum_overall_score: float = 0.90
    minimum_identity_score: float = 0.90
    max_attempts: int = 3
    require_references_for_characters: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_overall_score",
            _score(self.minimum_overall_score, "minimum_overall_score"),
        )
        object.__setattr__(
            self,
            "minimum_identity_score",
            _score(self.minimum_identity_score, "minimum_identity_score"),
        )
        object.__setattr__(
            self,
            "max_attempts",
            _positive_int(self.max_attempts, "max_attempts"),
        )
        if not isinstance(self.require_references_for_characters, bool):
            raise DomainValidationError(
                "require_references_for_characters must be a boolean"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def accepts(self, assessment: ConsistencyAssessment) -> bool:
        return (
            assessment.overall_score >= self.minimum_overall_score
            and assessment.identity_score >= self.minimum_identity_score
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "minimum_overall_score",
                "minimum_identity_score",
                "max_attempts",
                "require_references_for_characters",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class ReferenceAwareVisualGenerator(Protocol):
    """Visual generator that actually consumes resolved reference assets."""

    @property
    def engine_name(self) -> str:
        ...

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        ...

    def generate_with_references(
        self,
        request: VisualRequest,
        references: tuple[ReferenceAsset, ...],
    ) -> VisualResult:
        ...


@runtime_checkable
class ConsistencyEvaluator(Protocol):
    """Evaluator that measures a generated result against references."""

    @property
    def evaluator_name(self) -> str:
        ...

    def evaluate(
        self,
        request: VisualRequest,
        result: VisualResult,
        references: tuple[ReferenceAsset, ...],
    ) -> ConsistencyAssessment:
        ...


@dataclass(frozen=True, slots=True)
class ConsistencyAttempt(JsonContract):
    """One generation/evaluation attempt for a request."""

    attempt_number: int
    visual_result: VisualResult
    assessment: ConsistencyAssessment | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempt_number",
            _positive_int(self.attempt_number, "attempt_number"),
        )
        if not isinstance(self.visual_result, VisualResult):
            raise DomainValidationError(
                "visual_result must be a VisualResult"
            )
        if self.assessment is not None:
            if not isinstance(self.assessment, ConsistencyAssessment):
                raise DomainValidationError(
                    "assessment must be a ConsistencyAssessment"
                )
            if self.assessment.request_id != self.visual_result.request_id:
                raise DomainValidationError(
                    "assessment request_id does not match visual_result"
                )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["visual_result"] = self.visual_result.to_dict()
        payload["assessment"] = (
            self.assessment.to_dict() if self.assessment else None
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"attempt_number", "visual_result", "assessment", "metadata"},
        )
        data["visual_result"] = VisualResult.from_dict(data["visual_result"])
        if data.get("assessment") is not None:
            data["assessment"] = ConsistencyAssessment.from_dict(
                data["assessment"]
            )
        try:
            return cls(**data)
        except (KeyError, TypeError) as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ConsistentVisualResult(JsonContract):
    """Final consistency state for one request, including retries."""

    request_id: str
    accepted: bool
    attempts: tuple[ConsistencyAttempt, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _require_id(self.request_id, "request_id"),
        )
        if not isinstance(self.accepted, bool):
            raise DomainValidationError("accepted must be a boolean")
        attempts = tuple(self.attempts)
        if not attempts or not all(
            isinstance(attempt, ConsistencyAttempt)
            for attempt in attempts
        ):
            raise DomainValidationError(
                "attempts must contain at least one ConsistencyAttempt"
            )
        numbers = [attempt.attempt_number for attempt in attempts]
        if numbers != list(range(1, len(attempts) + 1)):
            raise DomainValidationError(
                "attempt numbers must be contiguous starting at 1"
            )
        if any(
            attempt.visual_result.request_id != self.request_id
            for attempt in attempts
        ):
            raise DomainValidationError(
                "attempt request_id does not match ConsistentVisualResult"
            )
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def final_attempt(self) -> ConsistencyAttempt:
        return self.attempts[-1]

    @property
    def known_cost_usd(self) -> float:
        return sum(
            attempt.visual_result.cost_usd or 0.0
            for attempt in self.attempts
        )

    @property
    def cost_complete(self) -> bool:
        return all(
            attempt.visual_result.cost_usd is not None
            for attempt in self.attempts
        )

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["attempts"] = [
            attempt.to_dict() for attempt in self.attempts
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"request_id", "accepted", "attempts", "metadata"},
        )
        data["attempts"] = tuple(
            ConsistencyAttempt.from_dict(item)
            for item in data.get("attempts", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ConsistencyReport(JsonContract):
    """Batch consistency report for a VisualGenerationPlan."""

    project_id: str
    story_id: str
    episode_id: str
    results: tuple[ConsistentVisualResult, ...]
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
            isinstance(result, ConsistentVisualResult)
            for result in results
        ):
            raise DomainValidationError(
                "results must contain at least one ConsistentVisualResult"
            )
        ids = [result.request_id for result in results]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(
                "request_id values must be unique within ConsistencyReport"
            )
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def success(self) -> bool:
        return all(result.accepted for result in self.results)

    @property
    def known_cost_usd(self) -> float:
        return sum(result.known_cost_usd for result in self.results)

    @property
    def cost_complete(self) -> bool:
        return all(result.cost_complete for result in self.results)

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
            ConsistentVisualResult.from_dict(item)
            for item in data.get("results", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


def bind_consistency_references(
    plan: VisualGenerationPlan,
    character_bible: CharacterBible,
    universe_bible: UniverseBible,
) -> VisualGenerationPlan:
    """Attach current Bible references without mutating prior sprint artifacts."""
    if character_bible.project_id != plan.project_id:
        raise DomainValidationError(
            "CharacterBible project_id does not match VisualGenerationPlan"
        )
    if universe_bible.project_id != plan.project_id:
        raise DomainValidationError(
            "UniverseBible project_id does not match VisualGenerationPlan"
        )

    requests = []
    for request in plan.requests:
        references = list(request.reference_asset_ids)
        for character_id in request.character_ids:
            references.extend(
                character_bible.resolve(character_id).reference_asset_ids
            )

        location_id = request.metadata.get("location_id")
        if isinstance(location_id, str) and location_id:
            references.extend(
                universe_bible.resolve(location_id).reference_asset_ids
            )

        requests.append(
            replace(
                request,
                reference_asset_ids=tuple(dict.fromkeys(references)),
            )
        )

    return VisualGenerationPlan(
        project_id=plan.project_id,
        story_id=plan.story_id,
        episode_id=plan.episode_id,
        requests=tuple(requests),
        metadata={
            **dict(plan.metadata),
            "consistency_references_bound": True,
        },
    )


def generate_consistent_visuals(
    generator: ReferenceAwareVisualGenerator,
    evaluator: ConsistencyEvaluator,
    plan: VisualGenerationPlan,
    catalog: ReferenceCatalog,
    policy: ConsistencyPolicy,
    *,
    max_cost_usd: float | None = None,
) -> ConsistencyReport:
    """Generate and evaluate each request until accepted or attempts are exhausted."""
    if catalog.project_id != plan.project_id:
        raise DomainValidationError(
            "ReferenceCatalog project_id does not match VisualGenerationPlan"
        )

    resolved: dict[str, tuple[ReferenceAsset, ...]] = {}
    for request in plan.requests:
        references = catalog.resolve_many(request.reference_asset_ids)
        if (
            policy.require_references_for_characters
            and request.character_ids
            and not references
        ):
            raise DomainValidationError(
                f"request {request.request_id!r} has characters but no "
                "reference assets"
            )
        resolved[request.request_id] = references

    budget = _optional_non_negative(max_cost_usd, "max_cost_usd")
    if budget is not None:
        projected = 0.0
        for request in plan.requests:
            estimate = generator.estimate_cost_usd(request)
            if estimate is None:
                raise DomainValidationError(
                    "cost estimate required before budget-controlled "
                    "consistency generation"
                )
            projected += (
                _non_negative(estimate, "estimated_cost_usd")
                * policy.max_attempts
            )
        if projected > budget:
            raise DomainValidationError(
                f"projected worst-case consistency cost "
                f"{projected:.6f} USD exceeds budget {budget:.6f} USD"
            )

    results = []
    for request in plan.requests:
        attempts = []
        accepted = False
        references = resolved[request.request_id]

        for attempt_number in range(1, policy.max_attempts + 1):
            visual_result = generator.generate_with_references(
                request,
                references,
            )
            if not isinstance(visual_result, VisualResult):
                raise DomainValidationError(
                    "ReferenceAwareVisualGenerator must return a VisualResult"
                )
            if visual_result.request_id != request.request_id:
                raise DomainValidationError(
                    "reference-aware generator returned a result for a "
                    "different request"
                )

            assessment = None
            if visual_result.success:
                assessment = evaluator.evaluate(
                    request,
                    visual_result,
                    references,
                )
                if not isinstance(assessment, ConsistencyAssessment):
                    raise DomainValidationError(
                        "ConsistencyEvaluator must return a "
                        "ConsistencyAssessment"
                    )
                if assessment.request_id != request.request_id:
                    raise DomainValidationError(
                        "ConsistencyEvaluator returned an assessment for a "
                        "different request"
                    )
                accepted = policy.accepts(assessment)

            attempts.append(
                ConsistencyAttempt(
                    attempt_number=attempt_number,
                    visual_result=visual_result,
                    assessment=assessment,
                )
            )
            if accepted:
                break

        results.append(
            ConsistentVisualResult(
                request_id=request.request_id,
                accepted=accepted,
                attempts=tuple(attempts),
                metadata={
                    "generator": generator.engine_name,
                    "evaluator": evaluator.evaluator_name,
                },
            )
        )

    return ConsistencyReport(
        project_id=plan.project_id,
        story_id=plan.story_id,
        episode_id=plan.episode_id,
        results=tuple(results),
        metadata={
            "minimum_overall_score": policy.minimum_overall_score,
            "minimum_identity_score": policy.minimum_identity_score,
            "max_attempts": policy.max_attempts,
        },
    )
