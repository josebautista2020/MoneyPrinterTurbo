"""Concrete runtime adapter registry outside reusable Core."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.runtime import (
    CAP_MEDIA_ASSEMBLY,
    CAP_RENDER_GENERAL,
    CAP_VISUAL_IMAGE,
    CAP_VISUAL_REFERENCE_IMAGE,
    RuntimeProviderBinding,
    SecretAvailability,
    SecretReference,
    require_capability,
)
from extensions.mpt_adapter.adapter import MPTAdapter
from extensions.mpt_adapter.media import MPTMediaAssembler
from extensions.mpt_adapter.visual import MPTImageVisualGenerator
from extensions.openai_image_adapter.reference import (
    OpenAIReferenceVisualGenerator,
)


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    adapter: str
    capabilities: tuple[str, ...]
    allowed_options: frozenset[str]
    required_options: frozenset[str] = frozenset()
    required_secret_refs: tuple[str, ...] = ()
    paid_authorization_required: bool = False


class EnvironmentSecretAvailability(SecretAvailability):
    """Check env/file references without returning secret values."""

    def is_available(self, reference: SecretReference) -> bool:
        if reference.scheme == "env":
            return bool(os.getenv(reference.key))
        if reference.scheme == "file-ref":
            return Path(reference.key).is_file()
        # Cloud secret-manager resolution is intentionally not implicit.
        return False


class RuntimeProviderRegistry:
    """Allowlisted factories for concrete provider adapters."""

    def __init__(self) -> None:
        self._descriptors: dict[str, AdapterDescriptor] = {
            "mpt-image": AdapterDescriptor(
                adapter="mpt-image",
                capabilities=(CAP_VISUAL_IMAGE,),
                allowed_options=frozenset(
                    {"cost_per_image_usd", "save_dir"}
                ),
                paid_authorization_required=True,
            ),
            "openai-reference-image": AdapterDescriptor(
                adapter="openai-reference-image",
                capabilities=(CAP_VISUAL_REFERENCE_IMAGE,),
                allowed_options=frozenset(
                    {
                        "response_model",
                        "image_model",
                        "cost_per_generation_usd",
                        "output_dir",
                        "reference_catalog_path",
                    }
                ),
                required_options=frozenset(
                    {"response_model", "image_model", "reference_catalog_path"}
                ),
                required_secret_refs=("env:OPENAI_API_KEY",),
                paid_authorization_required=True,
            ),
            "mpt-media": AdapterDescriptor(
                adapter="mpt-media",
                capabilities=(CAP_MEDIA_ASSEMBLY,),
                allowed_options=frozenset(
                    {
                        "estimated_cost_usd",
                        "work_dir",
                        "voice_name",
                        "output_uri_template",
                        "subtitle_enabled",
                    }
                ),
                required_options=frozenset(
                    {"voice_name", "output_uri_template"}
                ),
            ),
            "mpt-render": AdapterDescriptor(
                adapter="mpt-render",
                capabilities=(CAP_RENDER_GENERAL,),
                allowed_options=frozenset(),
            ),
        }

    def descriptor(self, adapter: str) -> AdapterDescriptor:
        try:
            return self._descriptors[adapter]
        except KeyError as exc:
            raise DomainValidationError(
                f"runtime adapter is not registered: {adapter!r}"
            ) from exc

    def validate_binding(
        self,
        binding: RuntimeProviderBinding,
        secrets: SecretAvailability,
    ) -> AdapterDescriptor:
        descriptor = self.descriptor(binding.adapter)
        declared = set(binding.capabilities)
        supported = set(descriptor.capabilities)
        unsupported = sorted(declared - supported)
        if unsupported:
            raise DomainValidationError(
                f"provider {binding.provider_id!r} declares unsupported "
                f"capabilities for {binding.adapter!r}: {unsupported}"
            )

        option_keys = set(binding.options)
        unknown = sorted(option_keys - descriptor.allowed_options)
        missing = sorted(descriptor.required_options - option_keys)
        if unknown:
            raise DomainValidationError(
                f"provider {binding.provider_id!r} has unknown options: "
                f"{unknown}"
            )
        if missing:
            raise DomainValidationError(
                f"provider {binding.provider_id!r} is missing options: "
                f"{missing}"
            )

        refs = {item.reference for item in binding.secret_refs}
        missing_refs = sorted(
            set(descriptor.required_secret_refs) - refs
        )
        if binding.external_calls_enabled and missing_refs:
            raise DomainValidationError(
                f"provider {binding.provider_id!r} is missing required "
                f"secret references: {missing_refs}"
            )
        if binding.external_calls_enabled:
            unavailable = [
                item.reference
                for item in binding.secret_refs
                if not secrets.is_available(item)
            ]
            if unavailable:
                raise DomainValidationError(
                    f"provider {binding.provider_id!r} has unavailable "
                    f"secret references: {sorted(unavailable)}"
                )
        return descriptor


    @staticmethod
    def _string_option(
        options: Mapping[str, Any],
        name: str,
        *,
        default: str | None = None,
    ) -> str:
        value = options.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise DomainValidationError(
                f"runtime option {name!r} must be a non-empty string"
            )
        return value.strip()

    @staticmethod
    def _number_option(
        options: Mapping[str, Any],
        name: str,
    ) -> float | None:
        value = options.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DomainValidationError(
                f"runtime option {name!r} must be a number or null"
            )
        value = float(value)
        if value < 0:
            raise DomainValidationError(
                f"runtime option {name!r} must be non-negative"
            )
        return value

    @staticmethod
    def _bool_option(
        options: Mapping[str, Any],
        name: str,
        *,
        default: bool,
    ) -> bool:
        value = options.get(name, default)
        if not isinstance(value, bool):
            raise DomainValidationError(
                f"runtime option {name!r} must be boolean"
            )
        return value

    def validate_profile(
        self,
        profile,
        secrets: SecretAvailability,
    ) -> None:
        from extensions.content_studio.runtime import RuntimeProfile

        if not isinstance(profile, RuntimeProfile):
            raise DomainValidationError(
                "runtime profile must be a RuntimeProfile"
            )
        for binding in profile.providers:
            self.validate_binding(binding, secrets)
        for stage, provider_id in profile.stage_bindings.items():
            binding = profile.provider(provider_id)
            capabilities = set(binding.capabilities)
            if stage == "visuals":
                if not capabilities.intersection(
                    {CAP_VISUAL_IMAGE, CAP_VISUAL_REFERENCE_IMAGE}
                ):
                    raise DomainValidationError(
                        f"provider {provider_id!r} cannot serve visuals"
                    )
            elif stage == "media":
                require_capability(binding, CAP_MEDIA_ASSEMBLY)
            else:
                raise DomainValidationError(
                    "runtime executor wiring is not implemented for "
                    f"stage {stage!r}"
                )

    def build_visual_generator(
        self,
        binding: RuntimeProviderBinding,
        secrets: SecretAvailability,
    ):
        descriptor = self.validate_binding(binding, secrets)
        options = dict(binding.options)

        if descriptor.adapter == "mpt-image":
            require_capability(binding, CAP_VISUAL_IMAGE)
            return MPTImageVisualGenerator(
                allow_paid_generation=binding.paid_calls_enabled,
                cost_per_image_usd=self._number_option(
                    options,
                    "cost_per_image_usd",
                ),
                save_dir=(
                    self._string_option(
                        options,
                        "save_dir",
                        default=".",
                    )
                    if "save_dir" in options
                    else ""
                ),
            )

        if descriptor.adapter == "openai-reference-image":
            require_capability(binding, CAP_VISUAL_REFERENCE_IMAGE)
            return OpenAIReferenceVisualGenerator(
                response_model=self._string_option(
                    options,
                    "response_model",
                ),
                image_model=self._string_option(
                    options,
                    "image_model",
                ),
                allow_paid_generation=binding.paid_calls_enabled,
                cost_per_generation_usd=self._number_option(
                    options,
                    "cost_per_generation_usd",
                ),
                output_dir=(
                    self._string_option(
                        options,
                        "output_dir",
                        default=".",
                    )
                    if "output_dir" in options
                    else ""
                ),
            )

        raise DomainValidationError(
            f"adapter {binding.adapter!r} is not a visual generator"
        )

    def build_media_assembler(
        self,
        binding: RuntimeProviderBinding,
        secrets: SecretAvailability,
    ) -> MPTMediaAssembler:
        descriptor = self.validate_binding(binding, secrets)
        if descriptor.adapter != "mpt-media":
            raise DomainValidationError(
                f"adapter {binding.adapter!r} is not a media assembler"
            )
        require_capability(binding, CAP_MEDIA_ASSEMBLY)
        options = dict(binding.options)
        return MPTMediaAssembler(
            allow_external_generation=binding.external_calls_enabled,
            estimated_cost_usd=self._number_option(
                options,
                "estimated_cost_usd",
            ),
            work_dir=(
                self._string_option(
                    options,
                    "work_dir",
                    default=".",
                )
                if "work_dir" in options
                else ""
            ),
        )

    def build_rendering_engine(
        self,
        binding: RuntimeProviderBinding,
        secrets: SecretAvailability,
    ) -> MPTAdapter:
        descriptor = self.validate_binding(binding, secrets)
        if descriptor.adapter != "mpt-render":
            raise DomainValidationError(
                f"adapter {binding.adapter!r} is not a rendering engine"
            )
        require_capability(binding, CAP_RENDER_GENERAL)
        if not binding.external_calls_enabled:
            raise DomainValidationError(
                "mpt-render requires external_calls_enabled=True"
            )
        return MPTAdapter()

    def capability_matrix(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "adapter": descriptor.adapter,
                "capabilities": list(descriptor.capabilities),
                "allowed_options": sorted(descriptor.allowed_options),
                "required_options": sorted(descriptor.required_options),
                "required_secret_refs": list(
                    descriptor.required_secret_refs
                ),
                "paid_authorization_required": (
                    descriptor.paid_authorization_required
                ),
            }
            for descriptor in sorted(
                self._descriptors.values(),
                key=lambda item: item.adapter,
            )
        )
