"""Visual generation adapter backed by MoneyPrinterTurbo image materials."""

from __future__ import annotations

import math

from app.models.schema import VideoAspect
from app.services import material

from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualGenerator,
    VisualRequest,
    VisualResult,
)


class MPTImageVisualGenerator(VisualGenerator):
    """Generate one image through MPT's OpenAI-compatible image material path."""

    def __init__(
        self,
        *,
        allow_paid_generation: bool = False,
        cost_per_image_usd: float | None = None,
        save_dir: str = "",
    ) -> None:
        if cost_per_image_usd is not None:
            if (
                isinstance(cost_per_image_usd, bool)
                or not isinstance(cost_per_image_usd, (int, float))
                or not math.isfinite(float(cost_per_image_usd))
                or cost_per_image_usd < 0
            ):
                raise ValueError(
                    "cost_per_image_usd must be a non-negative finite number"
                )
            cost_per_image_usd = float(cost_per_image_usd)
        self._allow_paid_generation = allow_paid_generation
        self._cost_per_image_usd = cost_per_image_usd
        self._save_dir = save_dir

    @property
    def engine_name(self) -> str:
        return "moneyprinterturbo-openai-image"

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        del request
        return self._cost_per_image_usd

    def generate(self, request: VisualRequest) -> VisualResult:
        if not self._allow_paid_generation:
            raise RuntimeError(
                "paid visual generation is disabled; explicit authorization "
                "is required before invoking MoneyPrinterTurbo image generation"
            )

        if request.asset_kind != "image":
            return self._failure(
                request,
                "MPTImageVisualGenerator only supports image requests",
            )

        if request.reference_asset_ids:
            return self._failure(
                request,
                "MPT OpenAI-compatible image generation does not support "
                "reference_asset_ids; refusing to silently drop consistency inputs",
            )

        if not material.is_openai_image_enabled():
            return self._failure(
                request,
                "MoneyPrinterTurbo OpenAI-compatible image generation is not configured",
            )

        try:
            aspect = VideoAspect(request.aspect_ratio)
        except ValueError:
            return self._failure(
                request,
                f"MoneyPrinterTurbo does not support aspect ratio "
                f"{request.aspect_ratio!r}",
            )

        prompt = request.prompt
        if request.negative_constraints:
            prompt += "\nAvoid: " + "; ".join(request.negative_constraints)

        try:
            materials = material.generate_images_openai(
                search_term=prompt,
                minimum_duration=max(1, math.ceil(request.duration_seconds)),
                video_aspect=aspect,
                save_dir=self._save_dir,
            )
        except Exception as exc:
            return self._failure(
                request,
                f"MoneyPrinterTurbo image generation raised "
                f"{type(exc).__name__}: {exc}",
            )

        if not materials:
            return self._failure(
                request,
                "MoneyPrinterTurbo image generation returned no material",
            )

        item = materials[0]
        source_info = (
            item.source_info if isinstance(item.source_info, dict) else {}
        )
        rendition = source_info.get("rendition")
        rendition = rendition if isinstance(rendition, dict) else {}

        width = self._positive_int_or_none(rendition.get("width"))
        height = self._positive_int_or_none(rendition.get("height"))
        provider = str(
            getattr(item, "provider", "") or source_info.get("provider") or
            "openai_image"
        )
        uri = str(getattr(item, "url", "") or "")
        if not uri:
            return self._failure(
                request,
                "MoneyPrinterTurbo generated material without a local URI",
            )

        artifact = VisualArtifact(
            asset_id=request.request_id,
            request_id=request.request_id,
            shot_id=request.shot_id,
            asset_kind="image",
            uri=uri,
            engine=self.engine_name,
            provider=provider,
            width=width,
            height=height,
            duration_seconds=request.duration_seconds,
            metadata={
                "requested_resolution": request.resolution,
                "requested_aspect_ratio": request.aspect_ratio,
                "source_info": source_info,
            },
        )
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=True,
            artifacts=(artifact,),
            cost_usd=self._cost_per_image_usd,
            metadata={
                "material_count": len(materials),
                "paid_generation_authorized": True,
            },
        )

    def _failure(
        self,
        request: VisualRequest,
        error: str,
    ) -> VisualResult:
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=False,
            error=error,
            cost_usd=0.0,
        )

    @staticmethod
    def _positive_int_or_none(value: object) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
