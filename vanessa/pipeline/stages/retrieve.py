import asyncio
import logging

from vanessa.core.protocols import HermesHealthProtocol, UnitOfWorkProtocol
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.broker.dispatcher import TaskDispatcher
from vanessa.infrastructure.websearch.protocols import WebSearchService
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.llm.memes import MemeCatalog, MemeDecider
from vanessa.pipeline.stages.retrieve_extras import _RetrieveExtrasMixin
from vanessa.pipeline.stages.retrieve_hermes import run_hermes_step

logger = logging.getLogger("vanessa.pipeline.stages")


class RetrieveStage(_RetrieveExtrasMixin):
    """Collect extra compose inputs: web results, memes, the Hermes ask."""

    def __init__(
        self,
        uow: UnitOfWorkProtocol | None,
        *,
        meme_catalog: MemeCatalog | None = None,
        meme_decider: MemeDecider | None = None,
        web_search: WebSearchService | None = None,
        hermes: HermesHealthProtocol | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self._uow = uow
        self._meme_catalog = meme_catalog
        self._meme_decider = meme_decider
        # Live web search (the "googling" skill); None disables it (default).
        self._web_search = web_search
        # Hermes health probe + the worker task queue; None disables Hermes.
        self._hermes = hermes
        self._dispatcher = dispatcher

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if self._uow is not None:
            await self._uow.commit()

        assert ctx.turn_plan is not None
        # Live web search (the "googling" skill) and the Hermes ask when the
        # planner flagged the turn. Both fail open and run side by side.
        await asyncio.gather(
            self._run_web_search(ctx),
            run_hermes_step(ctx, self._hermes, self._dispatcher),
        )
        self._maybe_attach_memes(ctx)

        logger.info(
            "turn_stage retrieve request_id=%s web=%s meme_blocks=%s "
            "meme_menu=%s web_ms=%.1f hermes=%s",
            get_request_id(),
            len(ctx.web_blocks),
            len(ctx.meme_blocks),
            len(ctx.meme_menu),
            ctx.web_ms,
            ctx.hermes_status,
        )
        return True
