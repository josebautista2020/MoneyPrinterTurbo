"""Deterministic render QA and mandatory human-review gate."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Self

from extensions.content_studio.consistency import ConsistencyReport
from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.media import MediaAssemblyResult
from extensions.content_studio.safety import (
    SafetyAssessment,
    SafetyPolicy,
    evaluate_safety_coverage,
)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a non-empty string")
    return value.strip()


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


@dataclass(frozen=True, slots=True)
class RenderQAPolicy(JsonContract):
    minimum_duration_seconds: float
    maximum_duration_seconds: float
    duration_tolerance_seconds: float = 1.0
    require_audio: bool = True
    require_subtitles: bool = True
    require_consistency_pass: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "minimum_duration_seconds",
            "maximum_duration_seconds",
            "duration_tolerance_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise DomainValidationError(f"{name} must be non-negative finite")
            object.__setattr__(self, name, float(value))
        if self.minimum_duration_seconds > self.maximum_duration_seconds:
            raise DomainValidationError("minimum duration exceeds maximum duration")
        for name in (
            "require_audio",
            "require_subtitles",
            "require_consistency_pass",
        ):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "minimum_duration_seconds",
                "maximum_duration_seconds",
                "duration_tolerance_seconds",
                "require_audio",
                "require_subtitles",
                "require_consistency_pass",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class QACheck(JsonContract):
    check_id: str
    passed: bool
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _text(self.check_id, "check_id"))
        if not isinstance(self.passed, bool):
            raise DomainValidationError("passed must be boolean")
        object.__setattr__(self, "message", _text(self.message, "message"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"check_id", "passed", "message"})
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RenderQAReport(JsonContract):
    project_id: str
    episode_id: str
    checks: tuple[QACheck, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(self, "episode_id", _text(self.episode_id, "episode_id"))
        checks = tuple(self.checks)
        if not checks or not all(isinstance(item, QACheck) for item in checks):
            raise DomainValidationError("checks must contain QACheck values")
        ids = [item.check_id for item in checks]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("check_id values must be unique")
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.checks)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["checks"] = [item.to_dict() for item in self.checks]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"project_id", "episode_id", "checks", "metadata"})
        data["checks"] = tuple(
            QACheck.from_dict(item) for item in data.get("checks", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


def evaluate_render_qa(
    project: ProjectSpec,
    media: MediaAssemblyResult,
    consistency: ConsistencyReport,
    policy: RenderQAPolicy,
) -> RenderQAReport:
    if project.project_id != consistency.project_id:
        raise DomainValidationError("project and consistency report do not match")
    checks: list[QACheck] = []

    checks.append(
        QACheck(
            "media-success",
            media.success,
            "media assembly must complete successfully",
        )
    )
    checks.append(
        QACheck(
            "consistency",
            (not policy.require_consistency_pass) or consistency.success,
            "visual consistency gate must pass",
        )
    )
    checks.append(
        QACheck(
            "audio",
            (not policy.require_audio) or media.audio is not None,
            "audio artifact must be present",
        )
    )
    checks.append(
        QACheck(
            "subtitles",
            (not policy.require_subtitles) or media.subtitle is not None,
            "subtitle artifact must be present",
        )
    )

    video = media.video
    if video is None:
        checks.extend(
            (
                QACheck("resolution", False, "render artifact must be present"),
                QACheck("duration", False, "render artifact must be present"),
            )
        )
    else:
        expected_w, expected_h = (
            int(value) for value in project.resolution.split("x", 1)
        )
        checks.append(
            QACheck(
                "resolution",
                video.width == expected_w and video.height == expected_h,
                "render dimensions must match ProjectSpec",
            )
        )
        duration_ok = (
            policy.minimum_duration_seconds
            <= video.duration_seconds
            <= policy.maximum_duration_seconds
        )
        checks.append(
            QACheck(
                "duration",
                duration_ok,
                "render duration must be inside configured QA bounds",
            )
        )

    return RenderQAReport(
        project_id=project.project_id,
        episode_id=consistency.episode_id,
        checks=tuple(checks),
        metadata={
            "publication_performed": False,
            "deterministic_metadata_qa": True,
        },
    )


@dataclass(frozen=True, slots=True)
class HumanReviewGate(JsonContract):
    project_id: str
    episode_id: str
    safety_complete: bool
    safety_blocked: bool
    render_qa_passed: bool
    eligible_for_human_review: bool
    publication_allowed: bool = False
    missing_safety_modalities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(self, "episode_id", _text(self.episode_id, "episode_id"))
        for name in (
            "safety_complete",
            "safety_blocked",
            "render_qa_passed",
            "eligible_for_human_review",
            "publication_allowed",
        ):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        if self.publication_allowed:
            raise DomainValidationError(
                "publication_allowed must remain False before explicit human approval"
            )
        object.__setattr__(
            self,
            "missing_safety_modalities",
            tuple(self.missing_safety_modalities),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "project_id",
                "episode_id",
                "safety_complete",
                "safety_blocked",
                "render_qa_passed",
                "eligible_for_human_review",
                "publication_allowed",
                "missing_safety_modalities",
                "metadata",
            },
        )
        data["missing_safety_modalities"] = tuple(
            data.get("missing_safety_modalities", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


def build_human_review_gate(
    project_id: str,
    episode_id: str,
    safety_policy: SafetyPolicy,
    safety_assessments: tuple[SafetyAssessment, ...],
    render_qa: RenderQAReport,
) -> HumanReviewGate:
    safety_complete, missing = evaluate_safety_coverage(
        safety_policy, safety_assessments
    )
    safety_blocked = any(
        assessment.has_blocking_findings for assessment in safety_assessments
    )
    eligible = safety_complete and not safety_blocked and render_qa.passed
    return HumanReviewGate(
        project_id=project_id,
        episode_id=episode_id,
        safety_complete=safety_complete,
        safety_blocked=safety_blocked,
        render_qa_passed=render_qa.passed,
        eligible_for_human_review=eligible,
        publication_allowed=False,
        missing_safety_modalities=missing,
        metadata={
            "human_approval_required": True,
            "automatic_publication": False,
        },
    )
