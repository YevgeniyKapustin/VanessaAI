from html import escape as _xml_escape

from pydantic import BaseModel, Field, field_validator


class StickerDefContent(BaseModel):
    """One sticker of the bot's pack with the personality tags it can play."""

    name: str
    tags: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0.1, le=5.0)
    file_id: str | None = None
    index: int | None = None
    emoji: str | None = None
    description: str = ""


def _first_sticker_for_tags(
    stickers: list[StickerDefContent],
) -> list[tuple[str, StickerDefContent]]:
    seen: set[str] = set()
    unique: list[tuple[str, StickerDefContent]] = []
    for sticker in stickers:
        for tag in sticker.tags:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append((key, sticker))
    return unique


def _prompt_tag_line(key: str, sticker: StickerDefContent) -> str:
    hint = sticker.emoji or sticker.name
    label = f"- {key} ({hint})" if hint else f"- {key}"
    if not sticker.description:
        return label
    return f"{label} — {sticker.description.strip()}"


def _xml_tag_inner(sticker: StickerDefContent) -> str:
    hint = sticker.emoji or sticker.name
    label = f"{hint} ({sticker.name})" if hint else sticker.name
    note = sticker.description.strip()
    if not note:
        return label
    return f"{label} — {note}"


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
    # Per-tag overrides of ``probability``: warm/positive tags (love, delight)
    # send more often, «дежурные» tags (thinking) less, so they don't get stale.
    # Falls back to the base ``probability``/``heuristic_probability`` otherwise.
    tag_probability: dict[str, float] = Field(default_factory=dict)
    # Soft fallback for tags the model invents but the pack doesn't have: the
    # parser maps them to the closest real tag or drops them (see sticker_tag.py).
    tag_aliases: dict[str, str] = Field(default_factory=dict)
    # The sticker-system cheat-sheet rendered as XML into the LLM prompt.
    system_description: str = ""
    tag_rules: list[str] = Field(default_factory=list)
    # Tags whose sticker fully replaces the text reply: the bot sends ONLY the
    # sticker because the image already carries the message (e.g. bemused 😐 has
    # a caption on it). The anti-spam gate is bypassed for these — the sticker IS
    # the reply.
    sticker_only_tags: list[str] = Field(default_factory=list)
    stickers: list[StickerDefContent] = Field(default_factory=list)

    @field_validator("tag_probability")
    @classmethod
    def _validate_tag_probability(cls, value: dict[str, float]) -> dict[str, float]:
        for tag, p in value.items():
            if not 0.0 <= p <= 1.0:
                raise ValueError(
                    f"tag_probability[{tag}] must be within [0, 1], got {p}"
                )
        return value

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
        return [
            _prompt_tag_line(key, sticker)
            for key, sticker in _first_sticker_for_tags(self.stickers)
        ]

    def _xml_available_tag_lines(self) -> list[str]:
        lines: list[str] = ["  <available_tags>"]
        for key, sticker in _first_sticker_for_tags(self.stickers):
            inner = _xml_tag_inner(sticker)
            lines.append(
                f'    <tag name="{_xml_escape(key)}">{_xml_escape(inner)}</tag>'
            )
        lines.append("  </available_tags>")
        return lines

    def _xml_tag_rule_lines(self) -> list[str]:
        if not self.tag_rules:
            return []
        lines = ["  <tag_rules>"]
        lines.extend(
            f"    <rule>{_xml_escape(rule.strip())}</rule>"
            for rule in self.tag_rules
            if rule.strip()
        )
        lines.append("  </tag_rules>")
        return lines

    def xml_system_block(self) -> str:
        """Render the sticker cheat-sheet as an XML block for the LLM prompt.

        Built entirely from the yaml so the tag list can never drift from the
        pack: ``<description>`` from ``system_description``, one ``<tag>`` per
        available tag (emoji + sticker name + usage note) and ``<tag_rules>``
        from ``tag_rules``.
        """
        lines: list[str] = ["<sticker_system>"]
        if self.system_description.strip():
            body = " ".join(
                part.strip()
                for part in self.system_description.splitlines()
                if part.strip()
            )
            lines.append(f"  <description>{_xml_escape(body)}</description>")
        lines.extend(self._xml_available_tag_lines())
        lines.extend(self._xml_tag_rule_lines())
        lines.append("</sticker_system>")
        return "\n".join(lines)
