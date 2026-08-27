from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config.settings import settings

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
    critic: LLMGenerationProfile = Field(
        default_factory=lambda: LLMGenerationProfile(
            temperature=0.1,
            top_p=0.85,
            max_tokens=256,
            presence_penalty=0.0,
            frequency_penalty=0.0,
        )
    )


class ConversationContent(BaseModel):
    session_window_size: int = Field(default=12, ge=4, le=50)
    session_idle_seconds: int = Field(default=300, ge=60, le=3600)
    post_reply_listen_count: int = Field(default=4, ge=1, le=20)


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


class CriticContent(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    fix_instruction_header: str = (
        "Humor editor's note (you MUST address it in the new version of the reply):"
    )


class PromptBudgetContent(BaseModel):
    """Per-section and global char caps for the compose prompt.

    Applied by ``PromptBuilder`` so a bloated context (old history, too many
    knowledge blocks, a long session) never blows the LLM context window.
    ``0`` disables the cap for that section. When the global cap is hit,
    sections are trimmed from the lowest priority up; priority order (highest
    first) is: current message > knowledge > session > context > humor/memes/
    metrics. The caps are pure character limits on the rendered bodies.
    """

    enabled: bool = True
    max_chars: int = 0  # global cap over the whole user prompt; 0 = unlimited
    context_blocks: int = 0
    knowledge_blocks: int = 0
    session_messages: int = 0
    humor_quotes: int = 0
    meme_blocks: int = 0
    meme_menu: int = 0
    metrics_block: int = 0


class LLMContent(BaseModel):
    task: str = ""
    answer: str = ""
    answer_examples: str = ""
    language: str = ""
    reply_instruction: str = ""
    compose_instruction: str = ""
    sticker_instruction: str = ""
    context_header: str
    context_block_header: str = (
        "--- Block {index} ({started_at} — {ended_at}) ---"
    )
    context_block_separator: str = "\n\n"
    current_message_header: str
    current_message_line: str = "{time} [user:{sender}] text: {content}"
    reply_message_header: str = "The user's message is a reply to this message:"
    reply_message_line: str = "[{sender}] text: {content}"
    session_header: str = "Recent correspondence in the chat:"
    session_user_line: str = "{time} [user:{sender}] text: {content}"
    session_assistant_line: str = "{time} [assistant] text: {content}"
    session_reply_line: str = "  ↳ reply to [{sender}] text: {content}"
    anchor_marker: str = " ← matches the query"
    assistant_line: str = "{time} [assistant]{anchor} text: {content}"
    user_line: str = "{time} [user:{sender}]{anchor} text: {content}"
    humor_quotes_header: str = "Recognizable memes and jokes from the chat (if appropriate):"
    humor_quote_line: str = "- {quote}"
    meme_header: str = (
        "Curated memes I know (use ONLY if it fits perfectly, max one per reply, "
        "paraphrase — never dump the definition, never force it):"
    )
    meme_line: str = "- {name}: {meaning} (appropriate: {usage})"
    meme_menu_header: str = (
        "Memes I can use if one fits (optional, max one per reply, "
        "never force, never dump the definition):"
    )
    meme_menu_line: str = "- {name} — {usage}"
    knowledge_header: str = "From my archive on the topic:"
    knowledge_block_line: str = "- [{kind}] {title}:\n  {content}"
    tone_note: str = ""
    owner_message_note: str = ""
    clarification_instruction: str = ""
    critic: CriticContent = Field(default_factory=CriticContent)
    generation: LLMGenerationProfiles = Field(default_factory=LLMGenerationProfiles)
    budget: PromptBudgetContent = Field(default_factory=PromptBudgetContent)

    def task_text(self) -> str:
        return (self.task or self.reply_instruction).strip()

    def answer_text(self) -> str:
        parts = [(self.answer or self.compose_instruction).strip()]
        if self.answer_examples.strip():
            parts.append(self.answer_examples.strip())
        return "\n\n".join(part for part in parts if part)

    def language_text(self) -> str:
        return self.language.strip()


class BotAccessMessages(BaseModel):
    private_chat: str
    required_user_missing: str
    required_user_not_configured: str
    wrong_chat: str = ""


class BotNotesMessages(BaseModel):
    owner_dm_only: str
    owner_only: str
    not_configured: str
    empty: str
    success: str
    error: str


class BotMessagesContent(BaseModel):
    welcome: str
    access: BotAccessMessages
    notes: BotNotesMessages


class DecisionContent(BaseModel):
    block_consecutive_replies: bool = True
    noise_max_words: int = 2
    noise_max_chars: int = 12
    default_bot_names: list[str] = Field(default_factory=list)
    trigger_keywords: list[str] = Field(default_factory=list)
    question_words: list[str] = Field(default_factory=list)
    modal_verbs: list[str] = Field(default_factory=list)
    # Short follow-up demands right after the bot's own reply ("а ещё" = "tell
    # me another one"). Used by the sender-aware continuation detector in both
    # the planner prefilter and the reaction-gate Tier-1. Empty = built-in
    # fallback set in app/decision/gate/continuation.py.
    continuation_phrases: list[str] = Field(default_factory=list)
    # Lightweight pre-planner Decision Gate prompt (see app/decision/gate/
    # reaction_gate.py). Placeholders: {message}, {recent}, {mentions_bot},
    # {reply_to_bot}, {reply_to_other_user}, {listen_window}. Empty string falls
    # back to the built-in DEFAULT_REACTION_GATE_PROMPT.
    reaction_gate_prompt: str = ""


class ProfanityContent(BaseModel):
    enabled: bool = False
    instruction: str = ""
    lemmas: dict[str, str] = Field(default_factory=dict)
    invariable: dict[str, str] = Field(default_factory=dict)


class MemoryContent(BaseModel):
    enabled: bool = True
    extraction_prompt: str = ""


class MetricsContent(BaseModel):
    enabled: bool = True
    extraction_prompt: str = ""
    feedback_header: str = "My mood and relationship notes about the sender:"
    feedback_line: str = (
        "- {name}: toxicity {toxicity}, trust {trust}/100, tone {distance}, mood {mood}"
    )
    # Cold-reply directive injected into the compose prompt when the sender is
    # stuck in a same-topic loop (annoyance >= feedback_annoyance_threshold).
    # Placeholders: {name}, {annoyance}. Empty = feature disabled.
    annoyance_note: str = ""


class PortraitContent(BaseModel):
    """Prompt for the hierarchical dossier summarization (person portraits)."""

    enabled: bool = True
    portrait_prompt: str = ""


class RagContent(BaseModel):
    turn_planner_prompt: str = ""
    query_rewrite_prompt: str = ""
    vector_min_score: float = 0.35

    @property
    def planner_prompt(self) -> str:
        if self.turn_planner_prompt.strip():
            return self.turn_planner_prompt
        return self.query_rewrite_prompt


class StickerDefContent(BaseModel):
    """One sticker of the bot's pack with the personality tags it can play."""

    name: str
    tags: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0.1, le=5.0)
    file_id: str | None = None
    index: int | None = None
    emoji: str | None = None
    description: str = ""


