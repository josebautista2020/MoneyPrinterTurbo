"""Local append-only audit storage for Human Review UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewDecisionStore,
)


class JsonlReviewDecisionStore(ReviewDecisionStore):
    """Append-only JSONL decision store scoped by package ID."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)

    def list(self, package_id: str) -> ReviewAuditTrail:
        package_id = self._validate_package_id(package_id)
        path = self._path(package_id)
        if not path.exists():
            return ReviewAuditTrail(package_id=package_id, decisions=())

        decisions = []
        for line_number, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
                decision = ReviewDecision.from_dict(payload)
            except (json.JSONDecodeError, DomainValidationError) as exc:
                raise DomainValidationError(
                    f"invalid audit record at {path}:{line_number}: {exc}"
                ) from exc
            if decision.package_id != package_id:
                raise DomainValidationError(
                    f"audit record package mismatch at {path}:{line_number}"
                )
            decisions.append(decision)
        return ReviewAuditTrail(
            package_id=package_id,
            decisions=tuple(decisions),
            metadata={"storage": "jsonl", "path": str(path)},
        )

    def append(self, decision: ReviewDecision) -> ReviewAuditTrail:
        trail = self.list(decision.package_id)
        if any(
            item.decision_id == decision.decision_id
            for item in trail.decisions
        ):
            raise DomainValidationError(
                f"duplicate decision_id: {decision.decision_id!r}"
            )

        updated = trail.append(decision)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(decision.package_id)
        record = json.dumps(
            decision.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(record + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return updated

    def _path(self, package_id: str) -> Path:
        return self._root_dir / f"{package_id}.jsonl"

    @staticmethod
    def _validate_package_id(package_id: str) -> str:
        try:
            empty = ReviewAuditTrail(package_id=package_id, decisions=())
        except DomainValidationError as exc:
            raise DomainValidationError(
                f"invalid package_id for audit storage: {package_id!r}"
            ) from exc
        return empty.package_id
