from typing import Protocol

from app.core.protocols import ContextRetrieverProtocol, TurnQueryProtocol
from app.llm.humor.humor_quotes import extract_humor_quotes
from app.llm.humor.humor_reflexion import reflexion_filter_humor_quotes
from app.llm.planner.turn_planner import TurnPlan
from app.services.orchestrator.orchestrator_config import OrchestratorConfig


class HumorPipelineProtocol(Protocol):
    async def fetch_quotes(
        self,
        turn_plan: TurnPlan,
        user_message: str,
    ) -> list[str]: ...


class HumorPipeline:
    def __init__(
        self,
        retriever: ContextRetrieverProtocol,
        turn_query: TurnQueryProtocol,
        config: OrchestratorConfig,
    ) -> None:
        self._retriever = retriever
        self._turn_query = turn_query
        self._config = config

    async def fetch_quotes(
        self,
        turn_plan: TurnPlan,
        user_message: str,
    ) -> list[str]:
        if not turn_plan.humor_ok or not turn_plan.humor_query.strip():
            return []

        humor_vector = await self._turn_query.embed_query(turn_plan.humor_query)
        humor_blocks = await self._retriever.search(
            query=turn_plan.humor_query,
            query_vector=humor_vector,
            fts_query=f"{turn_plan.humor_query} мем подкол шутка",
            top_k=self._config.humor_top_k,
            anchor_max=self._config.humor_anchor_max,
            window_before=self._config.humor_window_before,
            window_after=self._config.humor_window_after,
        )
        quotes = extract_humor_quotes(
            humor_blocks,
            max_quotes=self._config.humor_max_quotes,
            min_score=self._config.humor_min_quote_score,
        )
        return reflexion_filter_humor_quotes(
            quotes,
            humor_query=turn_plan.humor_query,
            user_message=user_message,
            max_quotes=self._config.humor_max_quotes,
        )
