"""Anti-corruption adapter for MoneyPrinterTurbo.

This is intentionally the only Content Studio extension that imports MoneyPrinterTurbo
implementation modules directly.
"""

from __future__ import annotations

from typing import Any

from app.models.schema import VideoParams
from app.services import task as mpt_task
from app.services import upload_post

from extensions.content_studio.rendering import (
    ExecutionRequest,
    ExecutionResult,
    RenderingEngine,
)


class MPTAdapter(RenderingEngine):
    """Translate provider-neutral Content Studio requests into MPT tasks."""

    @property
    def engine_name(self) -> str:
        return "moneyprinterturbo"

    def render(self, request: ExecutionRequest) -> ExecutionResult:
        # Content Studio owns publishing approval. Never allow an engine-level
        # auto-upload configuration to bypass Safety/QA/Human Review.
        if (
            upload_post.upload_post_service.is_configured()
            and upload_post.upload_post_service.auto_upload
        ):
            raise RuntimeError(
                "MoneyPrinterTurbo auto-upload must be disabled when invoked "
                "through Content Studio AI"
            )

        params_payload: dict[str, Any] = dict(request.options)
        params_payload.setdefault("video_subject", request.subject)
        if request.script:
            params_payload.setdefault("video_script", request.script)

        params = VideoParams(**params_payload)
        raw_result = mpt_task.start(
            task_id=request.request_id,
            params=params,
            stop_at=request.stop_at,
        )

        if not isinstance(raw_result, dict):
            return ExecutionResult(
                request_id=request.request_id,
                engine=self.engine_name,
                success=False,
                error="MoneyPrinterTurbo returned a non-dictionary result",
            )

        error = raw_result.get("error")
        videos = raw_result.get("videos") or []
        artifact_values = [
            *videos,
            raw_result.get("audio_file"),
            raw_result.get("subtitle_path"),
        ]
        artifacts = tuple(
            str(item) for item in artifact_values if isinstance(item, str) and item
        )

        success = error in (None, "")
        if request.stop_at == "video":
            success = success and bool(videos)

        return ExecutionResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=success,
            artifacts=artifacts,
            metadata=raw_result,
            error=str(error) if error else None,
        )
