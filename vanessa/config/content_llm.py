from pydantic import BaseModel, Field


class LLMGenerationProfile(BaseModel):
    temperature: float = Field(default=0.8, ge=0.0, le=1.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=64, le=4096)
    presence_penalty: float = Field(default=0.0, ge=0.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=0.0, le=2.0)
    # Reasoning mode for the composer on DeepSeek V4 (thinking) models: forces a
    # deeper chain of thought before every answer, cutting logical errors. The
    # planner profile leaves it unset (None → the API's default normal mode), so
    # the gate stays fast and cheap. ``reasoning_effort`` is DeepSeek-only —
    # Claude ignores it (the param is stripped in the Claude provider).
    reasoning_effort: str | None = None

    def to_params(self):
        from vanessa.llm.generation import LLMGenerationParams  # noqa: PLC0415

        return LLMGenerationParams(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            reasoning_effort=self.reasoning_effort,
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
    # Live web-search results block cap (chars). The section also yields to the
    # global prompt cap by priority (web sits just below knowledge).
    web_blocks: int = 2000


class LLMContent(BaseModel):
    task: str = ""
    answer: str = ""
    answer_examples: str = ""
    language: str = ""
    reply_instruction: str = ""
    compose_instruction: str = ""
    # Explicit final-task line appended at the very end of the user prompt (the
    # recommended "final task / call to action" block) — a clear statement of
    # what to do right now, in the freshest part of the model's memory.
    final_task: str = ""
    sticker_instruction: str = ""
    # Marker line the composer uses to split a long reply into several short
    # messages (blocks) of 1-2 sentences each. The prompt (llm.yaml ``answer:``)
    # instructs the model to put this tag on its own line at the end of every
    # block except the last; message_blocks.py uses it as the single source of
    # truth when splitting the finished reply for delivery.
    block_marker: str = "[next]"
    context_header: str
    context_block_header: str = "<!-- Block {index} ({started_at} — {ended_at}) -->"
    context_block_separator: str = "\n\n"
    current_message_header: str
    reply_message_header: str = "<!-- The user's message is a reply to this message -->"
    aliases_header: str = (
        "Aliases — the same person is often called by different names in the chat"
        " (a Telegram nickname, a nickname, a shortened form). Treat them as ONE"
        " person:"
    )
    session_header: str = "<!-- Recent correspondence in the chat -->"
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
    # Live web search results ("the googling skill"): header + one line per hit
    # + a short directive on how to use them. Rendered only when the planner
    # flagged the turn for web search and the Retrieve stage found results.
    web_header: str = "<!-- Live web results on the topic -->"
    web_block_line: str = "- {title} ({url}):\n  {snippet}"
    web_instruction: str = (
        "The web results above are LIVE search results — fresh, external data. "
        "Answer from them when they are relevant; if they do not answer the "
        "question, say so honestly instead of inventing facts."
    )
    tone_note: str = ""
    owner_message_note: str = ""
    clarification_instruction: str = ""
    # Detail-level directives injected when the planner decides the reply should
    # be brief or detailed (TurnPlan.detail). Empty string = no directive for
    # that level; "normal" injects nothing (the default persona voice applies).
    detail_note_brief: str = ""
    detail_note_detailed: str = ""
    # Composer max_tokens override for "detailed" replies, so a fuller answer
    # is not truncated. 0 = use the base composer max_tokens.
    detailed_max_tokens: int = 0
    # Instruction injected when the turn carries an image (vision): tells the
    # model how to handle the attached picture (describe / OCR / be honest about
    # unclear text instead of hallucinating).
    vision_note: str = ""
    # Photo album section: a list of photos the bot could re-send (RAG-selected),
    # with the instruction to emit [photo:<index>] when one fits the message.
    # Rendered as XML-like <attachment> entries (the input-block convention).
    photo_album_header: str = "<!-- Photos I can send (from our chat, matched to the context) -->"
    photo_album_line: str = (
        '<attachment index="{index}" type="photo" sender="{sender}" time="{time}">\n'
        "  <description>{caption}</description>\n"
        "</attachment>"
    )
    photo_album_instruction: str = ""
    # Note appended when the user EXPLICITLY asked for a photo and the album is
    # non-empty: the [photo:<index>] marker is required, never just implied — the
    # model must not "say" it sent a photo without the marker that delivers it.
    photo_request_required_note: str = ""
    # Honesty directive rendered when the album is empty AND the user asked for a
    # photo: the model must refuse truthfully instead of faking a "sent" claim.
    photo_album_empty_note: str = ""
    generation: LLMGenerationProfiles = Field(default_factory=LLMGenerationProfiles)
    budget: PromptBudgetContent = Field(default_factory=PromptBudgetContent)

    def task_text(self) -> str:
        return (self.task or self.reply_instruction).strip()

    def answer_text(self) -> str:
        parts = [(self.answer or self.compose_instruction).strip()]
        if self.answer_examples.strip():
            parts.append(self.answer_examples.strip())
        return "\n\n".join(part for part in parts if part)

    # Answer-format rules only (no examples) — the "constraints" part of the
    # recommended order. Examples are kept separate (see ``examples_text``) so
    # they can sit in their own block after the constraints and before the
    # dynamic input data.
    def answer_format_text(self) -> str:
        return (self.answer or self.compose_instruction).strip()

    # Few-shot examples block (the recommended "examples" position), rendered as
    # a standalone section instead of being bundled into the answer format.
    def examples_text(self) -> str:
        return self.answer_examples.strip()

    # Explicit final-task line that closes the user prompt (the recommended
    # "final task / call to action" position, the freshest model memory).
    def final_task_text(self) -> str:
        return self.final_task.strip()

    def language_text(self) -> str:
        return self.language.strip()
