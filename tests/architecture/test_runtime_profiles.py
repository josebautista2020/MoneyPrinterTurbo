"""Runtime profile contracts, registry and provider executor wiring tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from extensions.content_studio.consistency import (
    ConsistencyAssessment,
    ConsistencyAttempt,
    ConsistencyReport,
    ConsistentVisualResult,
)
from extensions.content_studio.bibles import CharacterBible, UniverseBible
from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)
from extensions.content_studio.media import (
    AudioArtifact,
    MediaAssemblyResult,
    RenderArtifact,
    SubtitleArtifact,
)
from extensions.content_studio.orchestration import (
    EpisodeWorkflowState,
    WorkflowArtifact,
    WorkflowStageRecord,
)
from extensions.content_studio.prompting import PromptPlan
from extensions.content_studio.runtime import (
    CAP_MEDIA_ASSEMBLY,
    CAP_VISUAL_IMAGE,
    CAP_VISUAL_REFERENCE_IMAGE,
    RuntimeProfile,
    RuntimeProviderBinding,
    SecretReference,
)
from extensions.content_studio.story import StoryPlan
from extensions.content_studio.visual_generation import (
    VisualArtifact,
    VisualGenerationPlan,
    VisualResult,
)
from extensions.operator_console.cli import main as cli_main
from extensions.operator_console.service import OperatorConsoleService
from extensions.runtime_profiles import (
    EnvironmentSecretAvailability,
    RuntimeExecutorFactory,
    RuntimeMediaStageExecutor,
    RuntimeProviderRegistry,
    RuntimeVisualStageExecutor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "extensions" / "content_studio" / "examples"
PROFILES = REPO_ROOT / "extensions" / "runtime_profiles" / "profiles"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _project_episode_2() -> ProjectSpec:
    base = ProjectSpec.from_json(_load(EXAMPLES / "generic_project.json"))
    story = StoryPlan.from_json(_load(EXAMPLES / "generic_story_plan.json"))
    episode = story.to_episode_spec()
    return ProjectSpec(
        project_id=base.project_id,
        title=base.title,
        language=base.language,
        target_platforms=base.target_platforms,
        aspect_ratio=base.aspect_ratio,
        resolution=base.resolution,
        characters=base.characters,
        episodes=(episode,),
        metadata={"runtime_test": True},
    )


def _record(
    stage: str,
    index: int,
    artifacts: tuple[WorkflowArtifact, ...] = (),
) -> WorkflowStageRecord:
    return WorkflowStageRecord(
        record_id=f"{stage}-pass-{index}",
        stage=stage,
        status="PASS",
        attempt=1,
        execution_key=f"{stage}-key-{index}",
        revision=1,
        started_at=f"2026-09-24T01:{index:02d}:00+00:00",
        finished_at=f"2026-09-24T01:{index:02d}:30+00:00",
        artifacts=artifacts,
        cost_usd=0.0,
    )


def _visual_ready_state(
    workflow_id: str = "runtime-visual-workflow",
) -> EpisodeWorkflowState:
    project = _project_episode_2()
    prompts = PromptPlan.from_json(_load(EXAMPLES / "generic_prompt_plan.json"))
    stages = ("project_episode", "bibles", "story", "storyboard", "prompts")
    records = []
    for index, stage in enumerate(stages, start=1):
        artifacts = ()
        if stage == "project_episode":
            artifacts = (WorkflowArtifact.from_contract("project", project),)
        elif stage == "prompts":
            artifacts = (WorkflowArtifact.from_contract("prompts", prompts),)
        records.append(_record(stage, index, artifacts))
    return EpisodeWorkflowState(
        workflow_id=workflow_id,
        project_id=project.project_id,
        episode_id="episode-2",
        records=tuple(records),
        max_cost_usd=2.0,
    )


def _consistency_report() -> ConsistencyReport:
    plan = VisualGenerationPlan.from_json(
        _load(EXAMPLES / "generic_visual_generation_plan.json")
    )
    results = []
    for request in plan.requests:
        visual = VisualResult(
            request_id=request.request_id,
            engine="offline-runtime-fixture",
            success=True,
            artifacts=(
                VisualArtifact(
                    asset_id=f"{request.request_id}-asset",
                    request_id=request.request_id,
                    shot_id=request.shot_id,
                    asset_kind="image",
                    uri=f"generated/runtime/{request.request_id}.png",
                    engine="offline-runtime-fixture",
                    provider="offline",
                    width=1080,
                    height=1920,
                    duration_seconds=request.duration_seconds,
                ),
            ),
            cost_usd=0.0,
        )
        assessment = ConsistencyAssessment(
            request_id=request.request_id,
            evaluator="offline-runtime",
            identity_score=0.98,
            appearance_score=0.98,
            wardrobe_score=0.98,
            environment_score=0.98,
        )
        results.append(
            ConsistentVisualResult(
                request_id=request.request_id,
                accepted=True,
                attempts=(
                    ConsistencyAttempt(
                        attempt_number=1,
                        visual_result=visual,
                        assessment=assessment,
                    ),
                ),
            )
        )
    return ConsistencyReport(
        project_id=plan.project_id,
        story_id=plan.story_id,
        episode_id=plan.episode_id,
        results=tuple(results),
        metadata={"offline": True},
    )


def _media_ready_state(
    workflow_id: str = "runtime-media-workflow",
) -> EpisodeWorkflowState:
    project = _project_episode_2()
    story = StoryPlan.from_json(_load(EXAMPLES / "generic_story_plan.json"))
    consistency = _consistency_report()
    stages = (
        "project_episode",
        "bibles",
        "story",
        "storyboard",
        "prompts",
        "visuals",
        "consistency",
    )
    records = []
    for index, stage in enumerate(stages, start=1):
        artifacts = ()
        if stage == "project_episode":
            artifacts = (WorkflowArtifact.from_contract("project", project),)
        elif stage == "story":
            artifacts = (WorkflowArtifact.from_contract("story", story),)
        elif stage == "consistency":
            artifacts = (
                WorkflowArtifact.from_contract(
                    "consistency",
                    consistency,
                ),
            )
        records.append(_record(stage, index, artifacts))
    return EpisodeWorkflowState(
        workflow_id=workflow_id,
        project_id=project.project_id,
        episode_id=story.brief.episode_id,
        records=tuple(records),
        max_cost_usd=2.0,
    )


class _NoSecrets:
    def is_available(self, reference: SecretReference) -> bool:
        del reference
        return False


class _AllSecrets:
    def is_available(self, reference: SecretReference) -> bool:
        del reference
        return True


class _FakeVisualGenerator:
    engine_name = "fake-runtime-visual"

    def __init__(self, cost: float = 0.01) -> None:
        self.cost = cost
        self.generate_calls = 0

    def estimate_cost_usd(self, request) -> float:
        del request
        return self.cost

    def generate(self, request) -> VisualResult:
        self.generate_calls += 1
        return VisualResult(
            request_id=request.request_id,
            engine=self.engine_name,
            success=True,
            artifacts=(
                VisualArtifact(
                    asset_id=f"{request.request_id}-generated",
                    request_id=request.request_id,
                    shot_id=request.shot_id,
                    asset_kind="image",
                    uri=f"generated/fake/{request.request_id}.png",
                    engine=self.engine_name,
                    provider="fake",
                    width=1080,
                    height=1920,
                    duration_seconds=request.duration_seconds,
                ),
            ),
            cost_usd=self.cost,
            metadata={"provider_called": False},
        )


class _FakeMediaAssembler:
    engine_name = "fake-runtime-media"

    def __init__(self, cost: float = 0.05) -> None:
        self.cost = cost
        self.assemble_calls = 0

    def estimate_cost_usd(self, plan) -> float:
        del plan
        return self.cost

    def assemble(self, plan) -> MediaAssemblyResult:
        self.assemble_calls += 1
        duration = sum(plan.visual_durations_seconds)
        return MediaAssemblyResult(
            assembly_id=plan.assembly_id,
            engine=self.engine_name,
            success=True,
            audio=AudioArtifact(
                audio_id=f"{plan.assembly_id}-audio",
                uri=f"{plan.output_uri}.wav",
                duration_seconds=duration,
                engine=self.engine_name,
                provider="fake",
            ),
            subtitle=(
                SubtitleArtifact(
                    subtitle_id=f"{plan.assembly_id}-subtitles",
                    uri=f"{plan.output_uri}.srt",
                    format="srt",
                    cue_count=4,
                    engine=self.engine_name,
                    provider="fake",
                )
                if plan.subtitle_enabled
                else None
            ),
            video=RenderArtifact(
                render_id=f"{plan.assembly_id}-video",
                uri=plan.output_uri,
                engine=self.engine_name,
                provider="fake",
                width=1080,
                height=1920,
                duration_seconds=duration,
                metadata={"publication_performed": False},
            ),
            cost_usd=self.cost,
            metadata={
                "provider_called": False,
                "publication_performed": False,
            },
        )


def _visual_profile(
    *,
    external: bool,
    paid: bool,
) -> RuntimeProfile:
    return RuntimeProfile(
        profile_id="visual-runtime-test",
        providers=(
            RuntimeProviderBinding(
                provider_id="visual-provider",
                adapter="mpt-image",
                capabilities=(CAP_VISUAL_IMAGE,),
                options={
                    "cost_per_image_usd": 0.01,
                    "save_dir": "generated/runtime/test",
                },
                external_calls_enabled=external,
                paid_calls_enabled=paid,
                max_stage_cost_usd=1.0,
            ),
        ),
        stage_bindings={"visuals": "visual-provider"},
    )


def _media_profile(*, external: bool) -> RuntimeProfile:
    return RuntimeProfile(
        profile_id="media-runtime-test",
        providers=(
            RuntimeProviderBinding(
                provider_id="media-provider",
                adapter="mpt-media",
                capabilities=(CAP_MEDIA_ASSEMBLY,),
                options={
                    "estimated_cost_usd": 0.05,
                    "voice_name": "test-voice",
                    "output_uri_template": (
                        "generated/{project_id}/{episode_id}/r{revision}/runtime.mp4"
                    ),
                    "subtitle_enabled": True,
                },
                external_calls_enabled=external,
                paid_calls_enabled=False,
                max_stage_cost_usd=0.5,
            ),
        ),
        stage_bindings={"media": "media-provider"},
    )


def _service(tmp_path: Path) -> OperatorConsoleService:
    return OperatorConsoleService(
        workflow_dir=tmp_path / "workflows",
        review_audit_dir=tmp_path / "reviews",
        publication_audit_dir=tmp_path / "publications",
    )


@pytest.mark.parametrize(
    "name",
    ["offline.json", "mpt-guarded.json", "openai-reference-guarded.json"],
)
def test_committed_profiles_are_default_deny(name) -> None:
    profile = RuntimeProfile.from_json(_load(PROFILES / name))

    for provider in profile.providers:
        assert provider.external_calls_enabled is False
        assert provider.paid_calls_enabled is False
    assert profile.metadata["live_publication"] is False


def test_kids_puppies_runtime_profile_is_default_deny() -> None:
    profile = RuntimeProfile.from_json(
        _load(
            REPO_ROOT
            / "verticals"
            / "kids_puppies"
            / "runtime"
            / "profile-guarded.json"
        )
    )

    assert profile.profile_id == "kids-puppies-guarded"
    assert profile.stage_bindings == {
        "visuals": "kids-reference-visuals",
        "media": "kids-media",
    }
    for provider in profile.providers:
        assert provider.external_calls_enabled is False
        assert provider.paid_calls_enabled is False
    assert profile.metadata["child_safe"] is True
    assert profile.metadata["pilot_cost_ceiling_usd"] == pytest.approx(10)
    assert profile.metadata["live_publication"] is False

    visuals = profile.provider("kids-reference-visuals")
    assert visuals.options["response_model"] == "gpt-6-astra"
    assert visuals.options["image_model"] == "gpt-image-2.5-sunburst"
    assert visuals.options["image_quality"] == "low"
    assert visuals.options["image_size"] == "1024x1536"
    assert visuals.max_stage_cost_usd == pytest.approx(10)
    assert [ref.reference for ref in visuals.secret_refs] == ["env:OPENAI_API_KEY"]

    media = profile.provider("kids-media")
    assert media.options["voice_name"] == "es-CO-SalomeNeural-Female"
    assert media.options["estimated_cost_usd"] == pytest.approx(0)
    bundled_voices = json.loads(
        (REPO_ROOT / "app/services/data/azure_voices.json").read_text(encoding="utf-8")
    )
    assert {
        "name": "es-CO-SalomeNeural",
        "gender": "Female",
    } in bundled_voices


def test_kids_puppies_real_voice_can_be_enabled_for_external_media() -> None:
    profile = RuntimeProfile.from_json(
        _load(
            REPO_ROOT
            / "verticals"
            / "kids_puppies"
            / "runtime"
            / "profile-guarded.json"
        )
    )
    media = profile.provider("kids-media")
    enabled = replace(media, external_calls_enabled=True)
    registry = RuntimeProviderRegistry()
    registry.validate_binding(enabled, _AllSecrets())
    registry.validate_binding(media, _AllSecrets())


def test_cli_runtime_matrix_is_offline_and_json_serializable(
    tmp_path,
    capsys,
) -> None:
    profile_path = PROFILES / "mpt-guarded.json"
    argv = [
        "--workflow-dir",
        str(tmp_path / "workflows"),
        "--review-dir",
        str(tmp_path / "reviews"),
        "--publication-dir",
        str(tmp_path / "publications"),
        "runtime-matrix",
        "--profile",
        str(profile_path),
    ]

    assert cli_main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_id"] == "mpt-guarded"
    assert {row["adapter"] for row in payload["profile"]} == {
        "mpt-image",
        "mpt-media",
    }


def test_secret_reference_round_trip_contains_reference_not_value() -> None:
    ref = SecretReference.parse("env:OPENAI_API_KEY")

    assert ref.reference == "env:OPENAI_API_KEY"
    assert SecretReference.from_json(ref.to_json()) == ref
    assert "sk-" not in ref.to_json()


def test_sensitive_runtime_options_are_rejected() -> None:
    with pytest.raises(DomainValidationError, match="SecretReference"):
        RuntimeProviderBinding(
            provider_id="bad-provider",
            adapter="mpt-image",
            capabilities=(CAP_VISUAL_IMAGE,),
            options={"api_key": "raw-secret-value"},
        )


def test_paid_calls_require_external_calls() -> None:
    with pytest.raises(
        DomainValidationError,
        match="requires external_calls_enabled",
    ):
        RuntimeProviderBinding(
            provider_id="bad-provider",
            adapter="mpt-image",
            capabilities=(CAP_VISUAL_IMAGE,),
            external_calls_enabled=False,
            paid_calls_enabled=True,
        )


def test_registry_rejects_unknown_adapter_and_capability() -> None:
    registry = RuntimeProviderRegistry()
    unknown = RuntimeProviderBinding(
        provider_id="unknown",
        adapter="not-registered",
        capabilities=(CAP_VISUAL_IMAGE,),
    )
    with pytest.raises(DomainValidationError, match="not registered"):
        registry.validate_binding(unknown, _NoSecrets())

    mismatch = RuntimeProviderBinding(
        provider_id="mismatch",
        adapter="mpt-media",
        capabilities=(CAP_VISUAL_IMAGE,),
        options={
            "voice_name": "voice",
            "output_uri_template": "generated/{episode_id}.mp4",
        },
    )
    with pytest.raises(DomainValidationError, match="unsupported"):
        registry.validate_binding(mismatch, _NoSecrets())


def test_runtime_matrix_rejects_invalid_option_types() -> None:
    registry = RuntimeProviderRegistry()
    profile = _visual_profile(external=False, paid=False)
    binding = replace(
        profile.providers[0],
        options={
            "cost_per_image_usd": "0.01",
            "save_dir": "generated/runtime/test",
        },
    )

    with pytest.raises(DomainValidationError, match="must be a number"):
        registry.validate_profile(
            replace(profile, providers=(binding,)),
            _NoSecrets(),
        )


def test_external_openai_profile_requires_declared_and_available_secret() -> None:
    registry = RuntimeProviderRegistry()
    base = RuntimeProfile.from_json(_load(PROFILES / "openai-reference-guarded.json"))
    binding = replace(
        base.providers[0],
        external_calls_enabled=True,
    )
    profile = replace(base, providers=(binding,))

    with pytest.raises(DomainValidationError, match="unavailable"):
        registry.validate_profile(profile, _NoSecrets())

    missing_ref = replace(binding, secret_refs=())
    with pytest.raises(DomainValidationError, match="missing required"):
        registry.validate_profile(
            replace(base, providers=(missing_ref,)),
            _AllSecrets(),
        )

    registry.validate_profile(profile, _AllSecrets())


def test_runtime_profile_capability_matrix_hides_secret_values() -> None:
    profile = RuntimeProfile.from_json(
        _load(PROFILES / "openai-reference-guarded.json")
    )
    matrix = profile.capability_matrix()

    assert matrix[0]["secret_refs"] == ["env:OPENAI_API_KEY"]
    assert all("value" not in row for row in matrix)
    assert "sk-" not in json.dumps(matrix)


def test_guarded_mpt_profile_blocks_before_provider_call(
    tmp_path,
    monkeypatch,
) -> None:
    called = False

    def fail_provider(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(
        "extensions.mpt_adapter.visual.material.generate_images_openai",
        fail_provider,
    )

    service = _service(tmp_path)
    state = _visual_ready_state("guarded-workflow")
    service.workflow_store.save(state)
    profile = RuntimeProfile.from_json(_load(PROFILES / "mpt-guarded.json"))

    updated = service.run_runtime_stage(
        state.workflow_id,
        profile,
    )

    record = updated.latest_record("visuals")
    assert record is not None
    assert record.status == "BLOCKED"
    assert "external_calls_enabled=False" in (record.error or "")
    assert not called


def test_operator_runtime_requires_extra_external_and_paid_confirmation(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    state = _visual_ready_state("confirm-workflow")
    service.workflow_store.save(state)
    profile = _visual_profile(external=True, paid=True)

    with pytest.raises(DomainValidationError, match="confirm_external"):
        service.run_runtime_stage(
            state.workflow_id,
            profile,
            registry=RuntimeProviderRegistry(),
            secrets=_AllSecrets(),
        )

    with pytest.raises(DomainValidationError, match="confirm_paid"):
        service.run_runtime_stage(
            state.workflow_id,
            profile,
            confirm_external=True,
            registry=RuntimeProviderRegistry(),
            secrets=_AllSecrets(),
        )


def test_visual_runtime_executor_wires_fake_generator_and_cost(
    tmp_path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    state = _visual_ready_state("visual-success-workflow")
    service.workflow_store.save(state)
    profile = _visual_profile(external=True, paid=True)
    registry = RuntimeProviderRegistry()
    fake = _FakeVisualGenerator(cost=0.01)
    monkeypatch.setattr(
        registry,
        "build_visual_generator",
        lambda binding, secrets: fake,
    )

    updated = service.run_runtime_stage(
        state.workflow_id,
        profile,
        confirm_external=True,
        confirm_paid=True,
        registry=registry,
        secrets=_AllSecrets(),
    )

    record = updated.latest_record("visuals")
    assert record is not None
    assert record.status == "PASS"
    assert record.cost_usd == pytest.approx(0.04)
    assert fake.generate_calls == 4
    assert {item.artifact_type for item in record.artifacts} == {
        "VisualGenerationPlan",
        "VisualGenerationReport",
    }
    serialized = updated.to_json()
    assert "raw-secret-value" not in serialized
    assert "OPENAI_API_KEY" not in serialized


def test_reference_plan_does_not_silently_use_basic_visual_provider(
    tmp_path,
    monkeypatch,
) -> None:
    state = _visual_ready_state("reference-mismatch-workflow")
    prompts = state.require_one("PromptPlan")
    changed_prompts = []
    for index, prompt in enumerate(prompts.prompts):
        changed_prompts.append(
            replace(
                prompt,
                reference_asset_ids=(
                    ("guide-ref-v1",) if index == 0 else prompt.reference_asset_ids
                ),
            )
        )
    changed = replace(prompts, prompts=tuple(changed_prompts))
    records = []
    for record in state.records:
        if record.stage == "prompts":
            records.append(
                replace(
                    record,
                    artifacts=(
                        WorkflowArtifact.from_contract(
                            "prompts-with-reference",
                            changed,
                        ),
                    ),
                )
            )
        else:
            records.append(record)
    state = replace(state, records=tuple(records))

    service = _service(tmp_path)
    service.workflow_store.save(state)
    profile = _visual_profile(external=True, paid=True)
    registry = RuntimeProviderRegistry()
    fake = _FakeVisualGenerator()
    monkeypatch.setattr(
        registry,
        "build_visual_generator",
        lambda binding, secrets: fake,
    )

    updated = service.run_runtime_stage(
        state.workflow_id,
        profile,
        confirm_external=True,
        confirm_paid=True,
        registry=registry,
        secrets=_AllSecrets(),
    )

    record = updated.latest_record("visuals")
    assert record is not None
    assert record.status == "FAIL"
    assert "visual.image.reference" in (record.error or "")
    assert fake.generate_calls == 0


def test_reference_runtime_binds_bibles_before_generation() -> None:
    state = _visual_ready_state("reference-binding-workflow")
    characters = CharacterBible.from_json(
        _load(EXAMPLES / "generic_character_bible.json")
    )
    universe = UniverseBible.from_json(_load(EXAMPLES / "generic_universe_bible.json"))
    records = tuple(
        replace(
            record,
            artifacts=(
                WorkflowArtifact.from_contract("characters", characters),
                WorkflowArtifact.from_contract("universe", universe),
            ),
        )
        if record.stage == "bibles"
        else record
        for record in state.records
    )
    state = replace(state, records=records)
    binding = RuntimeProviderBinding(
        provider_id="reference-provider",
        adapter="openai-reference-image",
        capabilities=(CAP_VISUAL_REFERENCE_IMAGE,),
        options={"reference_catalog_path": "unused.json"},
    )
    profile = RuntimeProfile(
        profile_id="reference-test",
        providers=(binding,),
        stage_bindings={"visuals": binding.provider_id},
    )
    executor = RuntimeVisualStageExecutor(
        profile, RuntimeProviderRegistry(), _NoSecrets()
    )
    plan = executor._plan(state, binding)
    assert plan.metadata["consistency_references_bound"] is True
    assert all(request.reference_asset_ids for request in plan.requests)


def test_media_runtime_executor_wires_fake_assembler(
    tmp_path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    state = _media_ready_state()
    service.workflow_store.save(state)
    profile = _media_profile(external=True)
    registry = RuntimeProviderRegistry()
    fake = _FakeMediaAssembler(cost=0.05)
    monkeypatch.setattr(
        registry,
        "build_media_assembler",
        lambda binding, secrets: fake,
    )

    updated = service.run_runtime_stage(
        state.workflow_id,
        profile,
        confirm_external=True,
        registry=registry,
        secrets=_AllSecrets(),
    )

    record = updated.latest_record("media")
    assert record is not None
    assert record.status == "PASS"
    assert record.cost_usd == pytest.approx(0.05)
    assert fake.assemble_calls == 1
    assert {item.artifact_type for item in record.artifacts} == {
        "MediaAssemblyPlan",
        "MediaAssemblyResult",
    }
    media = updated.require_one("MediaAssemblyResult")
    assert media.video is not None
    assert media.video.metadata["publication_performed"] is False


def test_runtime_factory_builds_only_declared_provider_stages() -> None:
    factory = RuntimeExecutorFactory(
        RuntimeProviderRegistry(),
        _NoSecrets(),
    )
    profile = RuntimeProfile.from_json(_load(PROFILES / "mpt-guarded.json"))

    executors = factory.build(profile)

    assert set(executors) == {"visuals", "media"}
    assert isinstance(executors["visuals"], RuntimeVisualStageExecutor)
    assert isinstance(executors["media"], RuntimeMediaStageExecutor)


def test_environment_secret_checker_never_returns_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-value")
    checker = EnvironmentSecretAvailability()
    ref = SecretReference.parse("env:OPENAI_API_KEY")

    assert checker.is_available(ref) is True
    assert not hasattr(checker, "resolve")


@pytest.mark.parametrize(
    "contract_type",
    [SecretReference, RuntimeProviderBinding, RuntimeProfile],
)
def test_runtime_schemas_are_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_registry_has_no_top_level_provider_imports() -> None:
    path = REPO_ROOT / "extensions" / "runtime_profiles" / "registry.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
        "app",
        "openai",
    )
    imports = []
    for node in tree.body:
        modules = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                imports.append(module)

    assert not imports


def test_runtime_core_has_no_provider_or_operator_imports() -> None:
    path = REPO_ROOT / "extensions" / "content_studio" / "runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app",
        "openai",
        "requests",
        "verticals",
        "extensions.mpt_adapter",
        "extensions.openai_image_adapter",
        "extensions.runtime_profiles",
        "extensions.operator_console",
    )
    violations = []

    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(module)

    assert not violations
