"""Offline checks for the complete paid reference-image batch."""

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from extensions.content_studio.consistency import ReferenceAsset, ReferenceCatalog
from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.runtime import (
    CAP_VISUAL_REFERENCE_IMAGE,
    RuntimeProfile,
    RuntimeProviderBinding,
)
from extensions.content_studio.visual_generation import VisualGenerationPlan
from extensions.operator_console.cli import main as operator_cli
from extensions.runtime_profiles.executors import RuntimeVisualStageExecutor
from extensions.runtime_profiles.reference_preflight import preflight_reference_images
from extensions.runtime_profiles.registry import RuntimeProviderRegistry


EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "extensions/content_studio/examples/generic_visual_generation_plan.json"
)


def _plan() -> VisualGenerationPlan:
    source = VisualGenerationPlan.from_json(EXAMPLE.read_text(encoding="utf-8"))
    requests = tuple(
        replace(request, reference_asset_ids=(f"reference-{index}",))
        for index, request in enumerate(source.requests)
    )
    return replace(source, requests=requests)


def _catalog(plan: VisualGenerationPlan, paths: list[Path]) -> ReferenceCatalog:
    return ReferenceCatalog(
        project_id=plan.project_id,
        assets=tuple(
            ReferenceAsset(
                reference_asset_id=f"reference-{index}",
                uri=str(path),
                media_type="image/png",
            )
            for index, path in enumerate(paths)
        ),
    )


def test_preflight_accepts_complete_local_image_batch(tmp_path: Path) -> None:
    plan = _plan()
    paths = []
    for index in range(len(plan.requests)):
        path = tmp_path / f"reference-{index}.png"
        Image.new("RGB", (8, 8)).save(path)
        paths.append(path)
    preflight_reference_images(plan, _catalog(plan, paths))


def test_preflight_rejects_missing_late_reference(tmp_path: Path) -> None:
    plan = _plan()
    paths = []
    for index in range(len(plan.requests)):
        path = tmp_path / f"reference-{index}.png"
        if index < len(plan.requests) - 1:
            Image.new("RGB", (8, 8)).save(path)
        paths.append(path)
    with pytest.raises(DomainValidationError, match="does not exist"):
        preflight_reference_images(plan, _catalog(plan, paths))


def test_preflight_rejects_unbound_plan(tmp_path: Path) -> None:
    source = VisualGenerationPlan.from_json(EXAMPLE.read_text(encoding="utf-8"))
    with pytest.raises(DomainValidationError, match="no reference_asset_ids"):
        preflight_reference_images(source, _catalog(_plan(), [tmp_path / "x.png"] * len(source.requests)))


def test_preflight_rejects_placeholder_and_corrupt_image(tmp_path: Path) -> None:
    plan = _plan()
    paths = [tmp_path / f"reference-{index}.png" for index in range(len(plan.requests))]
    for path in paths:
        Image.new("RGB", (8, 8)).save(path)
    catalog = _catalog(plan, paths)
    placeholder = replace(
        catalog,
        assets=(replace(catalog.assets[0], metadata={"placeholder": True}),)
        + catalog.assets[1:],
    )
    with pytest.raises(DomainValidationError, match="placeholder"):
        preflight_reference_images(plan, placeholder)

    paths[0].write_text("not an image", encoding="utf-8")
    with pytest.raises(DomainValidationError, match="not a readable image"):
        preflight_reference_images(plan, catalog)


def test_runtime_does_not_call_provider_if_late_reference_is_missing(
    tmp_path: Path,
) -> None:
    plan = _plan()
    paths = [tmp_path / f"reference-{index}.png" for index in range(len(plan.requests))]
    for path in paths[:-1]:
        Image.new("RGB", (8, 8)).save(path)
    catalog_path = tmp_path / "references.json"
    catalog_path.write_text(_catalog(plan, paths).to_json(), encoding="utf-8")
    binding = RuntimeProviderBinding(
        provider_id="visual-provider",
        adapter="openai-reference-image",
        capabilities=(CAP_VISUAL_REFERENCE_IMAGE,),
        options={"reference_catalog_path": str(catalog_path)},
        external_calls_enabled=True,
        paid_calls_enabled=True,
    )
    profile = RuntimeProfile(
        profile_id="preflight-test",
        providers=(binding,),
        stage_bindings={"visuals": binding.provider_id},
    )

    class FakeGenerator:
        engine_name = "fake"
        calls = 0

        def estimate_cost_usd(self, request):
            return 0.01

        def generate_with_references(self, request, references):
            self.calls += 1
            raise AssertionError("provider must not be called")

    generator = FakeGenerator()
    executor = RuntimeVisualStageExecutor(profile, RuntimeProviderRegistry(), None)
    with pytest.raises(DomainValidationError, match="does not exist"):
        executor._generate_references(generator, plan, binding)
    assert generator.calls == 0


def test_operator_can_preflight_without_provider_credentials(
    tmp_path: Path,
    capsys,
) -> None:
    plan = _plan()
    paths = [tmp_path / f"reference-{index}.png" for index in range(len(plan.requests))]
    for path in paths:
        Image.new("RGB", (8, 8)).save(path)
    plan_path = tmp_path / "plan.json"
    catalog_path = tmp_path / "catalog.json"
    plan_path.write_text(plan.to_json(), encoding="utf-8")
    catalog_path.write_text(_catalog(plan, paths).to_json(), encoding="utf-8")
    assert operator_cli([
        "preflight-references",
        "--plan", str(plan_path),
        "--catalog", str(catalog_path),
    ]) == 0
    assert '"provider_called": false' in capsys.readouterr().out


def test_operator_binds_kids_bibles_before_offline_preflight(
    tmp_path: Path,
    capsys,
) -> None:
    root = Path(__file__).resolve().parents[2] / "verticals/kids_puppies"
    source = VisualGenerationPlan.from_json(
        (root / "visuals/ep0002.visual-plan.json").read_text(encoding="utf-8")
    )
    assert all(not request.reference_asset_ids for request in source.requests)
    paths = [tmp_path / f"reference-{index}.png" for index in range(3)]
    for path in paths:
        Image.new("RGB", (8, 8)).save(path)
    catalog = ReferenceCatalog(
        project_id=source.project_id,
        assets=tuple(
            ReferenceAsset(
                reference_asset_id=asset_id,
                uri=str(path),
            )
            for asset_id, path in zip(
                ("toby-ref-v1", "luna-ref-v1", "park-ref-v1"), paths
            )
        ),
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(catalog.to_json(), encoding="utf-8")
    assert operator_cli([
        "preflight-references",
        "--plan", str(root / "visuals/ep0002.visual-plan.json"),
        "--catalog", str(catalog_path),
        "--character-bible", str(root / "bibles/character_bible.json"),
        "--universe-bible", str(root / "bibles/universe_bible.json"),
    ]) == 0
    assert '"reference_count": 3' in capsys.readouterr().out
