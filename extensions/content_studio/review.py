"""Human review contracts and auditable decision workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.consistency import ConsistencyReport
from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    SCHEMA_VERSION,
)
from extensions.content_studio.media import MediaAssemblyResult
from extensions.content_studio.quality import HumanReviewGate, RenderQAReport
from extensions.content_studio.safety import SafetyAssessment

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ACTIONS = {"approve", "reject", "regenerate_shot", "regenerate_episode"}


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DomainValidationError(f"{name} has invalid identifier: {value!r}")
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("metadata must be a mapping")
    try:
        decoded = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("metadata must be JSON-compatible") from exc
    if not isinstance(decoded, dict):
        raise DomainValidationError("metadata must serialize to an object")
    return decoded


def _payload(payload: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainValidationError("payload must be a mapping")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DomainValidationError("unsupported schema_version")
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


def _timestamp(value: str) -> str:
    value = _text(value, "decided_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainValidationError(
            "decided_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise DomainValidationError("decided_at must include a timezone")
    return value


@dataclass(frozen=True, slots=True)
class ReviewPackage(JsonContract):
    """All evidence needed by a human reviewer for one episode."""

    package_id: str
    project_id: str
    episode_id: str
    render_uri: str
    safety_assessments: tuple[SafetyAssessment, ...]
    render_qa: RenderQAReport
    gate: HumanReviewGate
    shot_ids: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("package_id", "project_id", "episode_id"):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        object.__setattr__(self, "render_uri", _text(self.render_uri, "render_uri"))

        assessments = tuple(self.safety_assessments)
        if not assessments or not all(
            isinstance(item, SafetyAssessment) for item in assessments
        ):
            raise DomainValidationError(
                "safety_assessments must contain at least one SafetyAssessment"
            )
        object.__setattr__(self, "safety_assessments", assessments)

        if not isinstance(self.render_qa, RenderQAReport):
            raise DomainValidationError("render_qa must be a RenderQAReport")
        if not isinstance(self.gate, HumanReviewGate):
            raise DomainValidationError("gate must be a HumanReviewGate")
        if self.render_qa.project_id != self.project_id:
            raise DomainValidationError("render_qa project_id does not match package")
        if self.render_qa.episode_id != self.episode_id:
            raise DomainValidationError("render_qa episode_id does not match package")
        if self.gate.project_id != self.project_id:
            raise DomainValidationError("gate project_id does not match package")
        if self.gate.episode_id != self.episode_id:
            raise DomainValidationError("gate episode_id does not match package")

        shots = tuple(_id(value, "shot_ids") for value in self.shot_ids)
        if not shots:
            raise DomainValidationError("shot_ids must contain at least one shot")
        if len(shots) != len(set(shots)):
            raise DomainValidationError("shot_ids must not contain duplicates")
        object.__setattr__(self, "shot_ids", shots)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["safety_assessments"] = [
            item.to_dict() for item in self.safety_assessments
        ]
        payload["render_qa"] = self.render_qa.to_dict()
        payload["gate"] = self.gate.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "package_id",
                "project_id",
                "episode_id",
                "render_uri",
                "safety_assessments",
                "render_qa",
                "gate",
                "shot_ids",
                "metadata",
            },
        )
        data["safety_assessments"] = tuple(
            SafetyAssessment.from_dict(item)
            for item in data.get("safety_assessments", ())
        )
        data["render_qa"] = RenderQAReport.from_dict(data["render_qa"])
        data["gate"] = HumanReviewGate.from_dict(data["gate"])
        data["shot_ids"] = tuple(data.get("shot_ids", ()))
        try:
            return cls(**data)
        except (KeyError, TypeError) as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ReviewDecision(JsonContract):
    """One explicit human decision. Approval is not publication."""

    decision_id: str
    package_id: str
    reviewer_id: str
    action: str
    decided_at: str
    comments: str
    target_shot_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("decision_id", "package_id", "reviewer_id"):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        if self.action not in _ACTIONS:
            raise DomainValidationError(f"unsupported review action: {self.action!r}")
        object.__setattr__(self, "decided_at", _timestamp(self.decided_at))
        object.__setattr__(self, "comments", _text(self.comments, "comments"))
        target = self.target_shot_id
        if target is not None:
            target = _id(target, "target_shot_id")
        if self.action == "regenerate_shot" and target is None:
            raise DomainValidationError(
                "regenerate_shot requires target_shot_id"
            )
        if self.action != "regenerate_shot" and target is not None:
            raise DomainValidationError(
                "target_shot_id is only valid for regenerate_shot"
            )
        object.__setattr__(self, "target_shot_id", target)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def approved(self) -> bool:
        return self.action == "approve"

    @property
    def requests_regeneration(self) -> bool:
        return self.action in {"regenerate_shot", "regenerate_episode"}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "decision_id",
                "package_id",
                "reviewer_id",
                "action",
                "decided_at",
                "comments",
                "target_shot_id",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ReviewAuditTrail(JsonContract):
    """Append-only logical audit trail for one review package."""

    package_id: str
    decisions: tuple[ReviewDecision, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_id", _id(self.package_id, "package_id"))
        decisions = tuple(self.decisions)
        if not all(isinstance(item, ReviewDecision) for item in decisions):
            raise DomainValidationError(
                "decisions must contain ReviewDecision values"
            )
        ids = [item.decision_id for item in decisions]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("decision_id values must be unique")
        if any(item.package_id != self.package_id for item in decisions):
            raise DomainValidationError(
                "all decisions must belong to the audit trail package"
            )
        timestamps = [
            datetime.fromisoformat(item.decided_at.replace("Z", "+00:00"))
            for item in decisions
        ]
        if timestamps != sorted(timestamps):
            raise DomainValidationError(
                "decisions must be ordered by decided_at"
            )
        object.__setattr__(self, "decisions", decisions)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def latest(self) -> ReviewDecision | None:
        return self.decisions[-1] if self.decisions else None

    def append(self, decision: ReviewDecision) -> "ReviewAuditTrail":
        if decision.package_id != self.package_id:
            raise DomainValidationError("decision package does not match audit trail")
        return ReviewAuditTrail(
            package_id=self.package_id,
            decisions=(*self.decisions, decision),
            metadata=self.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["decisions"] = [item.to_dict() for item in self.decisions]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"package_id", "decisions", "metadata"})
        data["decisions"] = tuple(
            ReviewDecision.from_dict(item) for item in data.get("decisions", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class ReviewDecisionStore(Protocol):
    def list(self, package_id: str) -> ReviewAuditTrail:
        ...

    def append(self, decision: ReviewDecision) -> ReviewAuditTrail:
        ...


def build_review_package(
    *,
    package_id: str,
    media: MediaAssemblyResult,
    consistency: ConsistencyReport,
    safety_assessments: tuple[SafetyAssessment, ...],
    render_qa: RenderQAReport,
    gate: HumanReviewGate,
) -> ReviewPackage:
    """Build review evidence only after a final render exists."""
    if media.video is None:
        raise DomainValidationError("media result must contain a render artifact")
    if render_qa.project_id != consistency.project_id:
        raise DomainValidationError("render QA and consistency project do not match")
    if render_qa.episode_id != consistency.episode_id:
        raise DomainValidationError("render QA and consistency episode do not match")

    return ReviewPackage(
        package_id=package_id,
        project_id=consistency.project_id,
        episode_id=consistency.episode_id,
        render_uri=media.video.uri,
        safety_assessments=safety_assessments,
        render_qa=render_qa,
        gate=gate,
        shot_ids=tuple(item.request_id for item in consistency.results),
        metadata={
            "publication_performed": False,
            "human_decision_required": True,
        },
    )


def validate_review_decision(
    package: ReviewPackage,
    decision: ReviewDecision,
) -> None:
    """Validate a human action against the package without publishing anything."""
    if decision.package_id != package.package_id:
        raise DomainValidationError("decision package_id does not match package")
    if decision.action == "approve" and not package.gate.eligible_for_human_review:
        raise DomainValidationError(
            "package is not eligible for human approval"
        )
    if (
        decision.action == "regenerate_shot"
        and decision.target_shot_id not in package.shot_ids
    ):
        raise DomainValidationError(
            "target_shot_id does not exist in ReviewPackage"
        )
