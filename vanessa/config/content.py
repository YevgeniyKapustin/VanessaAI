from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from vanessa.config.content_llm import (
    LLMContent,
    LLMGenerationProfile,
    LLMGenerationProfiles,
    PromptBudgetContent,
)
from vanessa.config.content_sections import (
    BotAccessMessages,
    BotMessagesContent,
    BotNotesMessages,
    ConversationContent,
    DecisionContent,
    MemeDefContent,
    MemesContent,
    MemoryContent,
    MetricsContent,
    PersonaContent,
    PortraitContent,
    ProfanityContent,
    RagContent,
)
from vanessa.config.content_stickers import StickerDefContent, StickersContent
from vanessa.config.paths import resolve_settings_path
from vanessa.config.settings import settings

# Paths are relative to config/behavior/. Clusters match pipeline jobs.
CONTENT_SECTIONS: dict[str, str | tuple[str, ...]] = {
    "bot": "bot.yaml",
    "persona": "persona.yaml",
    "conversation": "conversation.yaml",
    "llm": (
        "compose/system.yaml",
        "compose/layout.yaml",
        "compose/notes.yaml",
        "compose/generation.yaml",
    ),
    "decision": ("gate/decision.yaml", "gate/reaction_gate.yaml"),
    "memory": "knowledge/memory.yaml",
    "metrics": ("knowledge/metrics.yaml", "knowledge/mood.yaml"),
    "portrait": "knowledge/portrait.yaml",
    "rag": ("retrieve/rag.yaml", "gate/planner.yaml"),
    "profanity": "humor/profanity.yaml",
    "stickers": "humor/stickers.yaml",
    "memes": "humor/memes.yaml",
}


class AppContent(BaseModel):
    persona: PersonaContent
    llm: LLMContent
    conversation: ConversationContent = Field(default_factory=ConversationContent)
    bot: BotMessagesContent
    decision: DecisionContent
    profanity: ProfanityContent = Field(default_factory=ProfanityContent)
    rag: RagContent = Field(default_factory=RagContent)
    memory: MemoryContent = Field(default_factory=MemoryContent)
    metrics: MetricsContent = Field(default_factory=MetricsContent)
    portrait: PortraitContent = Field(default_factory=PortraitContent)
    stickers: StickersContent = Field(default_factory=StickersContent)
    memes: MemesContent = Field(default_factory=MemesContent)


def resolve_content_source() -> Path:
    """Locate the behavior YAML: a directory of per-section files or a single file."""
    source = resolve_settings_path(settings.behavior_config_path, "behavior")
    if source.exists():
        return source
    raise FileNotFoundError(f"Behavior config not found: {source}")


def _read_yaml_mapping(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return raw


def _merge_section_files(source: Path, filenames: str | tuple[str, ...]) -> dict:
    names = (filenames,) if isinstance(filenames, str) else filenames
    merged: dict = {}
    for name in names:
        chunk = _read_yaml_mapping(source / name)
        clash = set(merged) & set(chunk)
        if clash:
            raise ValueError(f"duplicate keys in {name}: {sorted(clash)}")
        merged.update(chunk)
    return merged


def _load_content_dict(source: Path) -> dict:
    """Assemble the AppContent dict from either a directory of section files
    or a single monolithic YAML file (backward compatible)."""
    if source.is_dir():
        return {
            section: _merge_section_files(source, filenames)
            for section, filenames in CONTENT_SECTIONS.items()
        }
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    return raw or {}


@lru_cache
def get_content() -> AppContent:
    source = resolve_content_source()
    return AppContent.model_validate(_load_content_dict(source))


def get_photo_placeholder() -> str:
    return get_content().bot.photo_placeholder


def get_bot_name_aliases() -> tuple[str, ...]:
    names = list(get_content().decision.default_bot_names)
    names.extend(settings.bot_name_aliases)
    return tuple(dict.fromkeys(name.strip().lower() for name in names if name.strip()))


def get_trigger_keywords() -> tuple[str, ...]:
    if settings.decision_trigger_keywords.strip():
        return settings.trigger_keywords
    return tuple(get_content().decision.trigger_keywords)


def get_question_words() -> tuple[str, ...]:
    return tuple(get_content().decision.question_words)


def get_modal_verbs() -> tuple[str, ...]:
    return tuple(get_content().decision.modal_verbs)


def get_continuation_phrases() -> tuple[str, ...]:
    return tuple(
        phrase.strip().lower()
        for phrase in get_content().decision.continuation_phrases
        if phrase.strip()
    )


__all__ = [
    "CONTENT_SECTIONS",
    "AppContent",
    "BotAccessMessages",
    "BotMessagesContent",
    "BotNotesMessages",
    "ConversationContent",
    "DecisionContent",
    "LLMContent",
    "LLMGenerationProfile",
    "LLMGenerationProfiles",
    "MemeDefContent",
    "MemesContent",
    "MemoryContent",
    "MetricsContent",
    "PersonaContent",
    "PortraitContent",
    "ProfanityContent",
    "PromptBudgetContent",
    "RagContent",
    "StickerDefContent",
    "StickersContent",
    "get_bot_name_aliases",
    "get_content",
    "get_continuation_phrases",
    "get_modal_verbs",
    "get_photo_placeholder",
    "get_question_words",
    "get_trigger_keywords",
    "resolve_content_source",
]
