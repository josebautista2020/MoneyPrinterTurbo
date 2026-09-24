"""MoneyPrinterTurbo / Upload-Post publishing adapter."""

from __future__ import annotations

import os

from app.services.upload_post import upload_post_service

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.publishing import (
    PublishRequest,
    PublishResult,
    Publisher,
    PublishTargetResult,
)


class MPTUploadPostPublisher(Publisher):
    """Explicit live-publish adapter over MoneyPrinterTurbo Upload-Post."""

    def __init__(
        self,
        *,
        allow_live_publish: bool = False,
    ) -> None:
        self._allow_live_publish = allow_live_publish

    @property
    def publisher_name(self) -> str:
        return "moneyprinterturbo-upload-post"

    def publish(self, request: PublishRequest) -> PublishResult:
        if request.dry_run:
            return PublishResult(
                request_id=request.request_id,
                publisher=self.publisher_name,
                success=True,
                dry_run=True,
                outcomes=tuple(
                    PublishTargetResult(
                        platform=target.platform,
                        account_ref=target.account_ref,
                        success=True,
                        metadata={
                            "validation_only": True,
                            "network_called": False,
                        },
                    )
                    for target in request.targets
                ),
                metadata={
                    "network_called": False,
                    "publication_performed": False,
                },
            )

        if not self._allow_live_publish:
            raise RuntimeError(
                "live publishing is disabled; explicit adapter authorization "
                "is required"
            )

        if not upload_post_service.is_configured():
            return self._failure(
                request,
                "Upload-Post is not configured or enabled",
                network_called=False,
            )
        if not os.path.isfile(request.video_uri):
            return self._failure(
                request,
                f"approved render does not exist: {request.video_uri}",
                network_called=False,
            )

        configured_account = upload_post_service.username
        accounts = {target.account_ref for target in request.targets}
        if accounts != {configured_account}:
            raise DomainValidationError(
                "PublishTarget account_ref must match configured "
                "Upload-Post username"
            )

        privacy_levels = {
            target.privacy_level for target in request.targets
        }
        if len(privacy_levels) != 1:
            raise DomainValidationError(
                "Upload-Post adapter requires one shared privacy_level "
                "per request"
            )

        youtube_targets = [
            target for target in request.targets if target.is_youtube
        ]
        youtube_extra = None
        if youtube_targets:
            audiences = {
                target.youtube_made_for_kids for target in youtube_targets
            }
            if None in audiences or len(audiences) != 1:
                raise DomainValidationError(
                    "YouTube targets require one explicit made-for-kids "
                    "declaration"
                )
            privacy_statuses = {
                target.youtube_privacy_status or "public"
                for target in youtube_targets
            }
            if len(privacy_statuses) != 1:
                raise DomainValidationError(
                    "YouTube targets require one shared privacyStatus"
                )
            youtube_extra = {
                "selfDeclaredMadeForKids": audiences.pop(),
                "youtube_title": request.title,
                "youtube_description": request.description,
                "tags": list(request.tags),
                "privacyStatus": privacy_statuses.pop(),
            }

        response = upload_post_service.upload_video(
            video_path=request.video_uri,
            title=request.title,
            platforms=[target.platform for target in request.targets],
            privacy_level=next(iter(privacy_levels)),
            youtube_extra=youtube_extra,
        )
        if not isinstance(response, dict):
            return self._failure(
                request,
                "Upload-Post returned a non-dict response",
                network_called=True,
            )

        success = bool(response.get("success"))
        external_request_id = response.get("request_id")
        error = None if success else str(
            response.get("error")
            or response.get("message")
            or "Upload-Post publish failed"
        )
        outcomes = tuple(
            PublishTargetResult(
                platform=target.platform,
                account_ref=target.account_ref,
                success=success,
                external_request_id=(
                    str(external_request_id)
                    if external_request_id
                    else None
                ),
                error=error,
                metadata={
                    "provider": "upload-post",
                },
            )
            for target in request.targets
        )
        return PublishResult(
            request_id=request.request_id,
            publisher=self.publisher_name,
            success=success,
            dry_run=False,
            outcomes=outcomes,
            error=error,
            metadata={
                "network_called": True,
                "publication_performed": success,
                "external_request_id": (
                    str(external_request_id)
                    if external_request_id
                    else None
                ),
            },
        )

    def _failure(
        self,
        request: PublishRequest,
        error: str,
        *,
        network_called: bool,
    ) -> PublishResult:
        return PublishResult(
            request_id=request.request_id,
            publisher=self.publisher_name,
            success=False,
            dry_run=False,
            outcomes=tuple(
                PublishTargetResult(
                    platform=target.platform,
                    account_ref=target.account_ref,
                    success=False,
                    error=error,
                )
                for target in request.targets
            ),
            error=error,
            metadata={
                "network_called": network_called,
                "publication_performed": False,
            },
        )
