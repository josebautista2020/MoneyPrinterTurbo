"""Atomic local checkpoint storage for EpisodeWorkflowState."""

from __future__ import annotations

import os
from pathlib import Path

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.orchestration import (
    EpisodeWorkflowState,
    WorkflowCheckpointStore,
)


class JsonWorkflowCheckpointStore(WorkflowCheckpointStore):
    """One validated JSON checkpoint per workflow ID."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)

    def load(self, workflow_id: str) -> EpisodeWorkflowState | None:
        path = self._path(workflow_id)
        if not path.exists():
            return None
        try:
            state = EpisodeWorkflowState.from_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, DomainValidationError) as exc:
            raise DomainValidationError(
                f"invalid workflow checkpoint {path}: {exc}"
            ) from exc
        if state.workflow_id != workflow_id:
            raise DomainValidationError(
                "checkpoint workflow_id does not match requested workflow"
            )
        return state

    def save(self, state: EpisodeWorkflowState) -> None:
        if not isinstance(state, EpisodeWorkflowState):
            raise DomainValidationError(
                "checkpoint store requires EpisodeWorkflowState"
            )
        self._root_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(state.workflow_id)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(state.to_json())
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            finally:
                raise

    def _path(self, workflow_id: str) -> Path:
        probe = EpisodeWorkflowState(
            workflow_id=workflow_id,
            project_id="checkpoint-probe",
            episode_id="checkpoint-probe",
        )
        return self._root_dir / f"{probe.workflow_id}.json"
