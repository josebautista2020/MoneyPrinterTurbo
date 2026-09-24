"""Provider-neutral runtime profile contracts for Content Studio AI."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from extensions.content_studio.domain import (
    DomainValidationError,
    JsonContract,
    SCHEMA_VERSION,
)
from extensions.content_studio.orchestration import WORKFLOW_STAGES

_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_ADAPTER_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_SENSITIVE_TOKENS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "private_key",
    "client_secret",
)

CAP_VISUAL_IMAGE = "visual.image"
CAP_VISUAL_REFERENCE_IMAGE = "visual.image.reference"
CAP_MEDIA_ASSEMBLY = "media.assembly"
CAP_RENDER_GENERAL = "render.general"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _id(value: str, name: str) -> str:
    value = _text(value, name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise DomainValidationError(f"{name} has invalid identifier")
    return value


def _metadata(value: Mapping[str, Any], *, allow_sensitive_keys: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainValidationError("mapping value expected")
    try:
        decoded = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("mapping must be JSON-compatible") from exc
    if not isinstance(decoded, dict):
        raise DomainValidationError("mapping must serialize to an object")
    if not allow_sensitive_keys:
        _reject_sensitive_keys(decoded)
    return decoded


def _reject_sensitive_keys(value: Any, path: str = "options") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in _SENSITIVE_TOKENS):
                raise DomainValidationError(
                    f"sensitive value must use SecretReference, not {path}.{key}"
                )
            _reject_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_keys(nested, f"{path}[{index}]")


def _payload(payload: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainValidationError("payload must be a mapping")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DomainValidationError("unsupported schema_version")
    data = dict(payload)
    data.pop("schema_version", None)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DomainValidationError(f"unknown fields: {unknown}")
    return data


def _optional_cost(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise DomainValidationError(
            f"{name} must be a non-negative finite number or null"
        )
    return float(value)


@dataclass(frozen=True, slots=True)
class SecretReference(JsonContract):
    """Reference to a secret source; never the secret value itself."""

    scheme: str
    key: str

    def __post_init__(self) -> None:
        scheme = _text(self.scheme, "scheme").lower()
        if scheme not in {"env", "secret-manager", "file-ref"}:
            raise DomainValidationError(
                "secret scheme must be env, secret-manager, or file-ref"
            )
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "key", _text(self.key, "key"))
        if self.scheme == "env" and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*",
            self.key,
        ):
            raise DomainValidationError("env secret key has invalid name")

    @property
    def reference(self) -> str:
        return f"{self.scheme}:{self.key}"

    @classmethod
    def parse(cls, value: str) -> "SecretReference":
        value = _text(value, "secret reference")
        scheme, separator, key = value.partition(":")
        if not separator:
            raise DomainValidationError(
                "secret reference must use scheme:key notation"
            )
        return cls(scheme=scheme, key=key)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(payload, {"scheme", "key"})
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RuntimeProviderBinding(JsonContract):
    """One adapter declaration inside a runtime profile."""

    provider_id: str
    adapter: str
    capabilities: tuple[str, ...]
    secret_refs: tuple[SecretReference, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)
    external_calls_enabled: bool = False
    paid_calls_enabled: bool = False
    max_stage_cost_usd: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _id(self.provider_id, "provider_id"),
        )
        adapter = _text(self.adapter, "adapter").lower()
        if not _ADAPTER_RE.fullmatch(adapter):
            raise DomainValidationError("adapter has invalid identifier")
        object.__setattr__(self, "adapter", adapter)

        capabilities = tuple(self.capabilities)
        if not capabilities:
            raise DomainValidationError(
                "capabilities must contain at least one capability"
            )
        normalized = []
        for capability in capabilities:
            capability = _text(capability, "capability").lower()
            if not _CAPABILITY_RE.fullmatch(capability):
                raise DomainValidationError(
                    f"invalid capability: {capability!r}"
                )
            normalized.append(capability)
        if len(normalized) != len(set(normalized)):
            raise DomainValidationError("capabilities must be unique")
        object.__setattr__(self, "capabilities", tuple(normalized))

        refs = tuple(self.secret_refs)
        if not all(isinstance(item, SecretReference) for item in refs):
            raise DomainValidationError(
                "secret_refs must contain SecretReference values"
            )
        references = [item.reference for item in refs]
        if len(references) != len(set(references)):
            raise DomainValidationError("secret_refs must be unique")
        object.__setattr__(self, "secret_refs", refs)

        for name in ("external_calls_enabled", "paid_calls_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        if self.paid_calls_enabled and not self.external_calls_enabled:
            raise DomainValidationError(
                "paid_calls_enabled requires external_calls_enabled"
            )
        object.__setattr__(
            self,
            "max_stage_cost_usd",
            _optional_cost(self.max_stage_cost_usd, "max_stage_cost_usd"),
        )
        object.__setattr__(self, "options", _metadata(self.options))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["secret_refs"] = [item.to_dict() for item in self.secret_refs]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {
                "provider_id",
                "adapter",
                "capabilities",
                "secret_refs",
                "options",
                "external_calls_enabled",
                "paid_calls_enabled",
                "max_stage_cost_usd",
                "metadata",
            },
        )
        data["capabilities"] = tuple(data.get("capabilities", ()))
        data["secret_refs"] = tuple(
            SecretReference.from_dict(item)
            for item in data.get("secret_refs", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RuntimeProfile(JsonContract):
    """Serializable runtime selection with no secret values."""

    profile_id: str
    providers: tuple[RuntimeProviderBinding, ...] = ()
    stage_bindings: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _id(self.profile_id, "profile_id"),
        )
        providers = tuple(self.providers)
        if not all(isinstance(item, RuntimeProviderBinding) for item in providers):
            raise DomainValidationError(
                "providers must contain RuntimeProviderBinding values"
            )
        ids = [item.provider_id for item in providers]
        if len(ids) != len(set(ids)):
            raise DomainValidationError("provider_id values must be unique")
        object.__setattr__(self, "providers", providers)

        if not isinstance(self.stage_bindings, Mapping):
            raise DomainValidationError("stage_bindings must be a mapping")
        bindings = {}
        known = set(ids)
        for stage, provider_id in self.stage_bindings.items():
            if stage not in WORKFLOW_STAGES:
                raise DomainValidationError(
                    f"unsupported stage binding: {stage!r}"
                )
            provider_id = _id(provider_id, "stage binding provider_id")
            if provider_id not in known:
                raise DomainValidationError(
                    f"stage {stage!r} references unknown provider "
                    f"{provider_id!r}"
                )
            bindings[str(stage)] = provider_id
        object.__setattr__(self, "stage_bindings", bindings)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def provider(self, provider_id: str) -> RuntimeProviderBinding:
        matches = [
            item for item in self.providers if item.provider_id == provider_id
        ]
        if len(matches) != 1:
            raise DomainValidationError(
                f"runtime provider not found: {provider_id!r}"
            )
        return matches[0]

    def provider_for_stage(self, stage: str) -> RuntimeProviderBinding:
        if stage not in WORKFLOW_STAGES:
            raise DomainValidationError(f"unsupported stage: {stage!r}")
        provider_id = self.stage_bindings.get(stage)
        if provider_id is None:
            raise DomainValidationError(
                f"runtime profile has no provider binding for stage {stage!r}"
            )
        return self.provider(provider_id)

    def capability_matrix(self) -> tuple[dict[str, Any], ...]:
        stages_by_provider: dict[str, list[str]] = {
            provider.provider_id: [] for provider in self.providers
        }
        for stage, provider_id in self.stage_bindings.items():
            stages_by_provider[provider_id].append(stage)
        return tuple(
            {
                "provider_id": provider.provider_id,
                "adapter": provider.adapter,
                "capabilities": list(provider.capabilities),
                "stages": sorted(stages_by_provider[provider.provider_id]),
                "external_calls_enabled": provider.external_calls_enabled,
                "paid_calls_enabled": provider.paid_calls_enabled,
                "max_stage_cost_usd": provider.max_stage_cost_usd,
                "secret_refs": [
                    item.reference for item in provider.secret_refs
                ],
            }
            for provider in self.providers
        )

    def to_dict(self) -> dict[str, Any]:
        payload = JsonContract.to_dict(self)
        payload["providers"] = [item.to_dict() for item in self.providers]
        payload["stage_bindings"] = dict(self.stage_bindings)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _payload(
            payload,
            {"profile_id", "providers", "stage_bindings", "metadata"},
        )
        data["providers"] = tuple(
            RuntimeProviderBinding.from_dict(item)
            for item in data.get("providers", ())
        )
        try:
            return cls(**data)
        except TypeError as exc:
            raise DomainValidationError(str(exc)) from exc


@runtime_checkable
class SecretAvailability(Protocol):
    """Check only whether a reference is available, not its value."""

    def is_available(self, reference: SecretReference) -> bool:
        ...


def validate_runtime_secrets(
    profile: RuntimeProfile,
    secrets: SecretAvailability,
) -> None:
    missing = []
    for provider in profile.providers:
        if not provider.external_calls_enabled:
            continue
        for reference in provider.secret_refs:
            if not secrets.is_available(reference):
                missing.append(
                    f"{provider.provider_id}:{reference.reference}"
                )
    if missing:
        raise DomainValidationError(
            "runtime profile has unavailable secret references: "
            + ", ".join(sorted(missing))
        )


def require_capability(
    provider: RuntimeProviderBinding,
    capability: str,
) -> None:
    capability = _text(capability, "capability").lower()
    if capability not in provider.capabilities:
        raise DomainValidationError(
            f"provider {provider.provider_id!r} lacks required "
            f"capability {capability!r}"
        )
