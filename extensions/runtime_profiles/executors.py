"""EpisodeStageExecutor wiring for runtime-selected providers."""

from __future__ import annotations

from pathlib import Path
from extensions.content_studio.consistency import (
    ReferenceAwareVisualGenerator,
    ReferenceCatalog,
)
from extensions.content_studio.domain import DomainValidationError, ProjectSpec
from extensions.content_studio.media import (
    MediaAssemblyPlan,
    assemble_media,
    build_media_assembly_plan,
)
from extensions.content_studio.orchestration import (
    EpisodeStageExecutor,
    EpisodeWorkflowState,
    StageExecutionResult,
    WorkflowArtifact,
)
from extensions.content_studio.prompting import PromptPlan
from extensions.content_studio.runtime import (
    CAP_VISUAL_IMAGE,
    CAP_VISUAL_REFERENCE_IMAGE,
    RuntimeProfile,
    RuntimeProviderBinding,
    SecretAvailability,
    require_capability,
)
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.visual_generation import (
    VisualGenerationPlan,
    VisualGenerationReport,
    VisualResult,
    build_visual_generation_plan,
    generate_visuals,
)
from extensions.runtime_profiles.registry import RuntimeProviderRegistry


def _remaining_budget(
    state: EpisodeWorkflowState,
    binding: RuntimeProviderBinding,
) -> float | None:
    ceilings = []
    if state.max_cost_usd is not None:
        ceilings.append(max(0.0, state.max_cost_usd - state.spent_cost_usd))
    if binding.max_stage_cost_usd is not None:
        ceilings.append(binding.max_stage_cost_usd)
    return min(ceilings) if ceilings else None


