from pydantic import BaseModel, Field


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
    photo_placeholder: str = "[фото]"
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
    # Short follow-up demands right after the bot's own reply (Russian "and also"
    # = "tell me another one"). Used by the sender-aware continuation detector in both
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

    @property
    def planner_prompt(self) -> str:
        if self.turn_planner_prompt.strip():
            return self.turn_planner_prompt
        return self.query_rewrite_prompt


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
