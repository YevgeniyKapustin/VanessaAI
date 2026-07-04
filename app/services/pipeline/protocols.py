from typing import Protocol

from app.services.pipeline.context import TurnPipelineContext


class PipelineStage(Protocol):
    async def run(self, ctx: TurnPipelineContext) -> bool:
        """Return False to stop the pipeline (ctx.result must be set)."""
