"""End-to-end episode workflow orchestration and release-candidate contracts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.consistency import ConsistencyReport
from extensions.content_studio.domain import (
    DomainValidationError,
    EpisodeSpec,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.media import MediaAssemblyResult
from extensions.content_studio.prompting import PromptPlan
from extensions.content_studio.publishing import (
    PublicationAuditTrail,
    PublishResult,
)
from extensions.content_studio.quality import HumanReviewGate, RenderQAReport
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewPackage,
    validate_review_decision,
)
from extensions.content_studio.safety import SafetyAssessment
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.storyboard import StoryboardPlan
from extensions.content_studio.visual_generation import (
    VisualGenerationPlan,
    VisualGenerationReport,
)

WORKFLOW_STAGES = (
    "project_episode",
    "bibles",
    "story",
    "storyboard",
    "prompts",
    "visuals",
    "consistency",
    "media",
    "safety_qa",
    "review_package",
    "human_review",
    "publish_dry_run",
)

TERMINAL_STAGE_STATUSES = {"PASS", "FAIL", "BLOCKED"}
ALL_STAGE_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "BLOCKED",
    "PASS",
    "FAIL",
    "WAIVED_BY_ADR",
}

_CONTRACT_TYPES: dict[str, type[JsonContract]] = {
    cls.__name__: cls
    for cls in (
        ProjectSpec,
        EpisodeSpec,
        CharacterBible,
        UniverseBible,
        StoryPlan,
        StoryboardPlan,
        PromptPlan,
        VisualGenerationPlan,
        VisualGenerationReport,
        ConsistencyReport,
        MediaAssemblyResult,
        SafetyAssessment,
        RenderQAReport,
        HumanReviewGate,
        ReviewPackage,
        ReviewDecision,
        ReviewAuditTrail,
        PublishResult,
        PublicationAuditTrail,
    )
}

_STAGE_REQUIREMENTS: dict[str, dict[str, int]] = {
    "project_episode": {"ProjectSpec": 1, "EpisodeSpec": 1},
    "bibles": {"CharacterBible": 1, "UniverseBible": 1},
    "story": {"StoryPlan": 1},
    "storyboard": {"StoryboardPlan": 1},
    "prompts": {"PromptPlan": 1},
    "visuals": {
        "VisualGenerationPlan": 1,
        "VisualGenerationReport": 1,
    },
    "consistency": {"ConsistencyReport": 1},
    "media": {"MediaAssemblyResult": 1},
    "safety_qa": {
        "SafetyAssessment": 1,
        "RenderQAReport": 1,
        "HumanReviewGate": 1,
    },
    "review_package": {"ReviewPackage": 1},
    "human_review": {
        "ReviewDecision": 1,
        "ReviewAuditTrail": 1,
    },
    "publish_dry_run": {
        "PublishResult": 1,
        "PublicationAuditTrail": 1,
    },
}


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a non-empty string")
    value = value.strip()
    if len(value) > 128:
        raise DomainValidationError(f"{name} must be <= 128 characters")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789._-"
    )
    if value[0] not in allowed or any(ch not in allowed for ch in value):
        raise DomainValidationError(f"{name} contains unsupported characters")
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


def _non_negative_cost(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise DomainValidationError(
            f"{name} must be a non-negative finite number or null"
        )
    return float(value)


def _stage_index(stage: str) -> int:
    try:
        return WORKFLOW_STAGES.index(stage)
    except ValueError as exc:
        raise DomainValidationError(
            f"unsupported workflow stage: {stage!r}"
        ) from exc


@dataclass(frozen=True, slots=True)
class WorkflowArtifact(JsonContract):
    artifact_id: str
    artifact_type: str
    payload: Mapping[str, Any]
    uri: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _id(self.artifact_id, "artifact_id"),
        )
        artifact_type = _text(self.artifact_type, "artifact_type")
        if artifact_type not in _CONTRACT_TYPES:
            raise DomainValidationError(
                f"unsupported artifact_type: {artifact_type!r}"
            )
        object.__setattr__(self, "artifact_type", artifact_type)
        if not isinstance(self.payload, Mapping):
            raise DomainValidationError("payload must be a mapping")
        normalized = _metadata(self.payload)
        contract_type = _CONTRACT_TYPES[artifact_type]
        contract_type.from_dict(normalized)
        object.__setattr__(self, "payload", normalized)
        object.__setattr__(
            self,
            "uri",
            _optional_text(self.uri, "uri"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_contract(
        cls,
        artifact_id: str,
        contract: JsonContract,
        *,
        uri: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "WorkflowArtifact":
        artifact_type = type(contract).__name__
        if artifact_type not in _CONTRACT_TYPES:
            raise DomainValidationError(
                f"unsupported workflow contract type: {artifact_type!r}"
            )
        return cls(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            payload=contract.to_dict(),
            uri=uri,
            metadata=metadata or {},
        )

    def to_contract(self) -> JsonContract:
        return _CONTRACT_TYPES[self.artifact_type].from_dict(self.payload)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "artifact_id",
                "artifact_type",
                "payload",
                "uri",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class StageExecutionResult(JsonContract):
    stage: str
    status: str
    artifacts: tuple[WorkflowArtifact, ...] = ()
    cost_usd: float | None = 0.0
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _stage_index(self.stage)
        if self.status not in TERMINAL_STAGE_STATUSES:
            raise DomainValidationError(
                "StageExecutionResult.status must be PASS, FAIL, or BLOCKED"
            )
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, WorkflowArtifact) for item in artifacts):
            raise DomainValidationError(
                "artifacts must contain WorkflowArtifact values"
            )
        ids = [item.artifact_id for item in artifacts]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(
                "artifact_id values must be unique in stage result"
            )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "cost_usd",
            _non_negative_cost(self.cost_usd, "cost_usd"),
        )
        object.__setattr__(self, "error", _optional_text(self.error, "error"))
        if self.status == "PASS" and self.error is not None:
            raise DomainValidationError(
                "PASS stage result must not contain error"
            )
        if self.status in {"FAIL", "BLOCKED"} and self.error is None:
            raise DomainValidationError(
                "FAIL/BLOCKED stage result requires error"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["artifacts"] = [item.to_dict() for item in self.artifacts]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "stage",
                "status",
                "artifacts",
                "cost_usd",
                "error",
                "metadata",
            },
        )
        data["artifacts"] = tuple(
            WorkflowArtifact.from_dict(item)
            for item in data.get("artifacts", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class WorkflowStageRecord(JsonContract):
    record_id: str
    stage: str
    status: str
    attempt: int
    execution_key: str
    revision: int
    started_at: str
    finished_at: str | None = None
    artifacts: tuple[WorkflowArtifact, ...] = ()
    cost_usd: float | None = 0.0
    error: str | None = None
    superseded: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _id(self.record_id, "record_id"),
        )
        _stage_index(self.stage)
        if self.status not in ALL_STAGE_STATUSES:
            raise DomainValidationError(
                f"unsupported stage status: {self.status!r}"
            )
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt <= 0
        ):
            raise DomainValidationError("attempt must be a positive integer")
        object.__setattr__(
            self,
            "execution_key",
            _id(self.execution_key, "execution_key"),
        )
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise DomainValidationError("revision must be a positive integer")
        object.__setattr__(
            self,
            "started_at",
            _timestamp(self.started_at, "started_at"),
        )
        if self.finished_at is not None:
            object.__setattr__(
                self,
                "finished_at",
                _timestamp(self.finished_at, "finished_at"),
            )
        if self.status == "IN_PROGRESS" and self.finished_at is not None:
            raise DomainValidationError(
                "IN_PROGRESS record must not have finished_at"
            )
        if self.status in TERMINAL_STAGE_STATUSES and self.finished_at is None:
            raise DomainValidationError(
                "terminal stage record requires finished_at"
            )
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, WorkflowArtifact) for item in artifacts):
            raise DomainValidationError(
                "artifacts must contain WorkflowArtifact values"
            )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "cost_usd",
            _non_negative_cost(self.cost_usd, "cost_usd"),
        )
        object.__setattr__(self, "error", _optional_text(self.error, "error"))
        if not isinstance(self.superseded, bool):
            raise DomainValidationError("superseded must be boolean")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["artifacts"] = [item.to_dict() for item in self.artifacts]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "record_id",
                "stage",
                "status",
                "attempt",
                "execution_key",
                "revision",
                "started_at",
                "finished_at",
                "artifacts",
                "cost_usd",
                "error",
                "superseded",
                "metadata",
            },
        )
        data["artifacts"] = tuple(
            WorkflowArtifact.from_dict(item)
            for item in data.get("artifacts", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class EpisodeWorkflowState(JsonContract):
    workflow_id: str
    project_id: str
    episode_id: str
    revision: int = 1
    records: tuple[WorkflowStageRecord, ...] = ()
    max_cost_usd: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("workflow_id", "project_id", "episode_id"):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise DomainValidationError("revision must be a positive integer")
        records = tuple(self.records)
        if not all(isinstance(item, WorkflowStageRecord) for item in records):
            raise DomainValidationError(
                "records must contain WorkflowStageRecord values"
            )
        ids = [item.record_id for item in records]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("record_id values must be unique")
        object.__setattr__(self, "records", records)
        object.__setattr__(
            self,
            "max_cost_usd",
            _non_negative_cost(self.max_cost_usd, "max_cost_usd"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def active_records(self) -> tuple[WorkflowStageRecord, ...]:
        return tuple(item for item in self.records if not item.superseded)

    def latest_record(self, stage: str) -> WorkflowStageRecord | None:
        _stage_index(stage)
        candidates = [
            item
            for item in self.records
            if item.stage == stage and not item.superseded
        ]
        return candidates[-1] if candidates else None

    def stage_status(self, stage: str) -> str:
        record = self.latest_record(stage)
        return record.status if record is not None else "PENDING"

    @property
    def spent_cost_usd(self) -> float:
        return sum(
            item.cost_usd or 0.0
            for item in self.records
            if item.status in TERMINAL_STAGE_STATUSES
        )

    @property
    def complete(self) -> bool:
        return all(self.stage_status(stage) == "PASS" for stage in WORKFLOW_STAGES)

    @property
    def next_stage(self) -> str | None:
        for stage in WORKFLOW_STAGES:
            if self.stage_status(stage) != "PASS":
                return stage
        return None

    def artifacts(self, artifact_type: str) -> tuple[WorkflowArtifact, ...]:
        return tuple(
            artifact
            for record in self.active_records()
            if record.status == "PASS"
            for artifact in record.artifacts
            if artifact.artifact_type == artifact_type
        )

    def require_one(self, artifact_type: str) -> JsonContract:
        matches = self.artifacts(artifact_type)
        if len(matches) != 1:
            raise DomainValidationError(
                f"expected exactly one active {artifact_type}; "
                f"found {len(matches)}"
            )
        return matches[0].to_contract()

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["records"] = [item.to_dict() for item in self.records]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "workflow_id",
                "project_id",
                "episode_id",
                "revision",
                "records",
                "max_cost_usd",
                "metadata",
            },
        )
        data["records"] = tuple(
            WorkflowStageRecord.from_dict(item)
            for item in data.get("records", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class EpisodeStageExecutor(Protocol):
    @property
    def stage_name(self) -> str:
        ...

    def estimate_cost_usd(
        self,
        state: EpisodeWorkflowState,
    ) -> float | None:
        ...

    def execute(
        self,
        state: EpisodeWorkflowState,
        execution_key: str,
    ) -> StageExecutionResult:
        ...


@runtime_checkable
class WorkflowCheckpointStore(Protocol):
    def load(self, workflow_id: str) -> EpisodeWorkflowState | None:
        ...

    def save(self, state: EpisodeWorkflowState) -> None:
        ...


@dataclass(frozen=True, slots=True)
class EpisodeReleaseCandidate(JsonContract):
    workflow_id: str
    revision: int
    project_id: str
    episode_id: str
    render_uri: str
    review_decision_id: str
    publish_request_id: str
    publication_record_id: str
    total_cost_usd: float
    publication_status: str = "dry_run_validated"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "workflow_id",
            "project_id",
            "episode_id",
            "review_decision_id",
            "publish_request_id",
            "publication_record_id",
        ):
            object.__setattr__(self, name, _id(getattr(self, name), name))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise DomainValidationError("revision must be a positive integer")
        object.__setattr__(
            self,
            "render_uri",
            _text(self.render_uri, "render_uri"),
        )
        cost = _non_negative_cost(self.total_cost_usd, "total_cost_usd")
        object.__setattr__(self, "total_cost_usd", cost or 0.0)
        if self.publication_status != "dry_run_validated":
            raise DomainValidationError(
                "release candidate publication_status must be dry_run_validated"
            )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
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
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


def _contract_identity(contract: JsonContract) -> tuple[str | None, str | None]:
    if isinstance(contract, ProjectSpec):
        return contract.project_id, None
    if isinstance(contract, EpisodeSpec):
        return contract.project_id, contract.episode_id
    if isinstance(contract, (CharacterBible, UniverseBible)):
        return contract.project_id, None
    if isinstance(contract, StoryPlan):
        return contract.brief.project_id, contract.brief.episode_id
    project_id = getattr(contract, "project_id", None)
    episode_id = getattr(contract, "episode_id", None)
    return project_id, episode_id


def validate_stage_artifacts(
    state: EpisodeWorkflowState,
    stage: str,
    artifacts: tuple[WorkflowArtifact, ...],
) -> None:
    requirements = _STAGE_REQUIREMENTS[stage]
    counts: dict[str, int] = {}
    contracts: list[JsonContract] = []

    for artifact in artifacts:
        counts[artifact.artifact_type] = counts.get(artifact.artifact_type, 0) + 1
        contract = artifact.to_contract()
        contracts.append(contract)
        project_id, episode_id = _contract_identity(contract)
        if project_id is not None and project_id != state.project_id:
            raise DomainValidationError(
                f"{artifact.artifact_type} project_id does not match workflow"
            )
        if episode_id is not None and episode_id != state.episode_id:
            raise DomainValidationError(
                f"{artifact.artifact_type} episode_id does not match workflow"
            )

    missing = [
        artifact_type
        for artifact_type, minimum in requirements.items()
        if counts.get(artifact_type, 0) < minimum
    ]
    if missing:
        raise DomainValidationError(
            f"stage {stage!r} missing required artifacts: {missing}"
        )

    if stage == "project_episode":
        project = next(
            item for item in contracts if isinstance(item, ProjectSpec)
        )
        episode = next(
            item for item in contracts if isinstance(item, EpisodeSpec)
        )
        matching = [
            item
            for item in project.episodes
            if item.episode_id == episode.episode_id
        ]
        if len(matching) != 1 or matching[0] != episode:
            raise DomainValidationError(
                "ProjectSpec must contain the exact EpisodeSpec artifact"
            )

    if stage == "consistency":
        report = next(
            item for item in contracts if isinstance(item, ConsistencyReport)
        )
        if not report.success:
            raise DomainValidationError(
                "consistency stage PASS requires successful ConsistencyReport"
            )

    if stage == "media":
        media = next(
            item for item in contracts if isinstance(item, MediaAssemblyResult)
        )
        if not media.success:
            raise DomainValidationError(
                "media stage PASS requires successful MediaAssemblyResult"
            )

    if stage == "safety_qa":
        qa = next(
            item for item in contracts if isinstance(item, RenderQAReport)
        )
        gate = next(
            item for item in contracts if isinstance(item, HumanReviewGate)
        )
        if not qa.passed or not gate.eligible_for_human_review:
            raise DomainValidationError(
                "safety_qa PASS requires passing QA and human-review eligibility"
            )

    if stage == "human_review":
        decision = next(
            item for item in contracts if isinstance(item, ReviewDecision)
        )
        audit = next(
            item for item in contracts if isinstance(item, ReviewAuditTrail)
        )
        package = state.require_one("ReviewPackage")
        if not isinstance(package, ReviewPackage):
            raise DomainValidationError("ReviewPackage artifact is invalid")
        validate_review_decision(package, decision)
        if decision.action != "approve":
            raise DomainValidationError(
                "human_review PASS requires ReviewDecision(action='approve')"
            )
        if audit.latest is None or audit.latest.decision_id != decision.decision_id:
            raise DomainValidationError(
                "human_review PASS requires approval to be latest audit decision"
            )

    if stage == "publish_dry_run":
        result = next(
            item for item in contracts if isinstance(item, PublishResult)
        )
        audit = next(
            item for item in contracts
            if isinstance(item, PublicationAuditTrail)
        )
        if not result.success or not result.dry_run:
            raise DomainValidationError(
                "publish_dry_run PASS requires successful dry-run PublishResult"
            )
        if result.metadata.get("publication_performed") is True:
            raise DomainValidationError(
                "publish_dry_run must not perform publication"
            )
        if not audit.records:
            raise DomainValidationError(
                "publish_dry_run requires PublicationAuditTrail record"
            )
        latest = audit.records[-1]
        if not latest.request.dry_run or not latest.result.dry_run:
            raise DomainValidationError(
                "publication audit must contain dry-run request/result"
            )
        if latest.result.request_id != result.request_id:
            raise DomainValidationError(
                "PublishResult does not match latest publication audit record"
            )


def _active_input_fingerprint(
    state: EpisodeWorkflowState,
    stage: str,
) -> str:
    index = _stage_index(stage)
    payload = [
        artifact.to_dict()
        for record in state.active_records()
        if record.status == "PASS"
        and _stage_index(record.stage) < index
        for artifact in record.artifacts
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _next_attempt(state: EpisodeWorkflowState, stage: str) -> int:
    attempts = [
        item.attempt
        for item in state.records
        if item.stage == stage
    ]
    return max(attempts, default=0) + 1


def _replace_record(
    state: EpisodeWorkflowState,
    record: WorkflowStageRecord,
) -> EpisodeWorkflowState:
    replaced = False
    records = []
    for item in state.records:
        if item.record_id == record.record_id:
            records.append(record)
            replaced = True
        else:
            records.append(item)
    if not replaced:
        records.append(record)
    return replace(state, records=tuple(records))


class EpisodeOrchestrator:
    """Checkpointed sequential coordinator for canonical episode stages."""

    def __init__(
        self,
        executors: Mapping[str, EpisodeStageExecutor],
        checkpoint_store: WorkflowCheckpointStore,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._executors = dict(executors)
        self._store = checkpoint_store
        self._clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        for stage, executor in self._executors.items():
            _stage_index(stage)
            if executor.stage_name != stage:
                raise DomainValidationError(
                    f"executor stage mismatch for {stage!r}"
                )

    def run_next(
        self,
        state: EpisodeWorkflowState,
    ) -> EpisodeWorkflowState:
        stage = state.next_stage
        if stage is None:
            return state

        existing = state.latest_record(stage)
        if existing is not None and existing.status == "IN_PROGRESS":
            attempt = existing.attempt
            execution_key = existing.execution_key
            record_id = existing.record_id
            started_at = existing.started_at
        else:
            attempt = _next_attempt(state, stage)
            fingerprint = _active_input_fingerprint(state, stage)
            seed = (
                f"{state.workflow_id}|{state.revision}|{stage}|"
                f"{attempt}|{fingerprint}"
            ).encode("utf-8")
            digest = hashlib.sha256(seed).hexdigest()[:24]
            execution_key = f"{stage}-{digest}"
            record_id = f"{stage}-r{state.revision}-a{attempt}"
            started_at = self._clock()

        executor = self._executors.get(stage)
        if executor is None:
            blocked = WorkflowStageRecord(
                record_id=record_id,
                stage=stage,
                status="BLOCKED",
                attempt=attempt,
                execution_key=execution_key,
                revision=state.revision,
                started_at=started_at,
                finished_at=self._clock(),
                cost_usd=0.0,
                error=f"no executor configured for stage {stage}",
            )
            updated = _replace_record(state, blocked)
            self._store.save(updated)
            return updated

        estimate = executor.estimate_cost_usd(state)
        estimate = _non_negative_cost(estimate, "estimated_cost_usd")
        if state.max_cost_usd is not None:
            if estimate is None:
                blocked = WorkflowStageRecord(
                    record_id=record_id,
                    stage=stage,
                    status="BLOCKED",
                    attempt=attempt,
                    execution_key=execution_key,
                    revision=state.revision,
                    started_at=started_at,
                    finished_at=self._clock(),
                    cost_usd=0.0,
                    error=(
                        "cost estimate required before executing "
                        f"budget-controlled stage {stage}"
                    ),
                )
                updated = _replace_record(state, blocked)
                self._store.save(updated)
                return updated
            if state.spent_cost_usd + estimate > state.max_cost_usd:
                blocked = WorkflowStageRecord(
                    record_id=record_id,
                    stage=stage,
                    status="BLOCKED",
                    attempt=attempt,
                    execution_key=execution_key,
                    revision=state.revision,
                    started_at=started_at,
                    finished_at=self._clock(),
                    cost_usd=0.0,
                    error=(
                        "estimated stage cost would exceed workflow budget"
                    ),
                    metadata={"estimated_cost_usd": estimate},
                )
                updated = _replace_record(state, blocked)
                self._store.save(updated)
                return updated

        in_progress = WorkflowStageRecord(
            record_id=record_id,
            stage=stage,
            status="IN_PROGRESS",
            attempt=attempt,
            execution_key=execution_key,
            revision=state.revision,
            started_at=started_at,
            artifacts=(),
            cost_usd=0.0,
            metadata={
                "input_fingerprint": _active_input_fingerprint(state, stage),
                "estimated_cost_usd": estimate,
            },
        )
        working = _replace_record(state, in_progress)
        self._store.save(working)

        try:
            result = executor.execute(working, execution_key)
            if not isinstance(result, StageExecutionResult):
                raise DomainValidationError(
                    "stage executor must return StageExecutionResult"
                )
            if result.stage != stage:
                raise DomainValidationError(
                    "stage executor returned result for different stage"
                )
            if result.status == "PASS":
                validate_stage_artifacts(
                    working,
                    stage,
                    result.artifacts,
                )
        except Exception as exc:
            result = StageExecutionResult(
                stage=stage,
                status="FAIL",
                artifacts=(),
                cost_usd=0.0,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"executor_exception": True},
            )

        actual_cost = result.cost_usd or 0.0
        final_status = result.status
        error = result.error
        if (
            state.max_cost_usd is not None
            and state.spent_cost_usd + actual_cost > state.max_cost_usd
        ):
            final_status = "FAIL"
            error = "actual stage cost exceeded workflow budget"

        terminal = WorkflowStageRecord(
            record_id=record_id,
            stage=stage,
            status=final_status,
            attempt=attempt,
            execution_key=execution_key,
            revision=state.revision,
            started_at=started_at,
            finished_at=self._clock(),
            artifacts=result.artifacts,
            cost_usd=actual_cost,
            error=error,
            metadata={
                **result.metadata,
                "estimated_cost_usd": estimate,
            },
        )
        updated = _replace_record(working, terminal)
        self._store.save(updated)
        return updated

    def run_until_blocked(
        self,
        state: EpisodeWorkflowState,
        *,
        stop_after: str | None = None,
    ) -> EpisodeWorkflowState:
        if stop_after is not None:
            _stage_index(stop_after)
        current = state
        while True:
            if current.complete:
                return current
            stage = current.next_stage
            if stage is None:
                return current
            current = self.run_next(current)
            record = current.latest_record(stage)
            if record is None:
                raise DomainValidationError(
                    "orchestrator did not produce a stage record"
                )
            if record.status in {"FAIL", "BLOCKED"}:
                return current
            if stop_after == stage:
                return current


def apply_review_decision(
    state: EpisodeWorkflowState,
    decision: ReviewDecision,
    audit: ReviewAuditTrail,
    *,
    decided_at: str,
) -> EpisodeWorkflowState:
    """Apply approval/rejection or rewind the workflow for regeneration."""
    decided_at = _timestamp(decided_at, "decided_at")
    package_contract = state.require_one("ReviewPackage")
    if not isinstance(package_contract, ReviewPackage):
        raise DomainValidationError("ReviewPackage artifact is invalid")
    validate_review_decision(package_contract, decision)
    if audit.package_id != package_contract.package_id:
        raise DomainValidationError(
            "review audit package_id does not match ReviewPackage"
        )
    if audit.latest is None or audit.latest.decision_id != decision.decision_id:
        raise DomainValidationError(
            "ReviewDecision must be the latest audit decision"
        )

    decision_artifact = WorkflowArtifact.from_contract(
        f"{decision.decision_id}-artifact",
        decision,
    )
    audit_artifact = WorkflowArtifact.from_contract(
        f"{decision.decision_id}-audit",
        audit,
    )

    if decision.action in {"approve", "reject"}:
        status = "PASS" if decision.action == "approve" else "FAIL"
        current = state.latest_record("human_review")
        attempt = (
            current.attempt
            if current is not None and current.status == "IN_PROGRESS"
            else _next_attempt(state, "human_review")
        )
        record = WorkflowStageRecord(
            record_id=f"human-review-{decision.decision_id}",
            stage="human_review",
            status=status,
            attempt=attempt,
            execution_key=f"human-review-{decision.decision_id}",
            revision=state.revision,
            started_at=decision.decided_at,
            finished_at=decided_at,
            artifacts=(decision_artifact, audit_artifact),
            cost_usd=0.0,
            error=(
                None
                if status == "PASS"
                else "episode rejected by human reviewer"
            ),
            metadata={
                "reviewer_id": decision.reviewer_id,
                "human_decision": decision.action,
            },
        )
        if status == "PASS":
            validate_stage_artifacts(
                state,
                "human_review",
                record.artifacts,
            )
        updated = replace(state, records=(*state.records, record))
        return updated

    reset_stage = (
        "visuals"
        if decision.action == "regenerate_shot"
        else "story"
    )
    reset_index = _stage_index(reset_stage)
    records = []
    for record in state.records:
        if (
            not record.superseded
            and _stage_index(record.stage) >= reset_index
        ):
            records.append(replace(record, superseded=True))
        else:
            records.append(record)

    review_event = WorkflowStageRecord(
        record_id=f"review-event-{decision.decision_id}",
        stage="human_review",
        status="BLOCKED",
        attempt=_next_attempt(state, "human_review"),
        execution_key=f"review-event-{decision.decision_id}",
        revision=state.revision,
        started_at=decision.decided_at,
        finished_at=decided_at,
        artifacts=(decision_artifact, audit_artifact),
        cost_usd=0.0,
        error=(
            f"human requested {decision.action}; workflow rewound "
            f"to {reset_stage}"
        ),
        superseded=True,
        metadata={
            "reviewer_id": decision.reviewer_id,
            "regeneration_target_shot_id": decision.target_shot_id,
            "rewind_to_stage": reset_stage,
        },
    )
    records.append(review_event)
    return replace(
        state,
        revision=state.revision + 1,
        records=tuple(records),
        metadata={
            **state.metadata,
            "last_regeneration_decision_id": decision.decision_id,
            "rewind_to_stage": reset_stage,
            "regeneration_target_shot_id": decision.target_shot_id,
        },
    )


def build_release_candidate(
    state: EpisodeWorkflowState,
) -> EpisodeReleaseCandidate:
    if not state.complete:
        raise DomainValidationError(
            "workflow must complete all stages before release candidate"
        )
    package = state.require_one("ReviewPackage")
    decision = state.require_one("ReviewDecision")
    publish_result = state.require_one("PublishResult")
    publication_audit = state.require_one("PublicationAuditTrail")

    if not isinstance(package, ReviewPackage):
        raise DomainValidationError("ReviewPackage artifact is invalid")
    if not isinstance(decision, ReviewDecision) or not decision.approved:
        raise DomainValidationError(
            "release candidate requires approved ReviewDecision"
        )
    if (
        not isinstance(publish_result, PublishResult)
        or not publish_result.success
        or not publish_result.dry_run
    ):
        raise DomainValidationError(
            "release candidate requires successful dry-run PublishResult"
        )
    if not isinstance(publication_audit, PublicationAuditTrail):
        raise DomainValidationError(
            "PublicationAuditTrail artifact is invalid"
        )
    if not publication_audit.records:
        raise DomainValidationError(
            "release candidate requires publication audit record"
        )
    latest = publication_audit.records[-1]
    if not latest.request.dry_run or latest.result.request_id != publish_result.request_id:
        raise DomainValidationError(
            "release candidate publication audit does not match dry-run result"
        )

    return EpisodeReleaseCandidate(
        workflow_id=state.workflow_id,
        revision=state.revision,
        project_id=state.project_id,
        episode_id=state.episode_id,
        render_uri=package.render_uri,
        review_decision_id=decision.decision_id,
        publish_request_id=publish_result.request_id,
        publication_record_id=latest.record_id,
        total_cost_usd=state.spent_cost_usd,
        metadata={
            "publication_performed": False,
            "release_candidate": True,
        },
    )
