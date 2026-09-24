"""Governed publishing gateway and idempotency tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from extensions.content_studio.domain import DomainValidationError, SCHEMA_VERSION
from extensions.content_studio.publishing import (
    PublicationAuditTrail,
    PublicationLedger,
    PublicationRecord,
    PublishGrant,
    Publisher,
    PublishingPolicy,
    PublishRequest,
    PublishResult,
    PublishTarget,
    PublishTargetResult,
    execute_publishing_gateway,
    validate_publish_authorization,
)
from extensions.content_studio.review import (
    ReviewAuditTrail,
    ReviewDecision,
    ReviewPackage,
)
from extensions.publishing_gateway import JsonlPublicationLedger

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
KIDS = REPO_ROOT / "verticals" / "kids_puppies"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def package() -> ReviewPackage:
    return ReviewPackage.from_json(
        _load(EXAMPLES / "generic_review_package.json")
    )


def review_audit() -> ReviewAuditTrail:
    return ReviewAuditTrail.from_json(
        _load(EXAMPLES / "generic_review_approval_audit.json")
    )


def policy() -> PublishingPolicy:
    return PublishingPolicy.from_json(
        _load(EXAMPLES / "generic_publishing_policy.json")
    )


def request() -> PublishRequest:
    return PublishRequest.from_json(
        _load(EXAMPLES / "generic_publish_request.json")
    )


def approval() -> ReviewDecision:
    return review_audit().latest


class _FakePublisher:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def publisher_name(self) -> str:
        return "fake-publisher"

    def publish(self, item: PublishRequest) -> PublishResult:
        self.calls += 1
        return PublishResult(
            request_id=item.request_id,
            publisher=self.publisher_name,
            success=True,
            dry_run=False,
            outcomes=tuple(
                PublishTargetResult(
                    platform=target.platform,
                    account_ref=target.account_ref,
                    success=True,
                    external_request_id="external-1",
                )
                for target in item.targets
            ),
            metadata={"publication_performed": True},
        )


def test_publisher_protocol() -> None:
    assert isinstance(_FakePublisher(), Publisher)


def test_dry_run_validates_and_audits_without_publisher_call(tmp_path) -> None:
    publisher = _FakePublisher()
    ledger = JsonlPublicationLedger(tmp_path / "publishing.jsonl")

    result = execute_publishing_gateway(
        publisher,
        ledger,
        package(),
        approval(),
        review_audit(),
        request(),
        policy(),
        record_id="record-1",
        recorded_at="2026-09-23T21:00:00+00:00",
    )

    assert result.success
    assert result.dry_run
    assert result.metadata["network_called"] is False
    assert result.metadata["publication_performed"] is False
    assert publisher.calls == 0
    stored = ledger.get(request().idempotency_key)
    assert stored is not None
    assert stored.result == result


def test_idempotent_replay_does_not_publish_or_append_again(tmp_path) -> None:
    publisher = _FakePublisher()
    ledger = JsonlPublicationLedger(tmp_path / "publishing.jsonl")
    kwargs = dict(
        publisher=publisher,
        ledger=ledger,
        package=package(),
        decision=approval(),
        review_audit=review_audit(),
        request=request(),
        policy=policy(),
        record_id="record-1",
        recorded_at="2026-09-23T21:00:00+00:00",
    )

    first = execute_publishing_gateway(**kwargs)
    second = execute_publishing_gateway(
        **{**kwargs, "record_id": "record-2"}
    )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert publisher.calls == 0
    assert len(ledger.trail().records) == 1


def test_same_idempotency_key_cannot_change_request(tmp_path) -> None:
    ledger = JsonlPublicationLedger(tmp_path / "publishing.jsonl")
    publisher = _FakePublisher()
    first = request()
    execute_publishing_gateway(
        publisher,
        ledger,
        package(),
        approval(),
        review_audit(),
        first,
        policy(),
        record_id="record-1",
        recorded_at="2026-09-23T21:00:00+00:00",
    )
    changed = replace(first, title="Different title")

    with pytest.raises(DomainValidationError, match="different request"):
        execute_publishing_gateway(
            publisher,
            ledger,
            package(),
            approval(),
            review_audit(),
            changed,
            policy(),
            record_id="record-2",
            recorded_at="2026-09-23T21:01:00+00:00",
        )


def test_stale_approval_is_rejected() -> None:
    audited = review_audit()
    later = ReviewDecision(
        decision_id="generic-regen-2",
        package_id=audited.package_id,
        reviewer_id="reviewer-1",
        action="regenerate_episode",
        decided_at="2026-09-23T21:10:00+00:00",
        comments="Regenerate after final visual inspection.",
    )
    stale = audited.append(later)

    with pytest.raises(DomainValidationError, match="latest review decision"):
        validate_publish_authorization(
            package(),
            approval(),
            stale,
            request(),
            policy(),
        )


def test_non_approval_decision_is_rejected() -> None:
    reject = ReviewDecision(
        decision_id="generic-reject-1",
        package_id=package().package_id,
        reviewer_id="reviewer-1",
        action="reject",
        decided_at="2026-09-23T20:55:00+00:00",
        comments="Rejected.",
    )
    audit = ReviewAuditTrail(
        package_id=package().package_id,
        decisions=(reject,),
    )
    rejected_request = replace(request(), decision_id=reject.decision_id)

    with pytest.raises(DomainValidationError, match="action='approve'"):
        validate_publish_authorization(
            package(),
            reject,
            audit,
            rejected_request,
            policy(),
        )


def test_unallowlisted_target_is_rejected() -> None:
    bad = replace(
        request(),
        targets=(
            PublishTarget(
                platform="youtube",
                account_ref="other-account",
                youtube_made_for_kids=False,
            ),
        ),
    )

    with pytest.raises(DomainValidationError, match="not allowlisted"):
        validate_publish_authorization(
            package(),
            approval(),
            review_audit(),
            bad,
            policy(),
        )


def test_youtube_requires_explicit_audience_declaration() -> None:
    bad = replace(
        request(),
        targets=(
            PublishTarget(
                platform="youtube",
                account_ref="demo-account",
                youtube_made_for_kids=None,
            ),
        ),
    )

    with pytest.raises(DomainValidationError, match="youtube_made_for_kids"):
        validate_publish_authorization(
            package(),
            approval(),
            review_audit(),
            bad,
            policy(),
        )


def test_synthetic_media_declaration_is_required() -> None:
    bad = replace(request(), contains_synthetic_media=False)

    with pytest.raises(DomainValidationError, match="synthetic-media"):
        validate_publish_authorization(
            package(),
            approval(),
            review_audit(),
            bad,
            policy(),
        )


def test_live_publish_is_default_denied_before_publisher_call(tmp_path) -> None:
    publisher = _FakePublisher()
    live = replace(
        request(),
        request_id="generic-live-1",
        idempotency_key="generic-live-key-1",
        dry_run=False,
    )

    with pytest.raises(DomainValidationError, match="live publishing is disabled"):
        execute_publishing_gateway(
            publisher,
            JsonlPublicationLedger(tmp_path / "publishing.jsonl"),
            package(),
            approval(),
            review_audit(),
            live,
            policy(),
            record_id="record-live-1",
            recorded_at="2026-09-23T21:00:00+00:00",
        )

    assert publisher.calls == 0


def test_live_publish_requires_both_policy_and_publisher(tmp_path) -> None:
    live_policy = replace(policy(), live_publish_enabled=True)
    live = replace(
        request(),
        request_id="generic-live-1",
        idempotency_key="generic-live-key-1",
        dry_run=False,
    )
    publisher = _FakePublisher()

    result = execute_publishing_gateway(
        publisher,
        JsonlPublicationLedger(tmp_path / "publishing.jsonl"),
        package(),
        approval(),
        review_audit(),
        live,
        live_policy,
        record_id="record-live-1",
        recorded_at="2026-09-23T21:00:00+00:00",
    )

    assert result.success
    assert not result.dry_run
    assert publisher.calls == 1


def test_publish_request_must_match_exact_approved_render() -> None:
    bad = replace(request(), video_uri="generated/other.mp4")

    with pytest.raises(DomainValidationError, match="approved render"):
        validate_publish_authorization(
            package(),
            approval(),
            review_audit(),
            bad,
            policy(),
        )


def test_jsonl_publication_ledger_is_append_only(tmp_path) -> None:
    ledger = JsonlPublicationLedger(tmp_path / "ledger.jsonl")
    assert isinstance(ledger, PublicationLedger)

    req = request()
    result = PublishResult(
        request_id=req.request_id,
        publisher="fake",
        success=True,
        dry_run=True,
        outcomes=(
            PublishTargetResult(
                platform="youtube",
                account_ref="demo-account",
                success=True,
            ),
        ),
    )
    record = PublicationRecord(
        record_id="record-1",
        idempotency_key=req.idempotency_key,
        request_fingerprint=req.fingerprint,
        request=req,
        result=result,
        recorded_at="2026-09-23T21:00:00+00:00",
    )
    trail = ledger.append(record)

    assert isinstance(trail, PublicationAuditTrail)
    assert ledger.get(req.idempotency_key) == record
    assert len(ledger.trail().records) == 1

    with pytest.raises(DomainValidationError, match="duplicate idempotency_key"):
        ledger.append(
            replace(record, record_id="record-2")
        )


@pytest.mark.parametrize(
    "contract_type",
    [
        PublishGrant,
        PublishTarget,
        PublishingPolicy,
        PublishRequest,
        PublishTargetResult,
        PublishResult,
        PublicationRecord,
        PublicationAuditTrail,
    ],
)
def test_publishing_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_publishing_core_has_no_provider_or_vertical_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "publishing.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app",
        "requests",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.publishing_gateway",
    )
    violations = []

    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(module)

    assert not violations


def test_kids_puppies_publish_example_is_dry_run_and_made_for_kids() -> None:
    kids_policy = PublishingPolicy.from_json(
        _load(KIDS / "publishing" / "policy.json")
    )
    kids_request = PublishRequest.from_json(
        _load(KIDS / "publishing" / "ep0002.publish-request.json")
    )
    kids_audit = ReviewAuditTrail.from_json(
        _load(KIDS / "review" / "ep0002.approval-audit.json")
    )

    assert kids_policy.live_publish_enabled is False
    assert kids_request.dry_run is True
    youtube = kids_request.targets[0]
    assert youtube.platform == "youtube"
    assert youtube.youtube_made_for_kids is True
    assert kids_audit.latest is not None
    assert kids_audit.latest.action == "approve"


def test_generic_publishing_examples_contain_no_vertical_defaults() -> None:
    content = (
        _load(EXAMPLES / "generic_publishing_policy.json")
        + _load(EXAMPLES / "generic_publish_request.json")
    ).lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content