class StickersContent(BaseModel):
    """Sticker engagement: catalog + anti-spam gates.

    ``probability`` is the chance to actually send a sticker when the LLM tagged a
    reply; ``heuristic_probability`` — when the tag came from text heuristics.
    ``min_messages_between`` is the hard cap: no more than one sticker per that many
    bot replies in a chat.

    The sticker list here is the single source of truth for which tags exist: the
    LLM prompt is built from ``available_tags`` and the pipeline only passes on tags
    that are in this list, so the model can never suggest a sticker we don't have.
    """

    enabled: bool = True
    sticker_set_name: str = "VanessaBot"
    probability: float = Field(default=0.6, ge=0.0, le=1.0)
    heuristic_probability: float = Field(default=0.45, ge=0.0, le=1.0)
    min_messages_between: int = Field(default=3, ge=1, le=100)
    # Tags whose sticker fully replaces the text reply: the bot sends ONLY the
    # sticker because the image already carries the message (e.g. bemused 😐 has
    # a caption on it). The anti-spam gate is bypassed for these — the sticker IS
    # the reply.
    sticker_only_tags: list[str] = Field(default_factory=list)
    stickers: list[StickerDefContent] = Field(default_factory=list)

    @property
    def available_tags(self) -> tuple[str, ...]:
        """Personality tags that actually have a sticker in the pack.

        The single source of truth: the LLM may only suggest these tags and the
        pipeline only passes these on to the bot.
        """
        tags: set[str] = set()
        for sticker in self.stickers:
            tags.update(tag.lower() for tag in sticker.tags)
        return tuple(sorted(tags))

    def is_sticker_only(self, tag: str | None) -> bool:
        """True when the tag should be sent as a bare sticker, no text reply."""
        if not tag:
            return False
        lowered = tag.lower()
        return any(lowered == candidate.lower() for candidate in self.sticker_only_tags)

    def tag_lines(self) -> list[str]:
        """Human-readable tag list for the LLM prompt (tag + emoji + meaning).

        Each line advertises one tag with its sticker emoji hint and, when the
        sticker has a ``description``, a short note on when to use that emotion.
        """
        lines: list[str] = []
        seen: set[str] = set()
        for sticker in self.stickers:
            for tag in sticker.tags:
                key = tag.lower()
                if key in seen:
                    continue
                seen.add(key)
                hint = sticker.emoji or sticker.name
                label = f"- {key} ({hint})" if hint else f"- {key}"
                if sticker.description:
                    label += f" — {sticker.description.strip()}"
                lines.append(label)
        return lines


class MemeDefContent(BaseModel):
    """One curated internet meme the bot knows and may reference in dialogue.

    ``keywords`` are trigger words/phrases matched against the user's message
    (case-insensitive, word-boundary guarded). ``meaning`` and ``usage`` are shown
    to the LLM so it applies the meme correctly instead of inventing its own.
    """

    name: str
    keywords: list[str] = Field(default_factory=list)
    meaning: str = ""
    usage: str = ""
    example: str | None = None


class MemesContent(BaseModel):
    """Curated meme catalog + anti-spam gates.

    Memes are only offered to the composer when the turn planner says humor is
    appropriate (``humor_ok``) AND one of a meme's keywords matches the message
    AND the anti-spam gate allows it (``probability`` + a per-chat cooldown of
    ``min_messages_between`` bot replies, mirroring the sticker gate).
    """

    enabled: bool = True
    probability: float = Field(default=0.4, ge=0.0, le=1.0)
    min_messages_between: int = Field(default=8, ge=1, le=100)
    max_per_reply: int = Field(default=1, ge=1, le=5)
    offer_on_humor: bool = True
    offer_max: int = Field(default=6, ge=1, le=25)
    memes: list[MemeDefContent] = Field(default_factory=list)


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
