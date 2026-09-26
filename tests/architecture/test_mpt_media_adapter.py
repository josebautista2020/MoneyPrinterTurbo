"""Offline tests for MPT audio/subtitle/render assembly adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from extensions.content_studio.media import MediaAssemblyPlan, assemble_media
from extensions.mpt_adapter.media import MPTMediaAssembler


def plan(tmp_path: Path, subtitle_enabled: bool = True) -> MediaAssemblyPlan:
    image = tmp_path / "visual-1.png"
    video = tmp_path / "visual-2.mp4"
    Image.new("RGB", (8, 8)).save(image)
    video.write_bytes(b"fake-video")
    return MediaAssemblyPlan(
        assembly_id="assembly-1",
        project_id="project-1",
        story_id="story-1",
        episode_id="episode-1",
        script="Hello world. This is a test.",
        language="en-US",
        voice_name="test-voice",
        visual_uris=(str(image), str(video)),
        visual_kinds=("image", "video"),
        visual_durations_seconds=(5.0, 7.0),
        aspect_ratio="9:16",
        resolution="1080x1920",
        output_uri=str(tmp_path / "final.mp4"),
        subtitle_enabled=subtitle_enabled,
    )


def test_external_generation_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    called = False

    def fake_tts(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("extensions.mpt_adapter.media.voice.tts", fake_tts)

    with pytest.raises(RuntimeError, match="explicit authorization"):
        MPTMediaAssembler().assemble(plan(tmp_path))

    assert not called


def test_mpt_media_adapter_maps_full_pipeline(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_tts(**kwargs):
        calls.append(("tts", kwargs))
        Path(kwargs["voice_file"]).write_bytes(b"wav")
        return SimpleNamespace(cues=[1])

    def fake_create_subtitle(**kwargs):
        calls.append(("subtitle", kwargs))
        Path(kwargs["subtitle_file"]).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nWorld\n",
            encoding="utf-8",
        )

    def fake_image_clip(image_path, clip_duration=5):
        calls.append(("image_clip", image_path, clip_duration))
        output = tmp_path / "image-clip.mp4"
        output.write_bytes(b"clip")
        return str(output)

    def fake_combine(**kwargs):
        calls.append(("combine", kwargs))
        Path(kwargs["combined_video_path"]).write_bytes(b"combined")
        return kwargs["combined_video_path"]

    def fake_render(**kwargs):
        calls.append(("render", kwargs))
        Path(kwargs["output_file"]).write_bytes(b"final")
        return True

    monkeypatch.setattr("extensions.mpt_adapter.media.voice.tts", fake_tts)
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.get_audio_duration",
        lambda path: 12.0,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.create_subtitle",
        fake_create_subtitle,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.render_image_zoom_video",
        fake_image_clip,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.combine_videos",
        fake_combine,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.generate_video",
        fake_render,
    )

    p = plan(tmp_path)
    assembler = MPTMediaAssembler(
        allow_external_generation=True,
        estimated_cost_usd=0.04,
        work_dir=str(tmp_path / "work"),
    )
    result = assemble_media(assembler, p, max_cost_usd=0.05)

    assert result.success
    assert result.cost_usd == pytest.approx(0.04)
    assert result.audio is not None
    assert result.audio.duration_seconds == pytest.approx(12.0)
    assert result.subtitle is not None
    assert result.subtitle.cue_count == 2
    assert result.video is not None
    assert result.video.uri == p.output_uri
    assert result.video.width == 1080
    assert result.video.height == 1920
    assert result.video.metadata["publication_performed"] is False
    assert [item[0] for item in calls] == [
        "tts", "subtitle", "image_clip", "combine", "render"
    ]


def test_subtitles_can_be_disabled(tmp_path, monkeypatch) -> None:
    def fake_tts(**kwargs):
        Path(kwargs["voice_file"]).write_bytes(b"wav")
        return SimpleNamespace(cues=[1])

    def fake_image_clip(image_path, clip_duration=5):
        output = tmp_path / "clip.mp4"
        output.write_bytes(b"clip")
        return str(output)

    def fake_combine(**kwargs):
        Path(kwargs["combined_video_path"]).write_bytes(b"combined")
        return kwargs["combined_video_path"]

    def fake_render(**kwargs):
        Path(kwargs["output_file"]).write_bytes(b"final")
        return True

    monkeypatch.setattr("extensions.mpt_adapter.media.voice.tts", fake_tts)
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.get_audio_duration",
        lambda path: 10.0,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.create_subtitle",
        lambda **kwargs: pytest.fail("subtitle should not be generated"),
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.render_image_zoom_video",
        fake_image_clip,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.combine_videos",
        fake_combine,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.generate_video",
        fake_render,
    )

    p = plan(tmp_path, subtitle_enabled=False)
    result = MPTMediaAssembler(
        allow_external_generation=True,
        estimated_cost_usd=0.0,
    ).assemble(p)

    assert result.success
    assert result.subtitle is None


def test_missing_visual_fails_before_tts_without_render(tmp_path, monkeypatch) -> None:
    p = plan(tmp_path)
    Path(p.visual_uris[-1]).unlink()
    rendered = False
    tts_called = False

    def fake_tts(**kwargs):
        nonlocal tts_called
        tts_called = True
        Path(kwargs["voice_file"]).write_bytes(b"wav")
        return SimpleNamespace(cues=[1])

    def fake_render(**kwargs):
        nonlocal rendered
        rendered = True

    monkeypatch.setattr("extensions.mpt_adapter.media.voice.tts", fake_tts)
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.get_audio_duration",
        lambda path: 10.0,
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.create_subtitle",
        lambda **kwargs: Path(kwargs["subtitle_file"]).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        ),
    )
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.video.generate_video",
        fake_render,
    )

    result = MPTMediaAssembler(
        allow_external_generation=True,
        estimated_cost_usd=0.02,
    ).assemble(p)

    assert not result.success
    assert "does not exist" in (result.error or "")
    assert result.cost_usd == 0.0
    assert result.metadata["provider_called"] is False
    assert not tts_called
    assert not rendered


def test_mpt_media_estimate_exposes_configured_cost(tmp_path) -> None:
    assembler = MPTMediaAssembler(estimated_cost_usd=0.125)

    assert assembler.estimate_cost_usd(plan(tmp_path)) == pytest.approx(0.125)


def test_corrupt_image_fails_before_tts(tmp_path, monkeypatch) -> None:
    p = plan(tmp_path)
    Path(p.visual_uris[0]).write_bytes(b"not a PNG")
    calls = []
    monkeypatch.setattr(
        "extensions.mpt_adapter.media.voice.tts",
        lambda **kwargs: calls.append(kwargs),
    )
    result = MPTMediaAssembler(
        allow_external_generation=True,
        estimated_cost_usd=0.02,
    ).assemble(p)
    assert not result.success
    assert result.cost_usd == 0.0
    assert result.metadata["provider_called"] is False
    assert calls == []
