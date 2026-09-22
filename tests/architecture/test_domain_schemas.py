import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.domain import (
    CharacterSpec,
    EpisodeSpec,
    ProjectSpec,
    SCHEMA_VERSION,
    SceneSpec,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_FILE = REPO_ROOT / "extensions" / "content_studio" / "domain.py"


@pytest.mark.parametrize(
    "contract_type",
    [ProjectSpec, EpisodeSpec, CharacterSpec, SceneSpec],
)
def test_json_schema_is_serializable_and_versioned(contract_type: type) -> None:
    schema = contract_type.json_schema()

    encoded = json.dumps(schema, sort_keys=True)
    assert encoded
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_domain_module_cannot_import_provider_or_vertical_code() -> None:
    tree = ast.parse(DOMAIN_FILE.read_text(encoding="utf-8"))
    forbidden = ("app", "verticals", "extensions.mpt_adapter")
    violations = []

    for node in ast.walk(tree):
        module_names = []
        if isinstance(node, ast.Import):
            module_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_names.append(node.module)

        for module in module_names:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(module)

    assert not violations


@pytest.mark.parametrize(
    "path",
    [
        REPO_ROOT
        / "extensions"
        / "content_studio"
        / "examples"
        / "generic_project.json",
        REPO_ROOT
        / "verticals"
        / "kids_puppies"
        / "examples"
        / "project.json",
    ],
)
def test_committed_examples_round_trip(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    project = ProjectSpec.from_json(content)
    restored = ProjectSpec.from_json(project.to_json())

    assert restored == project


def test_generic_core_example_has_no_kids_puppies_defaults() -> None:
    path = (
        REPO_ROOT
        / "extensions"
        / "content_studio"
        / "examples"
        / "generic_project.json"
    )
    content = path.read_text(encoding="utf-8").lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
