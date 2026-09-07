from vanessa.core.protocols import SceneDescriberProtocol
from vanessa.pipeline.context import TurnPipelineContext


class SceneStage:
    """Fill ``ctx.scene_description`` from the VRChat screenshot, or leave None."""

    def __init__(self, describer: SceneDescriberProtocol) -> None:
        self._describer = describer

    async def run(self, ctx: TurnPipelineContext) -> bool:
        ctx.scene_description = None
        if not ctx.profile.scene:
            return True
        image = ctx.turn.scene_image
        if image is None:
            return True
        ctx.scene_description = await self._describer.describe(image)
        return True
