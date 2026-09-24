"""Local append-only publication audit ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.publishing import (
    PublicationAuditTrail,
    PublicationLedger,
    PublicationRecord,
)


class JsonlPublicationLedger(PublicationLedger):
    """Append-only JSONL ledger for governed publication attempts."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def get(self, idempotency_key: str) -> PublicationRecord | None:
        for record in self._load_records():
            if record.idempotency_key == idempotency_key:
                return record
        return None

    def append(self, record: PublicationRecord) -> PublicationAuditTrail:
        records = self._load_records()
        if any(
            item.idempotency_key == record.idempotency_key
            for item in records
        ):
            raise DomainValidationError(
                f"duplicate idempotency_key: {record.idempotency_key!r}"
            )
        if any(item.record_id == record.record_id for item in records):
            raise DomainValidationError(
                f"duplicate record_id: {record.record_id!r}"
            )

        trail = PublicationAuditTrail(records=(*records, record))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            record.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return trail

    def trail(self) -> PublicationAuditTrail:
        return PublicationAuditTrail(
            records=self._load_records(),
            metadata={
                "storage": "jsonl",
                "path": str(self._path),
            },
        )

    def _load_records(self) -> tuple[PublicationRecord, ...]:
        if not self._path.exists():
            return ()

        records = []
        for line_number, raw in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
                record = PublicationRecord.from_dict(payload)
            except (json.JSONDecodeError, DomainValidationError) as exc:
                raise DomainValidationError(
                    f"invalid publication audit record at "
                    f"{self._path}:{line_number}: {exc}"
                ) from exc
            records.append(record)

        return PublicationAuditTrail(records=tuple(records)).records
