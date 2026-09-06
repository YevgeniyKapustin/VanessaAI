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
from vanessa.config.settings import settings

# One file per responsibility (SRP). Each file holds the body of its top-level
# section from the original monolithic config/content.yaml.
CONTENT_SECTIONS: dict[str, str] = {
    "bot": "bot.yaml",
    "persona": "persona.yaml",
    "conversation": "conversation.yaml",
    "llm": "llm.yaml",
    "decision": "decision.yaml",
    "memory": "memory.yaml",
    "metrics": "metrics.yaml",
    "portrait": "portrait.yaml",
    "rag": "rag.yaml",
    "profanity": "profanity.yaml",
    "stickers": "stickers.yaml",
    "memes": "memes.yaml",
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
    """Locate the content config: a directory of per-section files or a single YAML file."""
    configured = Path(settings.content_config_path)
    if configured.exists():
        return configured
    project_root = Path(__file__).resolve().parents[2]
    fallback = project_root / "config" / "content"
    if fallback.is_dir():
        return fallback
    raise FileNotFoundError(
        f"Content config not found: {configured} or {fallback}"
    )


def _load_content_dict(source: Path) -> dict:
    """Assemble the AppContent dict from either a directory of section files
    or a single monolithic YAML file (backward compatible)."""
    if source.is_dir():
        data: dict = {}
        for section, filename in CONTENT_SECTIONS.items():
            section_file = source / filename
            if section_file.is_file():
                raw = yaml.safe_load(section_file.read_text(encoding="utf-8"))
                data[section] = raw or {}
        return data
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
