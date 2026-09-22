import ast
import json
from pathlib import Path

import pytest

from extensions.content_studio.bibles import (
    CharacterBible,
    CharacterProfile,
    LocationProfile,
    UniverseBible,
)
from extensions.content_studio.domain import (
    DomainValidationError,
    ProjectSpec,
    SCHEMA_VERSION,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "extensions" / "content_studio"
GENERIC_PROJECT = CORE / "examples" / "generic_project.json"
GENERIC_CHARACTER_BIBLE = (
    CORE / "examples" / "generic_character_bible.json"
)
GENERIC_UNIVERSE_BIBLE = (
    CORE / "examples" / "generic_universe_bible.json"
)
KIDS_PROJECT = (
    REPO_ROOT
    / "verticals"
    / "kids_puppies"
    / "examples"
    / "project.json"
)
KIDS_CHARACTER_BIBLE = (
    REPO_ROOT
    / "verticals"
    / "kids_puppies"
    / "bibles"
    / "character_bible.json"
)
KIDS_UNIVERSE_BIBLE = (
    REPO_ROOT
    / "verticals"
    / "kids_puppies"
    / "bibles"
    / "universe_bible.json"
)


def _load_project(path: Path) -> ProjectSpec:
    return ProjectSpec.from_json(path.read_text(encoding="utf-8"))


def _load_character_bible(path: Path) -> CharacterBible:
    return CharacterBible.from_json(path.read_text(encoding="utf-8"))


def _load_universe_bible(path: Path) -> UniverseBible:
    return UniverseBible.from_json(path.read_text(encoding="utf-8"))


def test_generic_bibles_round_trip_and_validate_project() -> None:
    project = _load_project(GENERIC_PROJECT)
    characters = _load_character_bible(GENERIC_CHARACTER_BIBLE)
    universe = _load_universe_bible(GENERIC_UNIVERSE_BIBLE)

    characters.validate_project(project)
    universe.validate_project(project)

    assert CharacterBible.from_json(characters.to_json()) == characters
    assert UniverseBible.from_json(universe.to_json()) == universe
    assert characters.resolve("presenter").character_id == "guide-1"
    assert universe.resolve("main-studio").location_id == "studio"


def test_kids_puppies_bibles_are_valid_but_vertical_scoped() -> None:
    project = _load_project(KIDS_PROJECT)
    characters = _load_character_bible(KIDS_CHARACTER_BIBLE)
    universe = _load_universe_bible(KIDS_UNIVERSE_BIBLE)

    characters.validate_project(project)
    universe.validate_project(project)

    assert characters.resolve("Toby").character_id == "toby"
    assert universe.resolve("puppy-park").location_id == "parque"


def test_character_bible_requires_exact_project_coverage() -> None:
    project = _load_project(KIDS_PROJECT)
    incomplete = CharacterBible(
        project_id=project.project_id,
        profiles=(CharacterProfile(character_id="toby"),),
    )

    with pytest.raises(
        DomainValidationError,
        match="coverage mismatch",
    ):
        incomplete.validate_project(project)


def test_character_bible_rejects_unknown_project_character() -> None:
    project = _load_project(GENERIC_PROJECT)
    bible = CharacterBible(
        project_id=project.project_id,
        profiles=(
            CharacterProfile(character_id="guide-1"),
            CharacterProfile(character_id="intruder"),
        ),
    )

    with pytest.raises(
        DomainValidationError,
        match="coverage mismatch",
    ):
        bible.validate_project(project)


def test_character_aliases_must_not_be_ambiguous() -> None:
    with pytest.raises(
        DomainValidationError,
        match="ambiguous character alias",
    ):
        CharacterBible(
            project_id="project-1",
            profiles=(
                CharacterProfile(
                    character_id="alpha",
                    aliases=("shared",),
                ),
                CharacterProfile(
                    character_id="beta",
                    aliases=("SHARED",),
                ),
            ),
        )


def test_universe_bible_rejects_unresolved_scene_location() -> None:
    project = _load_project(GENERIC_PROJECT)
    universe = UniverseBible(
        project_id=project.project_id,
        locations=(
            LocationProfile(
                location_id="other-place",
                description="A different place.",
            ),
        ),
    )

    with pytest.raises(
        DomainValidationError,
        match="cannot resolve scene locations",
    ):
        universe.validate_project(project)


def test_location_aliases_must_not_be_ambiguous() -> None:
    with pytest.raises(
        DomainValidationError,
        match="ambiguous location alias",
    ):
        UniverseBible(
            project_id="project-1",
            locations=(
                LocationProfile(
                    location_id="place-a",
                    aliases=("shared",),
                    description="First place.",
                ),
                LocationProfile(
                    location_id="place-b",
                    aliases=("SHARED",),
                    description="Second place.",
                ),
            ),
        )


@pytest.mark.parametrize(
    "contract_type",
    [
        CharacterProfile,
        CharacterBible,
        LocationProfile,
        UniverseBible,
    ],
)
def test_bible_schemas_are_serializable_and_versioned(
    contract_type: type,
) -> None:
    schema = contract_type.json_schema()

    assert json.dumps(schema, sort_keys=True)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert "schema_version" in schema["required"]


def test_bibles_core_has_no_provider_or_vertical_imports() -> None:
    path = CORE / "bibles.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = ("app", "verticals", "extensions.mpt_adapter")
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


def test_generic_bible_examples_do_not_contain_vertical_defaults() -> None:
    content = (
        GENERIC_CHARACTER_BIBLE.read_text(encoding="utf-8")
        + GENERIC_UNIVERSE_BIBLE.read_text(encoding="utf-8")
    ).lower()

    assert "kids_puppies" not in content
    assert "toby" not in content
    assert "luna" not in content


def test_bible_metadata_must_be_json_compatible() -> None:
    with pytest.raises(
        DomainValidationError,
        match="JSON-compatible",
    ):
        CharacterProfile(
            character_id="guide-1",
            metadata={"bad": object()},
        )
