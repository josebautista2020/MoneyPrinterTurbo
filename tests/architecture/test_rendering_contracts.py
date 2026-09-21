"""Behavioral tests for provider-neutral rendering contracts."""

import pytest

from extensions.content_studio.rendering import ExecutionRequest


def test_execution_request_accepts_video_stage() -> None:
    request = ExecutionRequest(
        request_id="episode-001",
        subject="A puppy learns to share",
        stop_at="video",
    )
    assert request.request_id == "episode-001"
    assert request.stop_at == "video"


@pytest.mark.parametrize("field", ["request_id", "subject"])
def test_execution_request_rejects_empty_required_fields(field: str) -> None:
    values = {
        "request_id": "episode-001",
        "subject": "A puppy learns to share",
    }
    values[field] = "   "
    with pytest.raises(ValueError):
        ExecutionRequest(**values)


def test_execution_request_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unsupported stop_at"):
        ExecutionRequest(
            request_id="episode-001",
            subject="A puppy learns to share",
            stop_at="publish",
        )
