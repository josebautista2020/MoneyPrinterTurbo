"""Safe operator service over the Content Studio episode workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.orchestration import (
    WORKFLOW_STAGES,
    EpisodeOrchestrator,
    EpisodeReleaseCandidate,
    EpisodeStageExecutor,
    EpisodeWorkflowState,
    StageExecutionResult,
    WorkflowArtifact,
    apply_review_decision,
    build_release_candidate,
)
from extensions.content_studio.publishing import (
    Publisher,
    PublishingPolicy,
    PublishRequest,
    PublishResult,
    execute_publishing_gateway,
)
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewPackage,
)
from extensions.human_review_ui.store import JsonlReviewDecisionStore
from extensions.orchestration import JsonWorkflowCheckpointStore
from extensions.publishing_gateway import JsonlPublicationLedger


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    workflow_id: str
    project_id: str
    episode_id: str
    revision: int
    next_stage: str | None
    complete: bool
    spent_cost_usd: float
    max_cost_usd: float | None
    active_artifact_count: int
    stage_rows: tuple[Mapping[str, Any], ...]


class StaticStageExecutor(EpisodeStageExecutor):
    """One-shot executor for an already produced canonical stage result."""

    def __init__(self, result: StageExecutionResult) -> None:
        self._result = result
        self.calls = 0
        self.execution_keys: list[str] = []

    @property
    def stage_name(self) -> str:
        return self._result.stage

    def estimate_cost_usd(
        self,
        state: EpisodeWorkflowState,
    ) -> float | None:
        del state
        return self._result.cost_usd

    def execute(
        self,
        state: EpisodeWorkflowState,
        execution_key: str,
    ) -> StageExecutionResult:
        del state
        self.calls += 1
        self.execution_keys.append(execution_key)
        return self._result


class DryRunPublisher(Publisher):
    """Publisher identity used only by the gateway dry-run branch."""

    @property
    def publisher_name(self) -> str:
        return "operator-console-dry-run"

    def publish(self, request: PublishRequest) -> PublishResult:
        del request
        raise RuntimeError(
            "DryRunPublisher cannot execute live publication"
        )


class OperatorConsoleService:
    """Governed workflow operations shared by Streamlit and CLI surfaces."""

    def __init__(
        self,
        *,
        workflow_dir: str | Path,
        review_audit_dir: str | Path,
        publication_audit_dir: str | Path,
    ) -> None:
        self.workflow_store = JsonWorkflowCheckpointStore(workflow_dir)
        self.review_store = JsonlReviewDecisionStore(review_audit_dir)
        self.publication_audit_dir = Path(publication_audit_dir)

    def list_workflow_ids(self) -> tuple[str, ...]:
        return self.workflow_store.list_workflow_ids()

    def create_workflow(
        self,
        *,
        workflow_id: str,
        project_id: str,
        episode_id: str,
        max_cost_usd: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> EpisodeWorkflowState:
        if self.workflow_store.load(workflow_id) is not None:
            raise DomainValidationError(
                f"workflow already exists: {workflow_id!r}"
            )
        state = EpisodeWorkflowState(
            workflow_id=workflow_id,
            project_id=project_id,
            episode_id=episode_id,
            max_cost_usd=max_cost_usd,
            metadata={
                **dict(metadata or {}),
                "created_by": "operator-console",
                "live_publication_enabled": False,
            },
        )
        self.workflow_store.save(state)
        return state

    def load_workflow(self, workflow_id: str) -> EpisodeWorkflowState:
        state = self.workflow_store.load(workflow_id)
        if state is None:
            raise DomainValidationError(
                f"workflow does not exist: {workflow_id!r}"
            )
        return state

    def summarize(self, workflow_id: str) -> WorkflowSummary:
        state = self.load_workflow(workflow_id)
        rows = []
        for stage in WORKFLOW_STAGES:
            record = state.latest_record(stage)
            rows.append(
                {
                    "stage": stage,
                    "status": state.stage_status(stage),
                    "attempt": record.attempt if record else None,
                    "revision": record.revision if record else None,
                    "cost_usd": record.cost_usd if record else 0.0,
                    "execution_key": (
                        record.execution_key if record else None
                    ),
                    "artifact_count": (
                        len(record.artifacts) if record else 0
                    ),
                    "error": record.error if record else None,
                }
            )
        return WorkflowSummary(
            workflow_id=state.workflow_id,
            project_id=state.project_id,
            episode_id=state.episode_id,
            revision=state.revision,
            next_stage=state.next_stage,
            complete=state.complete,
            spent_cost_usd=state.spent_cost_usd,
            max_cost_usd=state.max_cost_usd,
            active_artifact_count=sum(
                len(record.artifacts)
                for record in state.active_records()
                if record.status == "PASS"
            ),
            stage_rows=tuple(rows),
        )

    def apply_stage_result(
        self,
        workflow_id: str,
        result: StageExecutionResult,
    ) -> EpisodeWorkflowState:
        state = self.load_workflow(workflow_id)
        if state.next_stage is None:
            raise DomainValidationError("workflow is already complete")
        if result.stage != state.next_stage:
            raise DomainValidationError(
                f"stage result {result.stage!r} does not match "
                f"next stage {state.next_stage!r}"
            )
        if result.stage in {"human_review", "publish_dry_run"}:
            raise DomainValidationError(
                f"{result.stage} must use its governed operator action"
            )
        executor = StaticStageExecutor(result)
        orchestrator = EpisodeOrchestrator(
            {result.stage: executor},
            self.workflow_store,
        )
        return orchestrator.run_next(state)

    def record_review_decision(
        self,
        workflow_id: str,
        *,
        reviewer_id: str,
        action: str,
        comments: str,
        target_shot_id: str | None = None,
        decision_id: str | None = None,
        decided_at: str | None = None,
    ) -> EpisodeWorkflowState:
        state = self.load_workflow(workflow_id)
        if state.next_stage != "human_review":
            raise DomainValidationError(
                "workflow is not waiting for human_review"
            )
        package = state.require_one("ReviewPackage")
        if not isinstance(package, ReviewPackage):
            raise DomainValidationError(
                "active ReviewPackage artifact is invalid"
            )
        timestamp = decided_at or datetime.now(timezone.utc).isoformat()
        decision = ReviewDecision(
            decision_id=decision_id or f"decision-{uuid4().hex}",
            package_id=package.package_id,
            reviewer_id=reviewer_id,
            action=action,
            decided_at=timestamp,
            comments=comments,
            target_shot_id=target_shot_id,
            metadata={
                "source": "operator-console",
                "workflow_id": state.workflow_id,
                "publication_performed": False,
            },
        )
        audit = self.review_store.append(decision)
        updated = apply_review_decision(
            state,
            decision,
            audit,
            decided_at=timestamp,
        )
        self.workflow_store.save(updated)
        return updated

    def prepare_publish_dry_run(
        self,
        workflow_id: str,
        *,
        request: PublishRequest,
        policy: PublishingPolicy,
        recorded_at: str | None = None,
    ) -> EpisodeWorkflowState:
        state = self.load_workflow(workflow_id)
        if state.next_stage != "publish_dry_run":
            raise DomainValidationError(
                "workflow is not ready for publish_dry_run"
            )
        if not request.dry_run:
            raise DomainValidationError(
                "Operator Console only accepts PublishRequest(dry_run=True)"
            )
        if policy.live_publish_enabled:
            raise DomainValidationError(
                "Operator Console requires live_publish_enabled=False"
            )

        package = state.require_one("ReviewPackage")
        decision = state.require_one("ReviewDecision")
        review_audit = state.require_one("ReviewAuditTrail")
        if not isinstance(package, ReviewPackage):
            raise DomainValidationError("ReviewPackage artifact is invalid")
        if not isinstance(decision, ReviewDecision):
            raise DomainValidationError("ReviewDecision artifact is invalid")
        if not isinstance(review_audit, ReviewAuditTrail):
            raise DomainValidationError("ReviewAuditTrail artifact is invalid")

        ledger = self._publication_ledger(workflow_id)
        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        result = execute_publishing_gateway(
            DryRunPublisher(),
            ledger,
            package,
            decision,
            review_audit,
            request,
            policy,
            record_id=f"{request.request_id}-record",
            recorded_at=timestamp,
        )
        audit = ledger.trail()
        stage_result = StageExecutionResult(
            stage="publish_dry_run",
            status="PASS",
            artifacts=(
                WorkflowArtifact.from_contract(
                    f"{request.request_id}-result",
                    result,
                ),
                WorkflowArtifact.from_contract(
                    f"{request.request_id}-audit",
                    audit,
                ),
            ),
            cost_usd=0.0,
            metadata={
                "operator_console": True,
                "network_called": False,
                "publication_performed": False,
            },
        )
        executor = StaticStageExecutor(stage_result)
        orchestrator = EpisodeOrchestrator(
            {"publish_dry_run": executor},
            self.workflow_store,
        )
        return orchestrator.run_next(state)

    def build_release_candidate(
        self,
        workflow_id: str,
    ) -> EpisodeReleaseCandidate:
        return build_release_candidate(self.load_workflow(workflow_id))

    def active_artifacts(
        self,
        workflow_id: str,
    ) -> tuple[WorkflowArtifact, ...]:
        state = self.load_workflow(workflow_id)
        return tuple(
            artifact
            for record in state.active_records()
            if record.status == "PASS"
            for artifact in record.artifacts
        )

    def _publication_ledger(
        self,
        workflow_id: str,
    ) -> JsonlPublicationLedger:
        return JsonlPublicationLedger(
            self.publication_audit_dir / f"{workflow_id}.jsonl"
        )
