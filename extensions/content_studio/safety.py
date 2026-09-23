"""Provider-neutral safety review contracts for Content Studio AI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    SCHEMA_VERSION,
)

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_SEVERITIES = {"info", "warning", "block"}
_MODALITIES = {"script", "subtitle", "audio", "visual", "metadata"}


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DomainValidationError(f"{name} has invalid identifier: {value!r}")
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _texts(values: tuple[str, ...] | list[str], name: str) -> tuple[str, ...]:
    normalized = tuple(_text(value, name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{name} must not contain duplicates")
    return normalized


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
        raise DomainValidationError(
            f"unsupported schema_version {payload.get('schema_version')!r}"
        )
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


@dataclass(frozen=True, slots=True)
class SafetyRule(JsonContract):
    rule_id: str
    category: str
    severity: str
    terms: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _id(self.rule_id, "rule_id"))
        object.__setattr__(self, "category", _id(self.category, "category"))
        if self.severity not in _SEVERITIES:
            raise DomainValidationError("severity must be info, warning, or block")
        object.__setattr__(self, "terms", _texts(self.terms, "terms"))
        if not self.terms:
            raise DomainValidationError("terms must contain at least one value")
        object.__setattr__(
            self, "description", _text(self.description, "description")
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload, {"rule_id", "category", "severity", "terms", "description"}
        )
        data["terms"] = tuple(data.get("terms", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SafetyPolicy(JsonContract):
    policy_id: str
    audience_min_age: int
    audience_max_age: int
    rules: tuple[SafetyRule, ...]
    required_modalities: tuple[str, ...] = (
        "script",
        "subtitle",
        "audio",
        "visual",
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _id(self.policy_id, "policy_id"))
        for name in ("audience_min_age", "audience_max_age"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainValidationError(f"{name} must be a non-negative integer")
        if self.audience_min_age > self.audience_max_age:
            raise DomainValidationError(
                "audience_min_age must not exceed audience_max_age"
            )
        rules = tuple(self.rules)
        if not rules or not all(isinstance(rule, SafetyRule) for rule in rules):
            raise DomainValidationError("rules must contain SafetyRule values")
        ids = [rule.rule_id for rule in rules]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("rule_id values must be unique")
        modalities = tuple(self.required_modalities)
        if not modalities or any(m not in _MODALITIES for m in modalities):
            raise DomainValidationError("required_modalities contains invalid value")
        if len(modalities) != len(set(modalities)):
            raise DomainValidationError("required_modalities must be unique")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "required_modalities", modalities)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["rules"] = [rule.to_dict() for rule in self.rules]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "policy_id",
                "audience_min_age",
                "audience_max_age",
                "rules",
                "required_modalities",
                "metadata",
            },
        )
        data["rules"] = tuple(
            SafetyRule.from_dict(item) for item in data.get("rules", ())
        )
        data["required_modalities"] = tuple(
            data.get(
                "required_modalities",
                ("script", "subtitle", "audio", "visual"),
            )
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SafetyReviewRequest(JsonContract):
    request_id: str
    project_id: str
    episode_id: str
    script: str
    subtitle_text: str = ""
    audio_uri: str | None = None
    visual_uris: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("request_id", "project_id", "episode_id"):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        object.__setattr__(self, "script", _text(self.script, "script"))
        if not isinstance(self.subtitle_text, str):
            raise DomainValidationError("subtitle_text must be a string")
        if self.audio_uri is not None:
            object.__setattr__(
                self, "audio_uri", _text(self.audio_uri, "audio_uri")
            )
        object.__setattr__(
            self, "visual_uris", _texts(self.visual_uris, "visual_uris")
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "project_id",
                "episode_id",
                "script",
                "subtitle_text",
                "audio_uri",
                "visual_uris",
                "metadata",
            },
        )
        data["visual_uris"] = tuple(data.get("visual_uris", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SafetyFinding(JsonContract):
    finding_id: str
    category: str
    severity: str
    modality: str
    evidence: str
    rule_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "finding_id", _id(self.finding_id, "finding_id")
        )
        object.__setattr__(self, "category", _id(self.category, "category"))
        if self.severity not in _SEVERITIES:
            raise DomainValidationError("invalid finding severity")
        if self.modality not in _MODALITIES:
            raise DomainValidationError("invalid finding modality")
        object.__setattr__(self, "evidence", _text(self.evidence, "evidence"))
        if self.rule_id is not None:
            object.__setattr__(self, "rule_id", _id(self.rule_id, "rule_id"))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "finding_id",
                "category",
                "severity",
                "modality",
                "evidence",
                "rule_id",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SafetyAssessment(JsonContract):
    request_id: str
    reviewer: str
    reviewed_modalities: tuple[str, ...]
    findings: tuple[SafetyFinding, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _id(self.request_id, "request_id")
        )
        object.__setattr__(self, "reviewer", _text(self.reviewer, "reviewer"))
        modalities = tuple(self.reviewed_modalities)
        if not modalities or any(m not in _MODALITIES for m in modalities):
            raise DomainValidationError("reviewed_modalities contains invalid value")
        if len(modalities) != len(set(modalities)):
            raise DomainValidationError("reviewed_modalities must be unique")
        findings = tuple(self.findings)
        if not all(isinstance(item, SafetyFinding) for item in findings):
            raise DomainValidationError("findings must contain SafetyFinding values")
        ids = [item.finding_id for item in findings]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("finding_id values must be unique")
        object.__setattr__(self, "reviewed_modalities", modalities)
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def has_blocking_findings(self) -> bool:
        return any(item.severity == "block" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["findings"] = [item.to_dict() for item in self.findings]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "reviewer",
                "reviewed_modalities",
                "findings",
                "metadata",
            },
        )
        data["reviewed_modalities"] = tuple(
            data.get("reviewed_modalities", ())
        )
        data["findings"] = tuple(
            SafetyFinding.from_dict(item) for item in data.get("findings", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class SafetyReviewer(Protocol):
    @property
    def reviewer_name(self) -> str:
        ...

    def review(
        self,
        request: SafetyReviewRequest,
        policy: SafetyPolicy,
    ) -> SafetyAssessment:
        ...


class TextRuleSafetyReviewer:
    """Deterministic text preflight. It is not a multimodal safety reviewer."""

    @property
    def reviewer_name(self) -> str:
        return "text-rule-preflight"

    def review(
        self,
        request: SafetyReviewRequest,
        policy: SafetyPolicy,
    ) -> SafetyAssessment:
        sources = [("script", request.script)]
        if request.subtitle_text.strip():
            sources.append(("subtitle", request.subtitle_text))
        findings: list[SafetyFinding] = []
        index = 0
        for modality, text in sources:
            normalized = text.casefold()
            for rule in policy.rules:
                for term in rule.terms:
                    if term.casefold() not in normalized:
                        continue
                    index += 1
                    findings.append(
                        SafetyFinding(
                            finding_id=f"finding-{index}",
                            category=rule.category,
                            severity=rule.severity,
                            modality=modality,
                            evidence=f"matched configured term: {term}",
                            rule_id=rule.rule_id,
                        )
                    )
                    break
        return SafetyAssessment(
            request_id=request.request_id,
            reviewer=self.reviewer_name,
            reviewed_modalities=tuple(modality for modality, _ in sources),
            findings=tuple(findings),
            metadata={
                "preflight_only": True,
                "does_not_review_visual_or_audio_content": True,
            },
        )


def evaluate_safety_coverage(
    policy: SafetyPolicy,
    assessments: tuple[SafetyAssessment, ...],
) -> tuple[bool, tuple[str, ...]]:
    """Require complete modality coverage and zero blocking findings."""
    if not assessments:
        return False, policy.required_modalities
    covered = {
        modality
        for assessment in assessments
        for modality in assessment.reviewed_modalities
    }
    missing = tuple(
        modality
        for modality in policy.required_modalities
        if modality not in covered
    )
    blocked = any(a.has_blocking_findings for a in assessments)
    return not blocked and not missing, missing