class RuntimeVisualStageExecutor(EpisodeStageExecutor):
    def __init__(
        self,
        profile: RuntimeProfile,
        registry: RuntimeProviderRegistry,
        secrets: SecretAvailability,
    ) -> None:
        self._profile = profile
        self._registry = registry
        self._secrets = secrets

    @property
    def stage_name(self) -> str:
        return "visuals"

    def _binding(self) -> RuntimeProviderBinding:
        return self._profile.provider_for_stage(self.stage_name)

    def _plan(self, state: EpisodeWorkflowState) -> VisualGenerationPlan:
        project = state.require_one("ProjectSpec")
        prompts = state.require_one("PromptPlan")
        if not isinstance(project, ProjectSpec):
            raise DomainValidationError("ProjectSpec artifact is invalid")
        if not isinstance(prompts, PromptPlan):
            raise DomainValidationError("PromptPlan artifact is invalid")
        return build_visual_generation_plan(prompts, project)

    def estimate_cost_usd(
        self,
        state: EpisodeWorkflowState,
    ) -> float | None:
        binding = self._binding()
        generator = self._registry.build_visual_generator(
            binding,
            self._secrets,
        )
        plan = self._plan(state)
        estimates = []
        for request in plan.requests:
            estimate = generator.estimate_cost_usd(request)
            if estimate is None:
                return None
            estimates.append(float(estimate))
        return sum(estimates)

    def execute(
        self,
        state: EpisodeWorkflowState,
        execution_key: str,
    ) -> StageExecutionResult:
        binding = self._binding()
        if not binding.external_calls_enabled:
            return StageExecutionResult(
                stage=self.stage_name,
                status="BLOCKED",
                error=(
                    f"runtime provider {binding.provider_id!r} has "
                    "external_calls_enabled=False"
                ),
                cost_usd=0.0,
                metadata={
                    "runtime_profile": self._profile.profile_id,
                    "provider_id": binding.provider_id,
                    "execution_key": execution_key,
                    "provider_called": False,
                },
            )

        descriptor = self._registry.validate_binding(
            binding,
            self._secrets,
        )
        if (
            descriptor.paid_authorization_required
            and not binding.paid_calls_enabled
        ):
            return StageExecutionResult(
                stage=self.stage_name,
                status="BLOCKED",
                error=(
                    f"runtime provider {binding.provider_id!r} requires "
                    "paid_calls_enabled=True"
                ),
                cost_usd=0.0,
                metadata={
                    "runtime_profile": self._profile.profile_id,
                    "provider_id": binding.provider_id,
                    "execution_key": execution_key,
                    "provider_called": False,
                },
            )

        generator = self._registry.build_visual_generator(
            binding,
            self._secrets,
        )
        plan = self._plan(state)
        has_references = any(
            request.reference_asset_ids for request in plan.requests
        )

        try:
            if has_references:
                require_capability(
                    binding,
                    CAP_VISUAL_REFERENCE_IMAGE,
                )
                if not isinstance(
                    generator,
                    ReferenceAwareVisualGenerator,
                ):
                    raise DomainValidationError(
                        "reference-aware visual plan requires a "
                        "ReferenceAwareVisualGenerator"
                    )
                report = self._generate_references(
                    generator,
                    plan,
                    binding,
                )
            else:
                require_capability(binding, CAP_VISUAL_IMAGE)
                report = generate_visuals(
                    generator,
                    plan,
                    max_cost_usd=_remaining_budget(state, binding),
                    fail_fast=True,
                )
        except Exception as exc:
            return StageExecutionResult(
                stage=self.stage_name,
                status="FAIL",
                error=f"{type(exc).__name__}: {exc}",
                cost_usd=0.0,
                metadata={
                    "runtime_profile": self._profile.profile_id,
                    "provider_id": binding.provider_id,
                    "execution_key": execution_key,
                },
            )

        status = "PASS" if report.success else "FAIL"
        error = None
        if not report.success:
            errors = [
                item.error or "visual generation failed"
                for item in report.results
                if not item.success
            ]
            error = "; ".join(errors) or "visual generation failed"
        cost = report.known_cost_usd if report.cost_complete else None
        return StageExecutionResult(
            stage=self.stage_name,
            status=status,
            artifacts=(
                WorkflowArtifact.from_contract(
                    f"{execution_key}-visual-plan",
                    plan,
                ),
                WorkflowArtifact.from_contract(
                    f"{execution_key}-visual-report",
                    report,
                ),
            ),
            cost_usd=cost,
            error=error,
            metadata={
                "runtime_profile": self._profile.profile_id,
                "provider_id": binding.provider_id,
                "adapter": binding.adapter,
                "execution_key": execution_key,
                "external_calls_enabled": binding.external_calls_enabled,
                "paid_calls_enabled": binding.paid_calls_enabled,
            },
        )

    def _generate_references(
        self,
        generator: ReferenceAwareVisualGenerator,
        plan: VisualGenerationPlan,
        binding: RuntimeProviderBinding,
    ) -> VisualGenerationReport:
        path = str(binding.options["reference_catalog_path"])
        catalog = ReferenceCatalog.from_json(
            Path(path).read_text(encoding="utf-8")
        )
        if catalog.project_id != plan.project_id:
            raise DomainValidationError(
                "ReferenceCatalog project_id does not match visual plan"
            )

        budget = binding.max_stage_cost_usd
        estimates = []
        for request in plan.requests:
            estimate = generator.estimate_cost_usd(request)
            if estimate is None and budget is not None:
                raise DomainValidationError(
                    "cost estimate required before budget-controlled "
                    "reference generation"
                )
            estimates.append(estimate)
        if budget is not None:
            projected = sum(float(item) for item in estimates if item is not None)
            if projected > budget:
                raise DomainValidationError(
                    "projected reference generation cost exceeds "
                    "max_stage_cost_usd"
                )

        results: list[VisualResult] = []
        for request in plan.requests:
            if not request.reference_asset_ids:
                raise DomainValidationError(
                    "openai-reference-image profile cannot silently handle "
                    "a request without reference_asset_ids"
                )
            references = catalog.resolve_many(request.reference_asset_ids)
            result = generator.generate_with_references(
                request,
                references,
            )
            results.append(result)
            if not result.success:
                break

        report = VisualGenerationReport(
            project_id=plan.project_id,
            story_id=plan.story_id,
            episode_id=plan.episode_id,
            results=tuple(results),
            metadata={
                "engine": generator.engine_name,
                "reference_catalog_path": path,
            },
        )
        if len(results) == len(plan.requests):
            report.validate_plan(plan)
        return report


