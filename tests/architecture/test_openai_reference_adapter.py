"""Tests for the OpenAI reference-image adapter without network calls."""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from extensions.content_studio.consistency import ReferenceAsset
from extensions.content_studio.visual_generation import VisualRequest
from extensions.openai_image_adapter import OpenAIReferenceVisualGenerator


def _png_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 24), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class _FakeResponses:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="response-1",
            output=[
                SimpleNamespace(
                    type="image_generation_call",
                    result=self.result,
                )
            ],
        )


class _FakeClient:
    def __init__(self, result: str) -> None:
        self.responses = _FakeResponses(result)


def request() -> VisualRequest:
    return VisualRequest(
        request_id="shot-1",
        project_id="project-1",
        story_id="story-1",
        episode_id="episode-1",
        scene_id="scene-1",
        shot_id="shot-1",
        prompt="A consistent friendly puppy in a park.",
        aspect_ratio="9:16",
        resolution="1080x1920",
        duration_seconds=5,
        character_ids=("puppy-1",),
        negative_constraints=("do not change fur color",),
        reference_asset_ids=("puppy-ref",),
    )


def test_paid_reference_generation_is_disabled_by_default(tmp_path) -> None:
    client = _FakeClient(_png_base64())
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        output_dir=str(tmp_path),
        client=client,
    )

    with pytest.raises(RuntimeError, match="explicit authorization"):
        generator.generate_with_references(
            request(),
            (
                ReferenceAsset(
                    "puppy-ref",
                    "https://example.com/puppy.png",
                ),
            ),
        )

    assert client.responses.calls == []


def test_reference_adapter_passes_multiple_images_and_saves_result(
    tmp_path,
) -> None:
    local_reference = tmp_path / "local-reference.png"
    Image.new("RGB", (8, 8), "white").save(
        local_reference,
        format="PNG",
    )
    client = _FakeClient(_png_base64())
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        allow_paid_generation=True,
        cost_per_generation_usd=0.07,
        output_dir=str(tmp_path / "generated"),
        client=client,
    )
    references = (
        ReferenceAsset(
            "puppy-ref",
            str(local_reference),
            character_id="puppy-1",
        ),
        ReferenceAsset(
            "park-ref",
            "https://example.com/park.png",
            location_id="park",
        ),
        ReferenceAsset(
            "file-ref",
            "openai-file://file_123",
        ),
    )

    result = generator.generate_with_references(request(), references)

    assert result.success
    assert result.cost_usd == pytest.approx(0.07)
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.width == 16
    assert artifact.height == 24
    assert artifact.provider == "openai"
    assert artifact.metadata["reference_asset_ids"] == [
        "puppy-ref",
        "park-ref",
        "file-ref",
    ]

    call = client.responses.calls[0]
    assert call["model"] == "test-response-model"
    assert call["tools"] == [
        {
            "type": "image_generation",
            "model": "test-image-model",
        }
    ]
    content = call["input"][0]["content"]
    image_inputs = [item for item in content if item["type"] == "input_image"]
    assert len(image_inputs) == 3
    assert image_inputs[0]["image_url"].startswith("data:image/png;base64,")
    assert image_inputs[1]["image_url"] == "https://example.com/park.png"
    assert image_inputs[2]["file_id"] == "file_123"
    assert "Avoid: do not change fur color" in content[0]["text"]


def test_missing_local_reference_fails_before_provider_call(tmp_path) -> None:
    client = _FakeClient(_png_base64())
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        allow_paid_generation=True,
        output_dir=str(tmp_path),
        client=client,
    )

    result = generator.generate_with_references(
        request(),
        (
            ReferenceAsset(
                "puppy-ref",
                str(tmp_path / "missing.png"),
            ),
        ),
    )

    assert not result.success
    assert result.cost_usd == 0.0
    assert client.responses.calls == []


def test_adapter_requires_at_least_one_reference(tmp_path) -> None:
    client = _FakeClient(_png_base64())
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        allow_paid_generation=True,
        output_dir=str(tmp_path),
        client=client,
    )

    result = generator.generate_with_references(request(), ())

    assert not result.success
    assert "at least one" in (result.error or "")
    assert client.responses.calls == []


def test_adapter_exposes_configured_cost_estimate() -> None:
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        cost_per_generation_usd=0.123,
        client=_FakeClient(_png_base64()),
    )

    assert generator.estimate_cost_usd(request()) == pytest.approx(0.123)


def test_adapter_unknown_cost_remains_unknown() -> None:
    generator = OpenAIReferenceVisualGenerator(
        response_model="test-response-model",
        image_model="test-image-model",
        client=_FakeClient(_png_base64()),
    )

    assert generator.estimate_cost_usd(request()) is None
