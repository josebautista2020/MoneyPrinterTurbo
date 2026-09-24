"""Governed, provider-neutral publishing contracts for Content Studio AI."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    SCHEMA_VERSION,
)
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewPackage,
    validate_review_decision,
)

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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


def _timestamp(value: str, name: str) -> str:
    value = _text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainValidationError(
            f"{name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise DomainValidationError(f"{name} must include a timezone")
    return value


@dataclass(frozen=True, slots=True)
class PublishGrant(JsonContract):
    """One platform/account pair permitted by policy."""

    platform: str
    account_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _id(self.platform, "platform"))
        object.__setattr__(
            self,
            "account_ref",
            _text(self.account_ref, "account_ref"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"platform", "account_ref"})
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublishTarget(JsonContract):
    """Destination-specific publishing intent."""

    platform: str
    account_ref: str
    privacy_level: str = "PUBLIC_TO_EVERYONE"
    youtube_privacy_status: str | None = None
    youtube_made_for_kids: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _id(self.platform, "platform"))
        object.__setattr__(
            self,
            "account_ref",
            _text(self.account_ref, "account_ref"),
        )
        object.__setattr__(
            self,
            "privacy_level",
            _text(self.privacy_level, "privacy_level"),
        )
        object.__setattr__(
            self,
            "youtube_privacy_status",
            _optional_text(
                self.youtube_privacy_status,
                "youtube_privacy_status",
            ),
        )
        if (
            self.youtube_made_for_kids is not None
            and not isinstance(self.youtube_made_for_kids, bool)
        ):
            raise DomainValidationError(
                "youtube_made_for_kids must be boolean or null"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def is_youtube(self) -> bool:
        return self.platform.startswith("youtube")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "platform",
                "account_ref",
                "privacy_level",
                "youtube_privacy_status",
                "youtube_made_for_kids",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublishingPolicy(JsonContract):
    """Default-deny publishing governance."""

    policy_id: str
    allowed_targets: tuple[PublishGrant, ...]
    live_publish_enabled: bool = False
    max_targets_per_request: int = 3
    require_latest_approval: bool = True
    require_explicit_youtube_audience: bool = True
    require_synthetic_media_declaration: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _id(self.policy_id, "policy_id"))
        grants = tuple(self.allowed_targets)
        if not grants or not all(isinstance(item, PublishGrant) for item in grants):
            raise DomainValidationError(
                "allowed_targets must contain at least one PublishGrant"
            )
        keys = [(item.platform, item.account_ref) for item in grants]
        if len(keys) != len(set(keys)):
            raise DomainValidationError("allowed_targets must be unique")
        object.__setattr__(self, "allowed_targets", grants)

        if (
            isinstance(self.max_targets_per_request, bool)
            or not isinstance(self.max_targets_per_request, int)
            or self.max_targets_per_request <= 0
        ):
            raise DomainValidationError(
                "max_targets_per_request must be a positive integer"
            )
        for name in (
            "live_publish_enabled",
            "require_latest_approval",
            "require_explicit_youtube_audience",
            "require_synthetic_media_declaration",
        ):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["allowed_targets"] = [
            item.to_dict() for item in self.allowed_targets
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "policy_id",
                "allowed_targets",
                "live_publish_enabled",
                "max_targets_per_request",
                "require_latest_approval",
                "require_explicit_youtube_audience",
                "require_synthetic_media_declaration",
                "metadata",
            },
        )
        data["allowed_targets"] = tuple(
            PublishGrant.from_dict(item)
            for item in data.get("allowed_targets", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublishRequest(JsonContract):
    """Explicit request to publish one approved render."""

    request_id: str
    package_id: str
    decision_id: str
    video_uri: str
    title: str
    targets: tuple[PublishTarget, ...]
    idempotency_key: str
    description: str = ""
    tags: tuple[str, ...] = ()
    contains_synthetic_media: bool = True
    dry_run: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "package_id",
            "decision_id",
            "idempotency_key",
        ):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        object.__setattr__(self, "video_uri", _text(self.video_uri, "video_uri"))
        object.__setattr__(self, "title", _text(self.title, "title"))
        if not isinstance(self.description, str):
            raise DomainValidationError("description must be a string")
        tags = tuple(_text(value, "tags") for value in self.tags)
        if len(tags) != len(set(tags)):
            raise DomainValidationError("tags must not contain duplicates")
        object.__setattr__(self, "tags", tags)
        targets = tuple(self.targets)
        if not targets or not all(
            isinstance(item, PublishTarget) for item in targets
        ):
            raise DomainValidationError(
                "targets must contain at least one PublishTarget"
            )
        keys = [(item.platform, item.account_ref) for item in targets]
        if len(keys) != len(set(keys)):
            raise DomainValidationError("targets must be unique")
        object.__setattr__(self, "targets", targets)
        if not isinstance(self.contains_synthetic_media, bool):
            raise DomainValidationError(
                "contains_synthetic_media must be boolean"
            )
        if not isinstance(self.dry_run, bool):
            raise DomainValidationError("dry_run must be boolean")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["targets"] = [item.to_dict() for item in self.targets]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "package_id",
                "decision_id",
                "video_uri",
                "title",
                "targets",
                "idempotency_key",
                "description",
                "tags",
                "contains_synthetic_media",
                "dry_run",
                "metadata",
            },
        )
        data["targets"] = tuple(
            PublishTarget.from_dict(item) for item in data.get("targets", ())
        )
        data["tags"] = tuple(data.get("tags", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublishTargetResult(JsonContract):
    platform: str
    account_ref: str
    success: bool
    external_request_id: str | None = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _id(self.platform, "platform"))
        object.__setattr__(
            self,
            "account_ref",
            _text(self.account_ref, "account_ref"),
        )
        if not isinstance(self.success, bool):
            raise DomainValidationError("success must be boolean")
        object.__setattr__(
            self,
            "external_request_id",
            _optional_text(
                self.external_request_id,
                "external_request_id",
            ),
        )
        object.__setattr__(self, "error", _optional_text(self.error, "error"))
        if self.success and self.error is not None:
            raise DomainValidationError(
                "successful target result must not contain error"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "platform",
                "account_ref",
                "success",
                "external_request_id",
                "error",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublishResult(JsonContract):
    request_id: str
    publisher: str
    success: bool
    dry_run: bool
    outcomes: tuple[PublishTargetResult, ...]
    idempotent_replay: bool = False
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _id(self.request_id, "request_id"))
        object.__setattr__(self, "publisher", _text(self.publisher, "publisher"))
        for name in ("success", "dry_run", "idempotent_replay"):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        outcomes = tuple(self.outcomes)
        if not outcomes or not all(
            isinstance(item, PublishTargetResult) for item in outcomes
        ):
            raise DomainValidationError(
                "outcomes must contain at least one PublishTargetResult"
            )
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "error", _optional_text(self.error, "error"))
        if self.success and self.error is not None:
            raise DomainValidationError(
                "successful PublishResult must not contain error"
            )
        if self.success and not all(item.success for item in outcomes):
            raise DomainValidationError(
                "successful PublishResult requires all outcomes to succeed"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["outcomes"] = [item.to_dict() for item in self.outcomes]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "request_id",
                "publisher",
                "success",
                "dry_run",
                "outcomes",
                "idempotent_replay",
                "error",
                "metadata",
            },
        )
        data["outcomes"] = tuple(
            PublishTargetResult.from_dict(item)
            for item in data.get("outcomes", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class Publisher(Protocol):
    @property
    def publisher_name(self) -> str:
        ...

    def publish(self, request: PublishRequest) -> PublishResult:
        ...


@dataclass(frozen=True, slots=True)
class PublicationRecord(JsonContract):
    record_id: str
    idempotency_key: str
    request_fingerprint: str
    request: PublishRequest
    result: PublishResult
    recorded_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _id(self.record_id, "record_id"))
        object.__setattr__(
            self,
            "idempotency_key",
            _id(self.idempotency_key, "idempotency_key"),
        )
        if not re.fullmatch(r"[0-9a-f]{64}", self.request_fingerprint):
            raise DomainValidationError(
                "request_fingerprint must be a SHA-256 hex digest"
            )
        if not isinstance(self.request, PublishRequest):
            raise DomainValidationError("request must be a PublishRequest")
        if not isinstance(self.result, PublishResult):
            raise DomainValidationError("result must be a PublishResult")
        if self.request.idempotency_key != self.idempotency_key:
            raise DomainValidationError(
                "record idempotency_key does not match request"
            )
        if self.request.fingerprint != self.request_fingerprint:
            raise DomainValidationError(
                "record request_fingerprint does not match request"
            )
        if self.result.request_id != self.request.request_id:
            raise DomainValidationError(
                "result request_id does not match request"
            )
        object.__setattr__(
            self,
            "recorded_at",
            _timestamp(self.recorded_at, "recorded_at"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["request"] = self.request.to_dict()
        payload["result"] = self.result.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "record_id",
                "idempotency_key",
                "request_fingerprint",
                "request",
                "result",
                "recorded_at",
                "metadata",
            },
        )
        data["request"] = PublishRequest.from_dict(data["request"])
        data["result"] = PublishResult.from_dict(data["result"])
        try:
            return cls(**data)
        except (KeyError, TypeError) as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PublicationAuditTrail(JsonContract):
    records: tuple[PublicationRecord, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if not all(isinstance(item, PublicationRecord) for item in records):
            raise DomainValidationError(
                "records must contain PublicationRecord values"
            )
        ids = [item.record_id for item in records]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("record_id values must be unique")
        keys = [item.idempotency_key for item in records]
        if len(keys) != len(set(keys)):
            raise DomainValidationError(
                "idempotency_key values must be unique in audit trail"
            )
        timestamps = [
            datetime.fromisoformat(item.recorded_at.replace("Z", "+00:00"))
            for item in records
        ]
        if timestamps != sorted(timestamps):
            raise DomainValidationError(
                "publication records must be ordered by recorded_at"
            )
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["records"] = [item.to_dict() for item in self.records]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"records", "metadata"})
        data["records"] = tuple(
            PublicationRecord.from_dict(item)
            for item in data.get("records", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class PublicationLedger(Protocol):
    def get(self, idempotency_key: str) -> PublicationRecord | None:
        ...

    def append(self, record: PublicationRecord) -> PublicationAuditTrail:
        ...


def validate_publish_authorization(
    package: ReviewPackage,
    decision: ReviewDecision,
    review_audit: ReviewAuditTrail,
    request: PublishRequest,
    policy: PublishingPolicy,
) -> None:
    """Fail closed unless the exact render has a current audited approval."""
    validate_review_decision(package, decision)
    if decision.action != "approve":
        raise DomainValidationError(
            "publishing requires ReviewDecision(action='approve')"
        )
    if review_audit.package_id != package.package_id:
        raise DomainValidationError(
            "review audit package_id does not match ReviewPackage"
        )
    audited = {
        item.decision_id: item for item in review_audit.decisions
    }
    if decision.decision_id not in audited:
        raise DomainValidationError(
            "approval decision is not present in ReviewAuditTrail"
        )
    if audited[decision.decision_id] != decision:
        raise DomainValidationError(
            "approval decision does not match audited decision"
        )
    if (
        policy.require_latest_approval
        and (
            review_audit.latest is None
            or review_audit.latest.decision_id != decision.decision_id
        )
    ):
        raise DomainValidationError(
            "publishing requires the approval to be the latest review decision"
        )
    if request.package_id != package.package_id:
        raise DomainValidationError(
            "PublishRequest package_id does not match ReviewPackage"
        )
    if request.decision_id != decision.decision_id:
        raise DomainValidationError(
            "PublishRequest decision_id does not match approval"
        )
    if request.video_uri != package.render_uri:
        raise DomainValidationError(
            "PublishRequest video_uri does not match approved render"
        )
    if len(request.targets) > policy.max_targets_per_request:
        raise DomainValidationError(
            "PublishRequest exceeds max_targets_per_request"
        )

    allowed = {
        (grant.platform, grant.account_ref)
        for grant in policy.allowed_targets
    }
    for target in request.targets:
        key = (target.platform, target.account_ref)
        if key not in allowed:
            raise DomainValidationError(
                f"publishing target is not allowlisted: {key!r}"
            )
        if (
            target.is_youtube
            and policy.require_explicit_youtube_audience
            and target.youtube_made_for_kids is None
        ):
            raise DomainValidationError(
                "YouTube target requires explicit youtube_made_for_kids"
            )

    if (
        policy.require_synthetic_media_declaration
        and not request.contains_synthetic_media
    ):
        raise DomainValidationError(
            "publishing policy requires synthetic-media declaration"
        )
    if not request.dry_run and not policy.live_publish_enabled:
        raise DomainValidationError(
            "live publishing is disabled by PublishingPolicy"
        )


def execute_publishing_gateway(
    publisher: Publisher,
    ledger: PublicationLedger,
    package: ReviewPackage,
    decision: ReviewDecision,
    review_audit: ReviewAuditTrail,
    request: PublishRequest,
    policy: PublishingPolicy,
    *,
    record_id: str,
    recorded_at: str,
) -> PublishResult:
    """Validate, deduplicate, optionally publish, and append audit evidence."""
    validate_publish_authorization(
        package,
        decision,
        review_audit,
        request,
        policy,
    )

    existing = ledger.get(request.idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != request.fingerprint:
            raise DomainValidationError(
                "idempotency_key was already used for a different request"
            )
        return replace(existing.result, idempotent_replay=True)

    if request.dry_run:
        result = PublishResult(
            request_id=request.request_id,
            publisher=publisher.publisher_name,
            success=True,
            dry_run=True,
            outcomes=tuple(
                PublishTargetResult(
                    platform=target.platform,
                    account_ref=target.account_ref,
                    success=True,
                    metadata={
                        "validation_only": True,
                        "network_called": False,
                    },
                )
                for target in request.targets
            ),
            metadata={
                "network_called": False,
                "publication_performed": False,
            },
        )
    else:
        result = publisher.publish(request)
        if not isinstance(result, PublishResult):
            raise DomainValidationError(
                "Publisher must return a PublishResult"
            )
        if result.request_id != request.request_id:
            raise DomainValidationError(
                "Publisher result request_id does not match request"
            )
        if result.dry_run:
            raise DomainValidationError(
                "live PublishRequest cannot return a dry-run result"
            )

    record = PublicationRecord(
        record_id=record_id,
        idempotency_key=request.idempotency_key,
        request_fingerprint=request.fingerprint,
        request=request,
        result=result,
        recorded_at=recorded_at,
        metadata={
            "review_decision_id": decision.decision_id,
            "reviewer_id": decision.reviewer_id,
        },
    )
    ledger.append(record)
    return result