class RuntimeMediaStageExecutor(EpisodeStageExecutor):
    def __init__(
        self,
        profile: RuntimeProfile,
        registry: RuntimeProviderRegistry,
        secrets: SecretAvailability,
    ) -> None:
        self._profile = profile
        self._registry = registry
        self._secrets = secrets

    @property
    def stage_name(self) -> str:
        return "media"

    def _binding(self) -> RuntimeProviderBinding:
        return self._profile.provider_for_stage(self.stage_name)

    def _plan(
        self,
        state: EpisodeWorkflowState,
        binding: RuntimeProviderBinding,
    ) -> MediaAssemblyPlan:
        project = state.require_one("ProjectSpec")
        consistency = state.require_one("ConsistencyReport")
        story = state.require_one("StoryPlan")
        if not isinstance(project, ProjectSpec):
            raise DomainValidationError("ProjectSpec artifact is invalid")
        if not isinstance(story, StoryPlan):
            raise DomainValidationError("StoryPlan artifact is invalid")

        options = dict(binding.options)
        script = "\n".join(
            beat.dialogue_hint or beat.summary
            for beat in story.beats
        )
        template = str(options["output_uri_template"])
        output_uri = template.format(
            workflow_id=state.workflow_id,
            project_id=state.project_id,
            episode_id=state.episode_id,
            revision=state.revision,
        )
        return build_media_assembly_plan(
            project,
            consistency,
            assembly_id=(
                f"{state.workflow_id}-r{state.revision}-media"
            ),
            script=script,
            language=project.language,
            voice_name=str(options["voice_name"]),
            output_uri=output_uri,
            subtitle_enabled=bool(
                options.get("subtitle_enabled", True)
            ),
        )

    def estimate_cost_usd(
        self,
        state: EpisodeWorkflowState,
    ) -> float | None:
        binding = self._binding()
        assembler = self._registry.build_media_assembler(
            binding,
            self._secrets,
        )
        return assembler.estimate_cost_usd(
            self._plan(state, binding)
        )

    def execute(
        self,
        state: EpisodeWorkflowState,
        execution_key: str,
    ) -> StageExecutionResult:
        binding = self._binding()
        if not binding.external_calls_enabled:
            return StageExecutionResult(
                stage=self.stage_name,
                status="BLOCKED",
                error=(
                    f"runtime provider {binding.provider_id!r} has "
                    "external_calls_enabled=False"
                ),
                cost_usd=0.0,
                metadata={
                    "runtime_profile": self._profile.profile_id,
                    "provider_id": binding.provider_id,
                    "execution_key": execution_key,
                    "provider_called": False,
                },
            )
        try:
            assembler = self._registry.build_media_assembler(
                binding,
                self._secrets,
            )
            plan = self._plan(state, binding)
            result = assemble_media(
                assembler,
                plan,
                max_cost_usd=_remaining_budget(state, binding),
            )
        except Exception as exc:
            return StageExecutionResult(
                stage=self.stage_name,
                status="FAIL",
                error=f"{type(exc).__name__}: {exc}",
                cost_usd=0.0,
                metadata={
                    "runtime_profile": self._profile.profile_id,
                    "provider_id": binding.provider_id,
                    "execution_key": execution_key,
                },
            )

        return StageExecutionResult(
            stage=self.stage_name,
            status="PASS" if result.success else "FAIL",
            artifacts=(
                WorkflowArtifact.from_contract(
                    f"{execution_key}-media-plan",
                    plan,
                ),
                WorkflowArtifact.from_contract(
                    f"{execution_key}-media-result",
                    result,
                ),
            ),
            cost_usd=result.cost_usd,
            error=None if result.success else result.error,
            metadata={
                "runtime_profile": self._profile.profile_id,
                "provider_id": binding.provider_id,
                "adapter": binding.adapter,
                "execution_key": execution_key,
                "external_calls_enabled": binding.external_calls_enabled,
            },
        )


class RuntimeExecutorFactory:
    """Create only the provider-backed stage executors declared by a profile."""

    def __init__(
        self,
        registry: RuntimeProviderRegistry,
        secrets: SecretAvailability,
    ) -> None:
        self._registry = registry
        self._secrets = secrets

    def build(
        self,
        profile: RuntimeProfile,
    ) -> dict[str, EpisodeStageExecutor]:
        executors: dict[str, EpisodeStageExecutor] = {}
        if "visuals" in profile.stage_bindings:
            executors["visuals"] = RuntimeVisualStageExecutor(
                profile,
                self._registry,
                self._secrets,
            )
        if "media" in profile.stage_bindings:
            executors["media"] = RuntimeMediaStageExecutor(
                profile,
                self._registry,
                self._secrets,
            )
        unsupported = sorted(
            set(profile.stage_bindings) - {"visuals", "media"}
        )
        if unsupported:
            raise DomainValidationError(
                "runtime provider executor wiring is not implemented for "
                f"stages: {unsupported}"
            )
        return executors
