"""Compose one announcement: code-built facts, model-written bullets.

Any LLM failure, an empty answer or a lost header falls back to plain item
titles, so the news always reaches the chat.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import tzinfo

from services.worker.announce.card_html import card_for
from services.worker.announce.content import WatchSpec
from services.worker.announce.mention import Participant
from services.worker.announce.models import Announcement
from services.worker.announce.prompt import (
    build_footer,
    build_header,
    build_prompt,
    clean_bullets,
    fallback_bullets,
)
from services.worker.hermes.compose import chat_request, final_text, truncate_message
from vanessa.core.protocols import LLMChatCompleter
from vanessa.llm.generation import LLMGenerationParams
from vanessa.pipeline.llm.format.answer_tag import is_untagged_reply
from vanessa.pipeline.llm.tagged_reply import request_tagged

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Composed:
    """One announcement in both shapes: the plain text and the rich card."""

    text: str
    rich_html: str | None = None


class AnnounceComposer:
    """LLM boundary for one watch (completer + persona prompt + wording)."""

    def __init__(
        self,
        completer: LLMChatCompleter | None,
        *,
        model: str,
        system_prompt: str,
        spec: WatchSpec,
        generation: LLMGenerationParams,
        zone: tzinfo,
        links: dict[str, str] | None = None,
    ) -> None:
        # completer=None turns the rewrite off: the fallback text is posted.
        self._completer = completer
        self._model = model
        self._system = system_prompt
        self._spec = spec
        self._generation = generation
        self._zone = zone
        self._links = links or {}

    async def compose(
        self,
        announcement: Announcement,
        *,
        stand_ready: bool | None,
        mention: Participant | None = None,
    ) -> str:
        """Header, bullets, footer — separated by blank lines."""
        composed = await self.compose_all(
            announcement, stand_ready=stand_ready, mention=mention
        )
        return composed.text

    async def compose_all(
        self,
        announcement: Announcement,
        *,
        stand_ready: bool | None,
        mention: Participant | None = None,
    ) -> Composed:
        """The text a watch always keeps, plus the card when the spec asks."""
        author = mention.markdown if mention is not None else ""
        header = build_header(
            self._spec,
            announcement,
            zone=self._zone,
            author=author,
            links=self._links,
        )
        body = list(await self._bullets(announcement, stand_ready=stand_ready))
        if stand_ready is False:
            body.append(self._spec.stand_down_line)
        blocks = [header]
        if body:
            blocks.append("\n".join(body))
        footer = build_footer(
            self._spec, announcement, zone=self._zone, links=self._links
        )
        if footer:
            blocks.append(footer)
        text = truncate_message("\n\n".join(block for block in blocks if block.strip()))
        return Composed(text=text, rich_html=self._card(header, body, footer, announcement))

    def _card(
        self,
        header: str,
        bullets: list[str],
        footer: str,
        announcement: Announcement,
    ) -> str | None:
        """The folded card; None when the watch posts plain text only."""
        if not self._spec.rich:
            return None
        return card_for(
            header=header,
            bullets=bullets,
            items=announcement.items,
            total=announcement.item_total,
            footer=footer,
        )

    async def _bullets(
        self, announcement: Announcement, *, stand_ready: bool | None
    ) -> list[str]:
        """Human bullets from the model; raw titles if it failed."""
        if self._completer is None:
            return fallback_bullets(self._spec, announcement)
        raw = await self._rewrite(announcement, stand_ready=stand_ready)
        if raw is None:
            return fallback_bullets(self._spec, announcement)
        return self._pick(announcement, clean_bullets(raw))

    def _pick(self, announcement: Announcement, bullets: list[str]) -> list[str]:
        """Model bullets; a lone change is always named, even a technical one."""
        if bullets:
            return bullets
        if announcement.item_total == 1:
            return fallback_bullets(self._spec, announcement)
        return []

    async def _rewrite(
        self, announcement: Announcement, *, stand_ready: bool | None
    ) -> str | None:
        try:
            raw = await self._complete(announcement, stand_ready=stand_ready)
        except Exception as exc:  # noqa: BLE001 - any LLM failure → fallback
            # The type only: provider errors may echo the prompt.
            logger.warning(
                "announce_llm_failed watch=%s key=%s error=%s",
                self._spec.id,
                announcement.key,
                type(exc).__name__,
            )
            return None
        if is_untagged_reply(raw):
            # No final-answer boundary after the retry → the plain bullets.
            logger.warning(
                "announce_llm_untagged watch=%s key=%s chars=%s",
                self._spec.id,
                announcement.key,
                len(raw),
            )
            return None
        return final_text(raw)

    async def _complete(
        self, announcement: Announcement, *, stand_ready: bool | None
    ) -> str:
        completer = self._completer
        assert completer is not None
        user = build_prompt(
            self._spec, announcement, stand_ready=stand_ready, zone=self._zone
        )

        async def create(*, strict: bool) -> str:
            messages, extra = chat_request(
                completer, self._system, user, strict=strict
            )
            return await completer.complete(
                self._model,
                messages,
                kind=f"{self._spec.kind}_announcement",
                **self._generation.to_llm_kwargs(),
                **extra,
            )

        return await request_tagged(create, str, model=self._model)


__all__ = ["AnnounceComposer"]
