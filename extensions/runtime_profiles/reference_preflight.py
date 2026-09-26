"""Validate every referenced image before any paid visual request starts."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, UnidentifiedImageError

from extensions.content_studio.consistency import ReferenceCatalog
from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.visual_generation import VisualGenerationPlan

MAX_REFERENCE_BYTES = 20 * 1024 * 1024


def preflight_reference_images(
    plan: VisualGenerationPlan,
    catalog: ReferenceCatalog,
) -> None:
    """Fail closed on missing, placeholder or unusable referenced images.

    Local paths use the same working-directory semantics as the OpenAI adapter.
    Remote resources cannot be checked offline and need a separate approval flow.
    """
    if catalog.project_id != plan.project_id:
        raise DomainValidationError(
            "ReferenceCatalog project_id does not match visual plan"
        )

    referenced = {
        asset_id
        for request in plan.requests
        for asset_id in request.reference_asset_ids
    }
    if not referenced:
        raise DomainValidationError(
            "reference-aware visual plan has no reference_asset_ids; "
            "bind CharacterBible and UniverseBible first"
        )
    for asset_id in sorted(referenced):
        asset = catalog.resolve(asset_id)
        if asset.metadata.get("placeholder") or catalog.metadata.get(
            "placeholder_uris"
        ):
            raise DomainValidationError(
                f"reference {asset_id!r} is a placeholder; supply an "
                "approved local image before paid generation"
            )
        if asset.media_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise DomainValidationError(
                f"reference {asset_id!r} has unsupported media_type"
            )
        uri = asset.uri.strip()
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            if parsed.netloc not in {"", "localhost"}:
                raise DomainValidationError(
                    f"reference {asset_id!r} has a non-local file URI"
                )
            raw_path = unquote(parsed.path)
            if os.name == "nt" and raw_path.startswith("/"):
                raw_path = raw_path[1:]
            path = Path(raw_path)
        elif "://" in uri:
            raise DomainValidationError(
                f"reference {asset_id!r} is not a verifiable local image"
            )
        else:
            path = Path(uri)

        if not path.is_file():
            raise DomainValidationError(
                f"reference {asset_id!r} image does not exist: {path}"
            )
        if not 0 < path.stat().st_size <= MAX_REFERENCE_BYTES:
            raise DomainValidationError(
                f"reference {asset_id!r} image must be nonempty and at most 20 MiB"
            )
        try:
            with Image.open(path) as image:
                image.verify()
                actual = Image.MIME.get(image.format)
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise DomainValidationError(
                f"reference {asset_id!r} is not a readable image"
            ) from exc
        if actual != asset.media_type:
            raise DomainValidationError(
                f"reference {asset_id!r} media_type does not match image"
            )
