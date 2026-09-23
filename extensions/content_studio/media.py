"""Provider-neutral audio, subtitle and final render assembly contracts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.consistency import ConsistencyReport
from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    ProjectSpec,
    SCHEMA_VERSION,
)

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_RESOLUTION_RE = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")
_ASPECT_RATIO_RE = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")


def _require_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DomainValidationError(
            f"{field_name} must match {_ID_RE.pattern!r}; got {value!r}"
        )
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _positive_number(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise DomainValidationError(
            f"{field_name} must be a positive finite number"
        )
    return float(value)


def _non_negative_number(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise DomainValidationError(
            f"{field_name} must be a non-negative finite number"
        )
    return float(value)


def _optional_non_negative(
    value: float | None,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _non_negative_number(value, field_name)


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DomainValidationError(f"{field_name} must be a positive integer")
    return value


def _unique_texts(
    values: tuple[str, ...] | list[str],
    field_name: str,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field_name) for value in values)
    if required and not normalized:
        raise DomainValidationError(f"{field_name} must contain at least one value")
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field_name} must not contain duplicates")
    return normalized


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("metadata must be a mapping")
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(
            "metadata must contain only JSON-compatible values"
        ) from exc
    if not isinstance(decoded, dict):
        raise DomainValidationError("metadata must serialize to a JSON object")
    return decoded


def _payload(
    payload: Mapping[str, Any],
    allowed_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainValidationError("payload must be a mapping")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise DomainValidationError(
            f"unsupported schema_version {version!r}; expected "
            f"{SCHEMA_VERSION!r}"
        )
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


@dataclass(frozen=True, slots=True)
class MediaAssemblyPlan(JsonContract):
    """Inputs needed to synthesize audio, subtitles and final video."""

    assembly_id: str
    project_id: str
    story_id: str
    episode_id: str
    script: str
    language: str
    voice_name: str
    visual_uris: tuple[str, ...]
    visual_durations_seconds: tuple[float, ...]
    aspect_ratio: str
    resolution: str
    output_uri: str
    voice_rate: float = 1.0
    voice_volume: float = 1.0
    subtitle_enabled: bool = True
    subtitle_mode: str = "sentence"
    subtitle_position: str = "bottom"
    font_name: str = "STHeitiMedium.ttc"
    font_size: int = 60
    text_color: str = "#FFFFFF"
    background_color: str | None = None
    rounded_subtitle_background: bool = False
    stroke_color: str = "#000000"
    stroke_width: float = 1.5
    clip_duration_seconds: int = 5
    fit_mode: str = "cover"
    transition: str = "none"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("assembly_id", "project_id", "story_id", "episode_id"):
            object.__setattr__(
                self,
                name,
                _require_id(getattr(self, name), name),
            )
        for name in (
            "script",
            "language",
            "voice_name",
            "output_uri",
            "subtitle_position",
            "font_name",
            "text_color",
            "stroke_color",
        ):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "visual_uris",
            _unique_texts(self.visual_uris, "visual_uris", required=True),
        )
        durations = tuple(
            _positive_number(value, "visual_durations_seconds")
            for value in self.visual_durations_seconds
        )
        if len(durations) != len(self.visual_uris):
            raise DomainValidationError(
                "visual_durations_seconds must align one-to-one with visual_uris"
            )
        object.__setattr__(
            self,
            "visual_durations_seconds",
            durations,
        )
        if (
            not isinstance(self.aspect_ratio, str)
            or not _ASPECT_RATIO_RE.fullmatch(self.aspect_ratio)
        ):
            raise DomainValidationError(
                "aspect_ratio must use positive W:H notation"
            )
        if (
            not isinstance(self.resolution, str)
            or not _RESOLUTION_RE.fullmatch(self.resolution)
        ):
            raise DomainValidationError(
                "resolution must use positive WIDTHxHEIGHT notation"
            )
        object.__setattr__(
            self,
            "voice_rate",
            _positive_number(self.voice_rate, "voice_rate"),
        )
        object.__setattr__(
            self,
            "voice_volume",
            _positive_number(self.voice_volume, "voice_volume"),
        )
        if not isinstance(self.subtitle_enabled, bool):
            raise DomainValidationError("subtitle_enabled must be a boolean")
        if self.subtitle_mode not in {"sentence", "word_by_word"}:
            raise DomainValidationError(
                "subtitle_mode must be 'sentence' or 'word_by_word'"
            )
        if self.subtitle_position not in {
            "top",
            "bottom",
            "center",
            "custom",
            "two_thirds_bottom",
        }:
            raise DomainValidationError("unsupported subtitle_position")
        object.__setattr__(
            self,
            "background_color",
            _optional_text(self.background_color, "background_color"),
        )
        if not isinstance(self.rounded_subtitle_background, bool):
            raise DomainValidationError(
                "rounded_subtitle_background must be a boolean"
            )
        object.__setattr__(
            self,
            "font_size",
            _positive_int(self.font_size, "font_size"),
        )
        object.__setattr__(
            self,
            "stroke_width",
            _non_negative_number(self.stroke_width, "stroke_width"),
        )
        object.__setattr__(
            self,
            "clip_duration_seconds",
            _positive_int(
                self.clip_duration_seconds,
                "clip_duration_seconds",
            ),
        )
        if self.fit_mode not in {"cover", "contain"}:
            raise DomainValidationError(
                "fit_mode must be 'cover' or 'contain'"
            )
        if self.transition not in {
            "none",
            "fade_in",
            "fade_out",
            "slide_in",
            "slide_out",
            "zoom_in",
            "zoom_out",
            "shuffle",
        }:
            raise DomainValidationError("unsupported transition")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "assembly_id",
                "project_id",
                "story_id",
                "episode_id",
                "script",
                "language",
                "voice_name",
                "visual_uris",
                "visual_durations_seconds",
                "aspect_ratio",
                "resolution",
                "output_uri",
                "voice_rate",
                "voice_volume",
                "subtitle_enabled",
                "subtitle_mode",
                "subtitle_position",
                "font_name",
                "font_size",
                "text_color",
                "background_color",
                "rounded_subtitle_background",
                "stroke_color",
                "stroke_width",
                "clip_duration_seconds",
                "fit_mode",
                "transition",
                "metadata",
            },
        )
        data["visual_uris"] = tuple(data.get("visual_uris", ()))
        data["visual_durations_seconds"] = tuple(
            data.get("visual_durations_seconds", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class AudioArtifact(JsonContract):
    audio_id: str
    uri: str
    duration_seconds: float
    engine: str
    provider: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "audio_id", _require_id(self.audio_id, "audio_id"))
        for name in ("uri", "engine", "provider"):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "duration_seconds",
            _positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"audio_id", "uri", "duration_seconds", "engine", "provider", "metadata"},
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class SubtitleArtifact(JsonContract):
    subtitle_id: str
    uri: str
    format: str
    cue_count: int
    engine: str
    provider: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subtitle_id",
            _require_id(self.subtitle_id, "subtitle_id"),
        )
        for name in ("uri", "format", "engine", "provider"):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "cue_count",
            _positive_int(self.cue_count, "cue_count"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"subtitle_id", "uri", "format", "cue_count", "engine", "provider", "metadata"},
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RenderArtifact(JsonContract):
    render_id: str
    uri: str
    engine: str
    provider: str
    width: int
    height: int
    duration_seconds: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "render_id",
            _require_id(self.render_id, "render_id"),
        )
        for name in ("uri", "engine", "provider"):
            object.__setattr__(
                self,
                name,
                _require_text(getattr(self, name), name),
            )
        object.__setattr__(self, "width", _positive_int(self.width, "width"))
        object.__setattr__(self, "height", _positive_int(self.height, "height"))
        object.__setattr__(
            self,
            "duration_seconds",
            _positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "render_id",
                "uri",
                "engine",
                "provider",
                "width",
                "height",
                "duration_seconds",
                "metadata",
            },
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class MediaAssemblyResult(JsonContract):
    assembly_id: str
    engine: str
    success: bool
    audio: AudioArtifact | None = None
    subtitle: SubtitleArtifact | None = None
    video: RenderArtifact | None = None
    error: str | None = None
    cost_usd: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assembly_id",
            _require_id(self.assembly_id, "assembly_id"),
        )
        object.__setattr__(self, "engine", _require_text(self.engine, "engine"))
        if not isinstance(self.success, bool):
            raise DomainValidationError("success must be a boolean")
        for value, expected, name in (
            (self.audio, AudioArtifact, "audio"),
            (self.subtitle, SubtitleArtifact, "subtitle"),
            (self.video, RenderArtifact, "video"),
        ):
            if value is not None and not isinstance(value, expected):
                raise DomainValidationError(f"{name} has invalid type")
        error = _optional_text(self.error, "error")
        cost = _optional_non_negative(self.cost_usd, "cost_usd")
        if self.success and (self.audio is None or self.video is None):
            raise DomainValidationError(
                "successful MediaAssemblyResult requires audio and video"
            )
        if self.success and error is not None:
            raise DomainValidationError(
                "successful MediaAssemblyResult cannot contain error"
            )
        if not self.success and error is None:
            raise DomainValidationError(
                "failed MediaAssemblyResult must contain error"
            )
        object.__setattr__(self, "error", error)
        object.__setattr__(self, "cost_usd", cost)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def validate_plan(self, plan: MediaAssemblyPlan) -> None:
        if self.assembly_id != plan.assembly_id:
            raise DomainValidationError(
                "MediaAssemblyResult assembly_id does not match plan"
            )
        if self.success and plan.subtitle_enabled and self.subtitle is None:
            raise DomainValidationError(
                "subtitle-enabled plan requires a SubtitleArtifact"
            )
        if self.success and not plan.subtitle_enabled and self.subtitle is not None:
            raise DomainValidationError(
                "subtitle-disabled plan must not contain SubtitleArtifact"
            )
        if self.success and self.video is not None and self.video.uri != plan.output_uri:
            raise DomainValidationError(
                "RenderArtifact URI does not match plan output_uri"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["audio"] = self.audio.to_dict() if self.audio else None
        payload["subtitle"] = (
            self.subtitle.to_dict() if self.subtitle else None
        )
        payload["video"] = self.video.to_dict() if self.video else None
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "assembly_id",
                "engine",
                "success",
                "audio",
                "subtitle",
                "video",
                "error",
                "cost_usd",
                "metadata",
            },
        )
        if data.get("audio") is not None:
            data["audio"] = AudioArtifact.from_dict(data["audio"])
        if data.get("subtitle") is not None:
            data["subtitle"] = SubtitleArtifact.from_dict(data["subtitle"])
        if data.get("video") is not None:
            data["video"] = RenderArtifact.from_dict(data["video"])
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class MediaAssembler(Protocol):
    @property
    def engine_name(self) -> str:
        ...

    def estimate_cost_usd(self, plan: MediaAssemblyPlan) -> float | None:
        ...

    def assemble(self, plan: MediaAssemblyPlan) -> MediaAssemblyResult:
        ...


def build_media_assembly_plan(
    project: ProjectSpec,
    consistency_report: ConsistencyReport,
    *,
    assembly_id: str,
    script: str,
    language: str,
    voice_name: str,
    output_uri: str,
    subtitle_enabled: bool = True,
) -> MediaAssemblyPlan:
    """Build a render plan from accepted visual-consistency outputs."""
    if consistency_report.project_id != project.project_id:
        raise DomainValidationError(
            "ConsistencyReport project_id does not match ProjectSpec"
        )
    if not consistency_report.success:
        raise DomainValidationError(
            "cannot render a ConsistencyReport with rejected visual results"
        )

    visual_uris = []
    visual_durations = []
    for result in consistency_report.results:
        attempt = result.final_attempt
        if not attempt.visual_result.success:
            raise DomainValidationError(
                "accepted consistency result contains failed visual output"
            )
        artifacts = attempt.visual_result.artifacts
        if not artifacts:
            raise DomainValidationError(
                "accepted consistency result has no visual artifact"
            )
        visual_uris.append(artifacts[0].uri)
        duration = artifacts[0].duration_seconds
        if duration is None:
            raise DomainValidationError(
                "accepted visual artifact is missing duration_seconds"
            )
        visual_durations.append(duration)

    return MediaAssemblyPlan(
        assembly_id=assembly_id,
        project_id=project.project_id,
        story_id=consistency_report.story_id,
        episode_id=consistency_report.episode_id,
        script=script,
        language=language,
        voice_name=voice_name,
        visual_uris=tuple(visual_uris),
        visual_durations_seconds=tuple(visual_durations),
        aspect_ratio=project.aspect_ratio,
        resolution=project.resolution,
        output_uri=output_uri,
        subtitle_enabled=subtitle_enabled,
        metadata={"source": "ConsistencyReport"},
    )


def assemble_media(
    assembler: MediaAssembler,
    plan: MediaAssemblyPlan,
    *,
    max_cost_usd: float | None = None,
) -> MediaAssemblyResult:
    """Run final media assembly with optional fail-closed cost preflight."""
    budget = _optional_non_negative(max_cost_usd, "max_cost_usd")
    if budget is not None:
        estimate = assembler.estimate_cost_usd(plan)
        if estimate is None:
            raise DomainValidationError(
                "cost estimate required before budget-controlled media assembly"
            )
        estimate = _non_negative_number(estimate, "estimated_cost_usd")
        if estimate > budget:
            raise DomainValidationError(
                f"projected media assembly cost {estimate:.6f} USD "
                f"exceeds budget {budget:.6f} USD"
            )

    result = assembler.assemble(plan)
    if not isinstance(result, MediaAssemblyResult):
        raise DomainValidationError(
            "MediaAssembler must return a MediaAssemblyResult"
        )
    result.validate_plan(plan)
    return result
