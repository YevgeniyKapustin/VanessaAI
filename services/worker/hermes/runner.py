"""One Hermes job: start a run, wait for it, post one follow-up.

Logs carry run ids, outcomes and durations only — never Hermes' answer
text or HTTP bodies.
"""

from __future__ import annotations

import logging
import time

from services.worker.hermes.blocks import followup_blocks
from services.worker.hermes.compose import FollowupComposer, truncate_message
from services.worker.hermes.html_file import HtmlFile, SplitAnswer, split_html_file
from services.worker.hermes.payload import HermesAsk
from services.worker.hermes.progress import ProgressLine
from services.worker.hermes.report_style import styled_file
from services.worker.hermes.trace import bind_job, trace_answer, trace_query, trace_sent
from vanessa.contracts.outbound import (
    DOCUMENT_MAX_CHARS,
    QUESTION_MAX_CHARS,
    OutboundDocument,
    OutboundMessage,
)
from vanessa.infrastructure.hermes import (
    HermesClient,
    HermesUnavailableError,
    HermesWaitResult,
    hermes_session_id,
    wait_for_output,
)
from vanessa.infrastructure.observability.metrics.metrics_hermes_jobs import (
    record_hermes_job,
)
from vanessa.pipeline.llm.format.message_blocks import strip_block_markers

logger = logging.getLogger(__name__)

OUTBOUND_SOURCE = "hermes"
# ``<style>\n`` + ``\n</style>`` around the report stylesheet.
_STYLE_TAGS_CHARS = 32


class HermesRunner:
    """Runs one ask end to end. Every outcome publishes exactly one message."""

    def __init__(
        self,
        client: HermesClient,
        composer: FollowupComposer,
        broker,
        *,
        outbound_stream: str,
        instructions: str,
        poll_seconds: float,
        max_wait_seconds: float,
        file_max_bytes: int = 262_144,
        report_css: str = "",
        progress: ProgressLine | None = None,
        progress_seconds: float = 0.0,
    ) -> None:
        self._client = client
        self._composer = composer
        self._broker = broker
        self._stream = outbound_stream
        self._instructions = instructions.strip() or None
        self._poll_seconds = poll_seconds
        self._max_wait_seconds = max_wait_seconds
        self._css = report_css
        self._progress = progress
        self._progress_seconds = progress_seconds
        # Bytes >= chars, so the file plus our stylesheet stays under the
        # wire cap.
        room = DOCUMENT_MAX_CHARS - len(report_css) - _STYLE_TAGS_CHARS
        self._file_max_bytes = max(0, min(file_max_bytes, room))

    async def run(self, ask: HermesAsk) -> None:
        bind_job(ask)
        started = time.monotonic()
        answer, outcome, failure = await self._ask_hermes(ask)
        trace_answer(answer, outcome)
        split = split_html_file(answer or "", max_bytes=self._file_max_bytes)
        file_task = self._composer.file_task(
            attached=split.file is not None, refused=bool(split.problems)
        )
        text = await self._composer.compose(
            ask,
            split.text or None,
            file_task=file_task,
            elapsed_seconds=time.monotonic() - started,
            failure_reason=failure,
        )
        if ask.bot_peer:
            # Agents get one flat message; keep the sentence punctuation the
            # block splitter would strip at every break.
            flat = strip_block_markers(text).strip()
            blocks = [truncate_message(" ".join(flat.split()))]
        else:
            blocks = followup_blocks(text) or [self._composer.fallback_line()]
        file = styled_file(split.file, self._css)
        trace_sent(blocks, file)
        await self._broker.publish(self._stream, _outbound(ask, blocks, file))
        seconds = time.monotonic() - started
        record_hermes_job(outcome, seconds)
        _log_done(ask, outcome, failure, seconds, blocks, split)

    async def _ask_hermes(self, ask: HermesAsk) -> tuple[str | None, str, str]:
        """Answer, outcome for metrics, and why there is no answer."""
        try:
            result = await self._run_and_wait(ask)
        except HermesUnavailableError:
            # The error text may carry the tunnel URL; log the fact only.
            logger.warning("hermes_unavailable chat_id=%s", ask.telegram_chat_id)
            return None, "unavailable", ""
        if not result.answer:
            return None, "no_answer", result.failure
        return result.answer, "answered", ""

    async def _run_and_wait(self, ask: HermesAsk) -> HermesWaitResult:
        run_started = time.monotonic()
        trace_query(ask, self._instructions)
        run_id = await self._client.start_run(
            ask.question,
            session_id=hermes_session_id(ask.channel, ask.telegram_chat_id),
            idempotency_key=ask.idempotency_key,
            instructions=self._instructions,
        )
        logger.info(
            "hermes_run_started run_id=%s chat_id=%s", run_id, ask.telegram_chat_id
        )
        result = await wait_for_output(
            self._client,
            run_id,
            poll_seconds=self._poll_seconds,
            max_wait_seconds=self._max_wait_seconds,
            progress_after_seconds=self._progress_seconds,
            on_progress=self._progress_callback(ask),
        )
        logger.info(
            "hermes_run_finished run_id=%s answered=%s failure=%s seconds=%.1f",
            run_id,
            bool(result.answer),
            result.failure or "-",
            time.monotonic() - run_started,
        )
        return result

    def _progress_callback(self, ask: HermesAsk):
        """One heartbeat per progress window; None when progress is off."""
        if self._progress is None or self._progress_seconds <= 0:
            return None

        async def tell(elapsed_seconds: float) -> None:
            await self._progress.tell(ask, elapsed_seconds)

        return tell


def _log_done(
    ask: HermesAsk,
    outcome: str,
    failure: str,
    seconds: float,
    blocks: list[str],
    split: SplitAnswer,
) -> None:
    logger.info(
        "hermes_job_done chat_id=%s outcome=%s failure=%s seconds=%.1f len=%s "
        "messages=%s file_bytes=%s file_refused=%s",
        ask.telegram_chat_id,
        outcome,
        failure or "-",
        seconds,
        sum(len(block) for block in blocks),
        len(blocks),
        split.file.size_bytes if split.file else 0,
        ",".join(split.problems) or "-",
    )


def _outbound(
    ask: HermesAsk, blocks: list[str], file: HtmlFile | None
) -> OutboundMessage:
    """One outbound item: the first block (the caption with a file), then
    the other blocks as separate messages."""
    document = (
        OutboundDocument(file_name=file.file_name, content=file.content)
        if file is not None
        else None
    )
    return OutboundMessage(
        channel="telegram",
        telegram_chat_id=ask.telegram_chat_id,
        text=blocks[0],
        reply_to_message_id=ask.telegram_message_id,
        source=OUTBOUND_SOURCE,
        document=document,
        more_texts=blocks[1:],
        question=ask.question[:QUESTION_MAX_CHARS],
    )
