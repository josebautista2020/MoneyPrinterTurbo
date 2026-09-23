"""Tests for the MoneyPrinterTurbo visual-generation ACL adapter."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from extensions.content_studio.visual_generation import VisualRequest
from extensions.mpt_adapter.visual import MPTImageVisualGenerator


def request() -> VisualRequest:
    return VisualRequest(
        request_id="shot-1",
        project_id="project-1",
        story_id="story-1",
        episode_id="episode-1",
        scene_id="scene-1",
        shot_id="shot-1",
        prompt="A friendly character in a park.",
        aspect_ratio="9:16",
        resolution="1080x1920",
        duration_seconds=5,
        character_ids=("character-1",),
        negative_constraints=("do not change wardrobe",),
    )


def test_paid_generation_is_disabled_by_default(monkeypatch) -> None:
    called = False

    def fake_generate(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fake_generate,
    )

    with pytest.raises(RuntimeError, match="explicit authorization"):
        MPTImageVisualGenerator().generate(request())

    assert not called


def test_adapter_rejects_reference_assets_without_external_call(
    monkeypatch,
) -> None:
    called = False

    def fake_generate(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fake_generate,
    )
    req = replace(request(), reference_asset_ids=("reference-1",))

    result = MPTImageVisualGenerator(
        allow_paid_generation=True,
    ).generate(req)

    assert not result.success
    assert "reference_asset_ids" in (result.error or "")
    assert result.cost_usd == 0.0
    assert not called


def test_adapter_requires_mpt_image_configuration(monkeypatch) -> None:
    called = False
    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.is_openai_image_enabled",
        lambda: False,
    )

    def fake_generate(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fake_generate,
    )

    result = MPTImageVisualGenerator(
        allow_paid_generation=True,
    ).generate(request())

    assert not result.success
    assert "not configured" in (result.error or "")
    assert not called


def test_adapter_maps_mpt_image_material_to_visual_artifact(
    monkeypatch,
) -> None:
    captured = {}
    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.is_openai_image_enabled",
        lambda: True,
    )

    def fake_generate_images_openai(**kwargs):
        captured.update(kwargs)
        return [
            SimpleNamespace(
                provider="openai_image",
                url="/tmp/generated-shot.png",
                source_info={
                    "provider": "openai_image",
                    "rendition": {
                        "width": 1024,
                        "height": 1536,
                    },
                },
            )
        ]

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fake_generate_images_openai,
    )

    generator = MPTImageVisualGenerator(
        allow_paid_generation=True,
        cost_per_image_usd=0.04,
        save_dir="/tmp/visuals",
    )
    result = generator.generate(request())

    assert result.success
    assert result.cost_usd == pytest.approx(0.04)
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.uri == "/tmp/generated-shot.png"
    assert artifact.width == 1024
    assert artifact.height == 1536
    assert artifact.provider == "openai_image"
    assert artifact.request_id == "shot-1"

    assert captured["minimum_duration"] == 5
    assert captured["save_dir"] == "/tmp/visuals"
    assert captured["video_aspect"].value == "9:16"
    assert "Avoid: do not change wardrobe" in captured["search_term"]


def test_adapter_estimate_exposes_configured_unit_cost() -> None:
    generator = MPTImageVisualGenerator(
        cost_per_image_usd=0.025,
    )

    assert generator.estimate_cost_usd(request()) == pytest.approx(0.025)


def test_adapter_unknown_cost_remains_unknown() -> None:
    generator = MPTImageVisualGenerator()

    assert generator.estimate_cost_usd(request()) is None


def test_adapter_rejects_video_requests_before_provider_call(
    monkeypatch,
) -> None:
    called = False
    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.is_openai_image_enabled",
        lambda: True,
    )

    def fake_generate(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fake_generate,
    )

    result = MPTImageVisualGenerator(
        allow_paid_generation=True,
    ).generate(replace(request(), asset_kind="video"))

    assert not result.success
    assert "only supports image" in (result.error or "")
    assert not called
