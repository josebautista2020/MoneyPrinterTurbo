"""Offline tests for the guarded MoneyPrinterTurbo publishing adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.publishing import (
    PublishRequest,
    PublishTarget,
)
from extensions.mpt_adapter.publishing import MPTUploadPostPublisher

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"


def request() -> PublishRequest:
    return PublishRequest.from_json(
        (EXAMPLES / "generic_publish_request.json").read_text(
            encoding="utf-8"
        )
    )


def test_adapter_dry_run_never_calls_upload_post(monkeypatch) -> None:
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network path must not be called")

    fake = SimpleNamespace(
        is_configured=lambda: True,
        username="demo-account",
        upload_video=fail,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )

    result = MPTUploadPostPublisher().publish(request())

    assert result.success
    assert result.dry_run
    assert result.metadata["network_called"] is False
    assert not called


def test_live_publish_is_disabled_by_default(monkeypatch, tmp_path) -> None:
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True

    fake = SimpleNamespace(
        is_configured=lambda: True,
        username="demo-account",
        upload_video=fail,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    live = replace(request(), video_uri=str(video), dry_run=False)

    with pytest.raises(RuntimeError, match="explicit adapter authorization"):
        MPTUploadPostPublisher().publish(live)

    assert not called


def test_live_adapter_maps_youtube_kids_declaration(
    monkeypatch,
    tmp_path,
) -> None:
    calls = []

    def fake_upload_video(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "request_id": "upload-post-123",
        }

    fake = SimpleNamespace(
        is_configured=lambda: True,
        username="kids-demo-channel",
        upload_video=fake_upload_video,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    live = PublishRequest(
        request_id="kids-live-1",
        package_id="kids-package-1",
        decision_id="kids-approval-1",
        video_uri=str(video),
        title="Toby y Luna",
        targets=(
            PublishTarget(
                platform="youtube",
                account_ref="kids-demo-channel",
                privacy_level="PUBLIC_TO_EVERYONE",
                youtube_privacy_status="private",
                youtube_made_for_kids=True,
            ),
        ),
        idempotency_key="kids-live-key-1",
        description="A child-safe original story.",
        tags=("perritos", "niños"),
        contains_synthetic_media=True,
        dry_run=False,
    )

    result = MPTUploadPostPublisher(
        allow_live_publish=True
    ).publish(live)

    assert result.success
    assert not result.dry_run
    assert result.metadata["publication_performed"] is True
    assert result.outcomes[0].external_request_id == "upload-post-123"
    assert len(calls) == 1
    call = calls[0]
    assert call["platforms"] == ["youtube"]
    assert call["youtube_extra"]["selfDeclaredMadeForKids"] is True
    assert call["youtube_extra"]["privacyStatus"] == "private"
    assert call["youtube_extra"]["tags"] == ["perritos", "niños"]


def test_account_must_match_upload_post_username(
    monkeypatch,
    tmp_path,
) -> None:
    fake = SimpleNamespace(
        is_configured=lambda: True,
        username="configured-account",
        upload_video=lambda **kwargs: pytest.fail(
            "provider should not be called"
        ),
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    live = replace(
        request(),
        video_uri=str(video),
        dry_run=False,
    )

    with pytest.raises(DomainValidationError, match="configured"):
        MPTUploadPostPublisher(
            allow_live_publish=True
        ).publish(live)


def test_missing_video_fails_before_provider_call(
    monkeypatch,
    tmp_path,
) -> None:
    called = False

    def fake_upload(**kwargs):
        nonlocal called
        called = True

    fake = SimpleNamespace(
        is_configured=lambda: True,
        username="demo-account",
        upload_video=fake_upload,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )
    live = replace(
        request(),
        video_uri=str(tmp_path / "missing.mp4"),
        dry_run=False,
    )

    result = MPTUploadPostPublisher(
        allow_live_publish=True
    ).publish(live)

    assert not result.success
    assert result.metadata["network_called"] is False
    assert not called


def test_unconfigured_upload_post_fails_without_network(
    monkeypatch,
    tmp_path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    fake = SimpleNamespace(
        is_configured=lambda: False,
        username="demo-account",
        upload_video=lambda **kwargs: pytest.fail(
            "provider should not be called"
        ),
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.publishing.upload_post_service",
        fake,
    )

    result = MPTUploadPostPublisher(
        allow_live_publish=True
    ).publish(
        replace(request(), video_uri=str(video), dry_run=False)
    )

    assert not result.success
    assert "not configured" in (result.error or "").lower()
    assert result.metadata["network_called"] is False
