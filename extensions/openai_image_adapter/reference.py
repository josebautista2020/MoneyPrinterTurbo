"""OpenAI reference-image adapter for Content Studio AI.

This module is intentionally outside the reusable Core. It implements the
ReferenceAwareVisualGenerator protocol with the OpenAI Responses API image
generation tool and accepts multiple input reference images.
"""

from __future__ import annotations

import base64
import io
import math
import mimetypes
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from openai import OpenAI
from PIL import Image, UnidentifiedImageError

from extensions.content_studio.consistency import (
    ReferenceAsset,
    ReferenceAwareVisualGenerator,
)
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualRequest,
    VisualResult,
)


class OpenAIReferenceVisualGenerator(ReferenceAwareVisualGenerator):
    """Reference-aware image generation through OpenAI Responses API."""

    def __init__(
        self,
        *,
        response_model: str,
        image_model: str,
        allow_paid_generation: bool = False,
        cost_per_generation_usd: float | None = None,
        output_dir: str = "",
        client: Any | None = None,
    ) -> None:
        self._response_model = self._require_text(
            response_model,
            "response_model",
        )
        self._image_model = self._require_text(
            image_model,
            "image_model",
        )
        if cost_per_generation_usd is not None:
            if (
                isinstance(cost_per_generation_usd, bool)
                or not isinstance(cost_per_generation_usd, (int, float))
                or not math.isfinite(float(cost_per_generation_usd))
                or cost_per_generation_usd < 0
            ):
                raise ValueError(
                    "cost_per_generation_usd must be a non-negative "
                    "finite number"
                )
            cost_per_generation_usd = float(cost_per_generation_usd)

        self._allow_paid_generation = allow_paid_generation
        self._cost_per_generation_usd = cost_per_generation_usd
        self._output_dir = output_dir
        self._client = client

    @property
    def engine_name(self) -> str:
        return "openai-reference-image"

    def estimate_cost_usd(self, request: VisualRequest) -> float | None:
        del request
        return self._cost_per_generation_usd

    def generate_with_references(
        self,
        request: VisualRequest,
        references: tuple[ReferenceAsset, ...],
    ) -> VisualResult:
        if not self._allow_paid_generation:
            raise RuntimeError(
                "paid reference-image generation is disabled; explicit "
                "authorization is required"
            )
        if request.asset_kind != "image":
            return self._failure(
                request,
                "OpenAIReferenceVisualGenerator only supports image requests",
                provider_called=False,
            )
        if not references:
            return self._failure(
                request,
                "reference-aware generation requires at least one "
                "ReferenceAsset",
                provider_called=False,
            )

        try:
            content = [
                {
                    "type": "input_text",
                    "text": self._prompt_text(request),
                }
            ]
            content.extend(
                self._reference_content(reference)
                for reference in references
            )
        except (OSError, ValueError) as exc:
            return self._failure(
                request,
                f"reference preparation failed: {type(exc).__name__}: {exc}",
                provider_called=False,
            )

        client = self._client or OpenAI()
        provider_called = False
        try:
            provider_called = True
            response = client.responses.create(
                model=self._response_model,
                input=[
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                tools=[
                    {
                        "type": "image_generation",
                        "model": self._image_model,
                    }
                ],
            )
        except Exception as exc:
            return self._failure(
                request,
                f"OpenAI reference generation failed: "
                f"{type(exc).__name__}: {exc}",
                provider_called=provider_called,
            )

        image_base64 = self._first_image_result(response)
        if not image_base64:
            return self._failure(
                request,
                "OpenAI response did not contain an image_generation_call "
                "result",
                provider_called=True,
            )

        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
            path, width, height = self._save_png(
                request.request_id,
                image_bytes,
            )
        except (ValueError, OSError, UnidentifiedImageError) as exc:
            return self._failure(
                request,
                f"OpenAI image result could not be persisted: "
                f"{type(exc).__name__}: {exc}",
                provider_called=True,
            )

        artifact = VisualArtifact(
            asset_id=f"{request.request_id}.reference",
            request_id=request.request_id,
            shot_id=request.shot_id,
            asset_kind="image",
            uri=path,
            engine=self.engine_name,
            provider="openai",
            width=width,
            height=height,
            duration_seconds=request.duration_seconds,
            metadata={
                "response_model": self._response_model,
                "image_model": self._image_model,
                "reference_asset_ids": [
                    reference.reference_asset_id
                    for reference in references
                ],
                "response_id": str(
                    self._field(response, "id") or ""
                ),
            },
        )
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=True,
            artifacts=(artifact,),
            cost_usd=self._cost_per_generation_usd,
            metadata={
                "reference_count": len(references),
                "paid_generation_authorized": True,
            },
        )

    def _prompt_text(self, request: VisualRequest) -> str:
        prompt = request.prompt
        if request.negative_constraints:
            prompt += "\nAvoid: " + "; ".join(request.negative_constraints)
        prompt += (
            "\nUse the supplied images as visual references. Preserve the "
            "identity, distinguishing features, wardrobe, and world continuity "
            "described in the prompt while composing the requested new scene."
        )
        return prompt

    def _reference_content(
        self,
        reference: ReferenceAsset,
    ) -> dict[str, str]:
        uri = reference.uri.strip()
        if uri.startswith(("https://", "http://")):
            return {
                "type": "input_image",
                "image_url": uri,
            }
        if uri.startswith("openai-file://"):
            file_id = uri.removeprefix("openai-file://").strip()
            if not file_id:
                raise ValueError("openai-file reference is missing file id")
            return {
                "type": "input_image",
                "file_id": file_id,
            }

        path = self._local_path(uri)
        if not path.is_file():
            raise ValueError(
                f"local reference image does not exist: {path}"
            )
        data = path.read_bytes()
        media_type = (
            reference.media_type
            or mimetypes.guess_type(path.name)[0]
            or "image/png"
        )
        encoded = base64.b64encode(data).decode("ascii")
        return {
            "type": "input_image",
            "image_url": f"data:{media_type};base64,{encoded}",
        }

    @staticmethod
    def _local_path(uri: str) -> Path:
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            path = unquote(parsed.path)
            if os.name == "nt" and path.startswith("/") and len(path) > 2:
                path = path[1:]
            return Path(path)
        return Path(uri)

    def _save_png(
        self,
        request_id: str,
        image_bytes: bytes,
    ) -> tuple[str, int, int]:
        output_dir = Path(self._output_dir or "generated/visuals")
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{request_id}-{uuid.uuid4().hex[:12]}.png"
        )
        output_path = output_dir / filename

        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                image = image.convert("RGB")
            width, height = image.size
            image.save(output_path, format="PNG")

        return str(output_path), width, height

    @staticmethod
    def _first_image_result(response: Any) -> str | None:
        output = OpenAIReferenceVisualGenerator._field(response, "output")
        if not isinstance(output, (list, tuple)):
            return None
        for item in output:
            if OpenAIReferenceVisualGenerator._field(
                item,
                "type",
            ) != "image_generation_call":
                continue
            result = OpenAIReferenceVisualGenerator._field(item, "result")
            if isinstance(result, str) and result:
                return result
        return None

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(name)
        return getattr(value, name, None)

    def _failure(
        self,
        request: VisualRequest,
        error: str,
        *,
        provider_called: bool,
    ) -> VisualResult:
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=False,
            error=error,
            cost_usd=(
                self._cost_per_generation_usd
                if provider_called
                else 0.0
            ),
            metadata={
                "provider_called": provider_called,
            },
        )

    @staticmethod
    def _require_text(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
        return value.strip()
