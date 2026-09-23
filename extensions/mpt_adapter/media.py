"""MoneyPrinterTurbo adapter for audio, subtitles and final rendering."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

from app.models.schema import (
    VideoAspect,
    VideoConcatMode,
    VideoFitMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services import video, voice

from extensions.content_studio.media import (
    AudioArtifact,
    MediaAssembler,
    MediaAssemblyPlan,
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
)


class MPTMediaAssembler(MediaAssembler):
    """Assemble narration, subtitles and final video using MPT services."""

    def __init__(
        self,
        *,
        allow_external_generation: bool = False,
        estimated_cost_usd: float | None = None,
        work_dir: str = "",
    ) -> None:
        if estimated_cost_usd is not None:
            if (
                isinstance(estimated_cost_usd, bool)
                or not isinstance(estimated_cost_usd, (int, float))
                or not math.isfinite(float(estimated_cost_usd))
                or estimated_cost_usd < 0
            ):
                raise ValueError(
                    "estimated_cost_usd must be a non-negative finite number"
                )
            estimated_cost_usd = float(estimated_cost_usd)
        self._allow_external_generation = allow_external_generation
        self._estimated_cost_usd = estimated_cost_usd
        self._work_dir = work_dir

    @property
    def engine_name(self) -> str:
        return "moneyprinterturbo-media"

    def estimate_cost_usd(self, plan: MediaAssemblyPlan) -> float | None:
        del plan
        return self._estimated_cost_usd

    def assemble(self, plan: MediaAssemblyPlan) -> MediaAssemblyResult:
        if not self._allow_external_generation:
            raise RuntimeError(
                "external media generation is disabled; explicit authorization "
                "is required before invoking MoneyPrinterTurbo TTS"
            )

        work_dir = Path(
            self._work_dir
            or Path(plan.output_uri).parent
            / f".content-studio-{plan.assembly_id}"
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(work_dir / "narration.wav")
        subtitle_path = str(work_dir / "subtitles.srt")
        combined_path = str(work_dir / "combined-visuals.mp4")

        tts_started = False
        try:
            tts_started = True
            sub_maker = voice.tts(
                text=plan.script,
                voice_name=plan.voice_name,
                voice_rate=plan.voice_rate,
                voice_file=audio_path,
                voice_volume=plan.voice_volume,
            )
            if sub_maker is None or not os.path.isfile(audio_path):
                return self._failure(
                    plan,
                    "MoneyPrinterTurbo TTS did not produce narration audio",
                    provider_called=tts_started,
                )

            audio_duration = voice.get_audio_duration(audio_path)
            if not audio_duration or audio_duration <= 0:
                return self._failure(
                    plan,
                    "MoneyPrinterTurbo could not determine narration duration",
                    provider_called=True,
                )

            subtitle_artifact = None
            if plan.subtitle_enabled:
                voice.create_subtitle(
                    sub_maker=sub_maker,
                    text=plan.script,
                    subtitle_file=subtitle_path,
                    word_level=plan.subtitle_mode == "word_by_word",
                )
                if not os.path.isfile(subtitle_path):
                    return self._failure(
                        plan,
                        "MoneyPrinterTurbo subtitle generation did not create SRT",
                        provider_called=True,
                    )
                cue_count = self._count_srt_cues(subtitle_path)
                if cue_count <= 0:
                    return self._failure(
                        plan,
                        "MoneyPrinterTurbo subtitle file contains no cues",
                        provider_called=True,
                    )
                subtitle_artifact = SubtitleArtifact(
                    subtitle_id=f"{plan.assembly_id}.subtitles",
                    uri=subtitle_path,
                    format="srt",
                    cue_count=cue_count,
                    engine=self.engine_name,
                    provider="moneyprinterturbo",
                    metadata={
                        "mode": plan.subtitle_mode,
                        "source": "tts-timing",
                    },
                )

            visual_paths = self._prepare_visuals(plan)
            aspect = VideoAspect(plan.aspect_ratio)
            transition = self._transition(plan.transition)
            video.combine_videos(
                combined_video_path=combined_path,
                video_paths=visual_paths,
                audio_file=audio_path,
                video_aspect=aspect,
                video_concat_mode=VideoConcatMode.sequential,
                video_transition_mode=transition,
                max_clip_duration=plan.clip_duration_seconds,
                threads=2,
                video_fit_mode=VideoFitMode(plan.fit_mode),
            )
            if not os.path.isfile(combined_path):
                return self._failure(
                    plan,
                    "MoneyPrinterTurbo did not create combined visual track",
                    provider_called=True,
                )

            output_path = Path(plan.output_uri)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            params = VideoParams(
                video_subject=plan.assembly_id,
                video_script=plan.script,
                video_aspect=plan.aspect_ratio,
                video_fit_mode=plan.fit_mode,
                video_concat_mode=VideoConcatMode.sequential.value,
                video_transition_mode=transition,
                video_clip_duration=plan.clip_duration_seconds,
                voice_name=plan.voice_name,
                voice_volume=plan.voice_volume,
                voice_rate=plan.voice_rate,
                subtitle_enabled=plan.subtitle_enabled,
                subtitle_position=plan.subtitle_position,
                subtitle_display_mode=plan.subtitle_mode,
                font_name=plan.font_name,
                text_fore_color=plan.text_color,
                text_background_color=plan.background_color or False,
                rounded_subtitle_background=plan.rounded_subtitle_background,
                font_size=plan.font_size,
                stroke_color=plan.stroke_color,
                stroke_width=plan.stroke_width,
                bgm_type="none",
            )
            video.generate_video(
                video_path=combined_path,
                audio_path=audio_path,
                subtitle_path=subtitle_path if plan.subtitle_enabled else "",
                output_file=plan.output_uri,
                params=params,
            )
            if not os.path.isfile(plan.output_uri):
                return self._failure(
                    plan,
                    "MoneyPrinterTurbo final render did not create output video",
                    provider_called=True,
                )

            width, height = aspect.to_resolution()
            audio_artifact = AudioArtifact(
                audio_id=f"{plan.assembly_id}.audio",
                uri=audio_path,
                duration_seconds=float(audio_duration),
                engine=self.engine_name,
                provider="moneyprinterturbo",
                metadata={"voice_name": plan.voice_name},
            )
            render_artifact = RenderArtifact(
                render_id=f"{plan.assembly_id}.video",
                uri=plan.output_uri,
                engine=self.engine_name,
                provider="moneyprinterturbo",
                width=width,
                height=height,
                duration_seconds=float(audio_duration),
                metadata={
                    "aspect_ratio": plan.aspect_ratio,
                    "resolution": plan.resolution,
                    "visual_count": len(visual_paths),
                    "publication_performed": False,
                },
            )
            return MediaAssemblyResult(
                assembly_id=plan.assembly_id,
                engine=self.engine_name,
                success=True,
                audio=audio_artifact,
                subtitle=subtitle_artifact,
                video=render_artifact,
                cost_usd=self._estimated_cost_usd,
                metadata={
                    "external_generation_authorized": True,
                    "publication_performed": False,
                },
            )
        except Exception as exc:
            return self._failure(
                plan,
                f"MoneyPrinterTurbo media assembly raised "
                f"{type(exc).__name__}: {exc}",
                provider_called=tts_started,
            )

    def _prepare_visuals(self, plan: MediaAssemblyPlan) -> list[str]:
        prepared = []
        for index, (uri, kind, duration) in enumerate(
            zip(
                plan.visual_uris,
                plan.visual_kinds,
                plan.visual_durations_seconds,
            ),
            start=1,
        ):
            if not os.path.isfile(uri):
                raise FileNotFoundError(f"visual input does not exist: {uri}")
            if kind == "video":
                prepared.append(uri)
                continue
            rendered = video.render_image_zoom_video(
                image_path=uri,
                clip_duration=max(1, math.ceil(duration)),
            )
            if not rendered or not os.path.isfile(rendered):
                raise RuntimeError(
                    f"failed to convert image visual #{index} into video clip"
                )
            prepared.append(rendered)
        return prepared

    @staticmethod
    def _transition(value: str) -> VideoTransitionMode | None:
        mapping = {
            "none": VideoTransitionMode.none,
            "fade_in": VideoTransitionMode.fade_in,
            "fade_out": VideoTransitionMode.fade_out,
            "slide_in": VideoTransitionMode.slide_in,
            "slide_out": VideoTransitionMode.slide_out,
            "zoom_in": VideoTransitionMode.zoom_in,
            "zoom_out": VideoTransitionMode.zoom_out,
            "shuffle": VideoTransitionMode.shuffle,
        }
        return mapping[value]

    @staticmethod
    def _count_srt_cues(path: str) -> int:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return len(
            re.findall(
                r"(?m)^\s*\d+\s*$",
                text,
            )
        )

    def _failure(
        self,
        plan: MediaAssemblyPlan,
        error: str,
        *,
        provider_called: bool,
    ) -> MediaAssemblyResult:
        return MediaAssemblyResult(
            assembly_id=plan.assembly_id,
            engine=self.engine_name,
            success=False,
            error=error,
            cost_usd=(
                self._estimated_cost_usd if provider_called else 0.0
            ),
            metadata={
                "provider_called": provider_called,
                "publication_performed": False,
            },
        )
