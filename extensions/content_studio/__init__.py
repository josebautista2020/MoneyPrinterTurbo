"""Reusable Content Studio AI core.

This package must remain vertical-agnostic. Vertical-specific behavior belongs under
``verticals/`` and integrations with MoneyPrinterTurbo belong behind adapters.
"""

from extensions.content_studio.domain import (
    CharacterSpec,
    DomainValidationError,
    EpisodeSpec,
    ProjectSpec,
    SCHEMA_VERSION,
    SceneSpec,
)

__all__ = [
    "CharacterSpec",
    "DomainValidationError",
    "EpisodeSpec",
    "ProjectSpec",
    "SCHEMA_VERSION",
    "SceneSpec",
]
