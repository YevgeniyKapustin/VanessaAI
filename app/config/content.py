from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config.settings import settings


class LLMGenerationProfile(BaseModel):
    temperature: float = Field(default=0.8, ge=0.0, le=1.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=64, le=4096)
    presence_penalty: float = Field(default=0.0, ge=0.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=0.0, le=2.0)

    def to_params(self):
        from app.llm.planner.generation_config import LLMGenerationParams

        return LLMGenerationParams(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
        )


class LLMGenerationProfiles(BaseModel):
    composer: LLMGenerationProfile = Field(
        default_factory=lambda: LLMGenerationProfile(
            temperature=0.8,
            top_p=0.9,
            max_tokens=512,
            presence_penalty=0.4,
            frequency_penalty=0.35,
        )
    )
    planner: LLMGenerationProfile = Field(
        default_factory=lambda: LLMGenerationProfile(
            temperature=0.1,
            top_p=0.85,
            max_tokens=192,
            presence_penalty=0.0,
            frequency_penalty=0.0,
        )
    )


class ConversationContent(BaseModel):
    session_window_size: int = Field(default=12, ge=4, le=50)
    session_idle_seconds: int = Field(default=300, ge=60, le=3600)
    post_reply_listen_count: int = Field(default=5, ge=1, le=20)


class PersonaContent(BaseModel):
    identity: str = ""
    voice: str = ""
    rules: str = ""
    role: str = ""
    style: str = ""

    def identity_text(self) -> str:
        return (self.identity or self.role).strip()

    def voice_text(self) -> str:
        return (self.voice or self.style).strip()

    def rules_text(self) -> str:
        return self.rules.strip()


class LLMContent(BaseModel):
    task: str = ""
    answer: str = ""
    answer_examples: str = ""
    reply_instruction: str = ""
    compose_instruction: str = ""
    context_header: str
    context_block_header: str = (
        "--- Фрагмент {index} ({started_at} — {ended_at}) ---"
    )
    context_block_separator: str = "\n\n"
    current_message_header: str
    current_message_line: str = "[user:{sender}] {content}"
    session_header: str = "Недавняя переписка в чате:"
    session_user_line: str = "{time} [user:{sender}] {content}"
    session_assistant_line: str = "{time} [assistant] {content}"
    anchor_marker: str = " ← совпадение с запросом"
    assistant_line: str = "{time} [assistant]{anchor} {content}"
    user_line: str = "{time} [user:{sender}]{anchor} {content}"
    humor_quotes_header: str = "Узнаваемые мемы и подколы из беседы (если уместно):"
    humor_quote_line: str = "- {quote}"
    owner_message_note: str = ""
    generation: LLMGenerationProfiles = Field(default_factory=LLMGenerationProfiles)

    def task_text(self) -> str:
        return (self.task or self.reply_instruction).strip()

    def answer_text(self) -> str:
        parts = [(self.answer or self.compose_instruction).strip()]
        if self.answer_examples.strip():
            parts.append(self.answer_examples.strip())
        return "\n\n".join(part for part in parts if part)


class BotAccessMessages(BaseModel):
    private_chat: str
    required_user_missing: str
    required_user_not_configured: str


class BotMessagesContent(BaseModel):
    welcome: str
    error_api: str
    access: BotAccessMessages


class DecisionContent(BaseModel):
    block_consecutive_replies: bool = True
    noise_max_words: int = 2
    noise_max_chars: int = 12
    default_bot_names: list[str] = Field(default_factory=list)
    trigger_keywords: list[str] = Field(default_factory=list)
    question_words: list[str] = Field(default_factory=list)
    modal_verbs: list[str] = Field(default_factory=list)


class ProfanityContent(BaseModel):
    enabled: bool = False
    instruction: str = ""
    lemmas: dict[str, str] = Field(default_factory=dict)
    invariable: dict[str, str] = Field(default_factory=dict)


class RagContent(BaseModel):
    turn_planner_prompt: str = ""
    query_rewrite_prompt: str = ""
    vector_min_score: float = 0.35

    @property
    def planner_prompt(self) -> str:
        if self.turn_planner_prompt.strip():
            return self.turn_planner_prompt
        return self.query_rewrite_prompt


class AppContent(BaseModel):
    persona: PersonaContent
    llm: LLMContent
    conversation: ConversationContent = Field(default_factory=ConversationContent)
    bot: BotMessagesContent
    decision: DecisionContent
    profanity: ProfanityContent = Field(default_factory=ProfanityContent)
    rag: RagContent = Field(default_factory=RagContent)


def resolve_content_path() -> Path:
    configured = Path(settings.content_config_path)
    if configured.is_file():
        return configured
    project_root = Path(__file__).resolve().parents[2]
    fallback = project_root / "config" / "content.yaml"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"Content config not found: {configured} or {fallback}"
    )


@lru_cache
def get_content() -> AppContent:
    path = resolve_content_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AppContent.model_validate(raw)


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
