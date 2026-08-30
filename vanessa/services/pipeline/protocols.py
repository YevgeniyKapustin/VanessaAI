from typing import Protocol

from vanessa.services.pipeline.context import TurnPipelineContext


class PipelineStage(Protocol):
    async def run(self, ctx: TurnPipelineContext) -> bool:
        """Return False to stop the pipeline (ctx.result must be set)."""


class FinalizeStageProtocol(PipelineStage):
    async def skip(self, ctx: TurnPipelineContext, *, reason: str) -> None:
        """Finish the turn without a reply (index + metrics + result).

        Used when a later stage decides the user's message does not need a
        reply.
        """
