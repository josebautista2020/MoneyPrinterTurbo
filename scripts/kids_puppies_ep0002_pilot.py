"""Prepare guarded ep0002 pilot inputs from versioned kids-puppies assets.

This script intentionally performs no provider calls. It builds reproducible
operator inputs and a temporary paid runtime profile that can be used only by a
manual workflow run with explicit confirmation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from extensions.content_studio.bibles import CharacterBible, UniverseBible  # noqa: E402
from extensions.content_studio.domain import (  # noqa: E402
    EpisodeSpec,
    ProjectSpec,
    SceneSpec,
)
from extensions.content_studio.orchestration import (  # noqa: E402
    StageExecutionResult,
    WorkflowArtifact,
)
from extensions.content_studio.prompting import PromptPlan  # noqa: E402
from extensions.content_studio.runtime import RuntimeProfile  # noqa: E402
from extensions.content_studio.story import StoryPlan  # noqa: E402
from extensions.content_studio.storyboard import StoryboardPlan  # noqa: E402

VERTICAL_DIR = ROOT_DIR / "verticals" / "kids_puppies"
CONFIRMATION_PHRASE = "RUN_EP0002_PAID_UNDER_5_USD"
PILOT_COST_CEILING_USD = 5.0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _episode_from_story(story: StoryPlan) -> EpisodeSpec:
    scenes = tuple(
        SceneSpec(
            scene_id=beat.beat_id,
            order=beat.order,
            duration_seconds=beat.duration_seconds,
            location=beat.location_id,
            action=beat.summary,
            character_ids=beat.character_ids,
            dialogue=beat.dialogue_hint,
            camera=None,
            emotion=beat.emotion,
            transition="cut",
            metadata=dict(beat.metadata),
        )
        for beat in story.beats
    )
    return EpisodeSpec(
        episode_id=story.brief.episode_id,
        project_id=story.brief.project_id,
        title=story.brief.title,
        language=story.brief.language,
        duration_target_seconds=story.brief.duration_target_seconds,
        character_ids=story.brief.character_ids,
        lesson=story.brief.lesson,
        scenes=scenes,
        metadata=dict(story.brief.metadata),
    )


def _project_for_episode(story: StoryPlan) -> tuple[ProjectSpec, EpisodeSpec]:
    project = ProjectSpec.from_json(
        (VERTICAL_DIR / "examples" / "project.json").read_text(encoding="utf-8")
    )
    episode = _episode_from_story(story)
    episodes = tuple(
        item for item in project.episodes if item.episode_id != episode.episode_id
    ) + (episode,)
    project = replace(
        project,
        episodes=episodes,
        metadata={
            **dict(project.metadata),
            "ep0002_bound_from_story": True,
        },
    )
    return project, episode


def build_initial_bundle() -> list[dict[str, Any]]:
    story = StoryPlan.from_json(
        (VERTICAL_DIR / "stories" / "ep0002.story.json").read_text(
            encoding="utf-8"
        )
    )
    project, episode = _project_for_episode(story)
    character_bible = CharacterBible.from_json(
        (VERTICAL_DIR / "bibles" / "character_bible.json").read_text(
            encoding="utf-8"
        )
    )
    universe_bible = UniverseBible.from_json(
        (VERTICAL_DIR / "bibles" / "universe_bible.json").read_text(
            encoding="utf-8"
        )
    )
    storyboard = StoryboardPlan.from_json(
        (VERTICAL_DIR / "storyboards" / "ep0002.storyboard.json").read_text(
            encoding="utf-8"
        )
    )
    prompts = PromptPlan.from_json(
        (VERTICAL_DIR / "prompts" / "ep0002.prompt-plan.json").read_text(
            encoding="utf-8"
        )
    )
    results = (
        StageExecutionResult(
            stage="project_episode",
            status="PASS",
            artifacts=(
                WorkflowArtifact.from_contract("ep0002-project", project),
                WorkflowArtifact.from_contract("ep0002-episode", episode),
            ),
            cost_usd=0.0,
            metadata={"source": "versioned-kids-puppies-assets"},
        ),
        StageExecutionResult(
            stage="bibles",
            status="PASS",
            artifacts=(
                WorkflowArtifact.from_contract(
                    "ep0002-character-bible",
                    character_bible,
                ),
                WorkflowArtifact.from_contract("ep0002-universe-bible", universe_bible),
            ),
            cost_usd=0.0,
            metadata={"source": "versioned-kids-puppies-assets"},
        ),
        StageExecutionResult(
            stage="story",
            status="PASS",
            artifacts=(WorkflowArtifact.from_contract("ep0002-story", story),),
            cost_usd=0.0,
            metadata={"source": "versioned-kids-puppies-assets"},
        ),
        StageExecutionResult(
            stage="storyboard",
            status="PASS",
            artifacts=(
                WorkflowArtifact.from_contract("ep0002-storyboard", storyboard),
            ),
            cost_usd=0.0,
            metadata={"source": "versioned-kids-puppies-assets"},
        ),
        StageExecutionResult(
            stage="prompts",
            status="PASS",
            artifacts=(WorkflowArtifact.from_contract("ep0002-prompts", prompts),),
            cost_usd=0.0,
            metadata={"source": "versioned-kids-puppies-assets"},
        ),
    )
    return [item.to_dict() for item in results]


def build_paid_profile(source: Path, max_cost_usd: float) -> dict[str, Any]:
    if max_cost_usd <= 0 or max_cost_usd > PILOT_COST_CEILING_USD:
        raise SystemExit("max_cost_usd must be > 0 and <= 5")
    profile = RuntimeProfile.from_json(source.read_text(encoding="utf-8"))
    payload = profile.to_dict()
    visual_provider_id = payload["stage_bindings"]["visuals"]
    for provider in payload["providers"]:
        if provider["provider_id"] == visual_provider_id:
            provider["external_calls_enabled"] = True
            provider["paid_calls_enabled"] = True
            provider["max_stage_cost_usd"] = max_cost_usd
    payload["metadata"] = {
        **dict(payload.get("metadata", {})),
        "pilot_runtime_copy": True,
        "live_publication": False,
        "pilot_cost_ceiling_usd": max_cost_usd,
    }
    RuntimeProfile.from_dict(payload)
    return payload


def validate_confirmation(value: str, max_cost_usd: float) -> None:
    if value != CONFIRMATION_PHRASE:
        raise SystemExit(
            f"confirmation must exactly equal {CONFIRMATION_PHRASE!r}"
        )
    if max_cost_usd <= 0 or max_cost_usd > PILOT_COST_CEILING_USD:
        raise SystemExit("max_cost_usd must be > 0 and <= 5")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    bundle = sub.add_parser("bundle")
    bundle.add_argument("--output", required=True)

    profile = sub.add_parser("paid-profile")
    profile.add_argument("--source", required=True)
    profile.add_argument("--output", required=True)
    profile.add_argument("--max-cost-usd", required=True, type=float)

    confirm = sub.add_parser("confirm")
    confirm.add_argument("--value", required=True)
    confirm.add_argument("--max-cost-usd", required=True, type=float)

    args = parser.parse_args()
    if args.command == "bundle":
        _write_json(Path(args.output), build_initial_bundle())
        return 0
    if args.command == "paid-profile":
        payload = build_paid_profile(Path(args.source), args.max_cost_usd)
        _write_json(Path(args.output), payload)
        return 0
    if args.command == "confirm":
        validate_confirmation(args.value, args.max_cost_usd)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
