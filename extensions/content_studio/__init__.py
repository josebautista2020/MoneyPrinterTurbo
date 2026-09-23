"""Reusable Content Studio AI core.

This package must remain vertical-agnostic. Vertical-specific behavior belongs under
``verticals/`` and integrations with MoneyPrinterTurbo belong behind adapters.
"""

from extensions.content_studio.bibles import (
    CharacterBible,
    CharacterProfile,
    LocationProfile,
    UniverseBible,
)
from extensions.content_studio.prompting import (
    CanonicalPromptCompiler,
    PromptCompiler,
    PromptContext,
    PromptPlan,
    ShotPrompt,
    compile_prompts,
)
from extensions.content_studio.story import (
    StoryBeat,
    StoryBrief,
    StoryContext,
    StoryEngine,
    StoryPlan,
    generate_story,
)
from extensions.content_studio.storyboard import (
    StoryboardContext,
    StoryboardEngine,
    StoryboardPlan,
    StoryboardScene,
    StoryboardShot,
    generate_storyboard,
)
from extensions.content_studio.domain import (
    CharacterSpec,
    DomainValidationError,
    EpisodeSpec,
    ProjectSpec,
    SCHEMA_VERSION,
    SceneSpec,
)

__all__ = [
    "CharacterBible",
    "CharacterProfile",
    "CharacterSpec",
    "DomainValidationError",
    "EpisodeSpec",
    "LocationProfile",
    "ProjectSpec",
    "SCHEMA_VERSION",
    "SceneSpec",
    "UniverseBible",
    "StoryBeat",
    "StoryBrief",
    "StoryContext",
    "StoryEngine",
    "StoryPlan",
    "generate_story",
    "StoryboardContext",
    "StoryboardEngine",
    "StoryboardPlan",
    "StoryboardScene",
    "StoryboardShot",
    "generate_storyboard",
    "CanonicalPromptCompiler",
    "PromptCompiler",
    "PromptContext",
    "PromptPlan",
    "ShotPrompt",
    "compile_prompts",
]
