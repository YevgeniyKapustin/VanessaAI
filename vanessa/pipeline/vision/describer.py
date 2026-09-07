"""VRChat scene description — same vision client as PhotoCaptioner, different prompt."""

import logging

from openai import AsyncOpenAI

from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.core.protocols import SceneDescriberProtocol

logger = logging.getLogger(__name__)

SCENE_MAX_CHARS = 600

_SCENE_SYSTEM = (
    "You describe a VRChat first-person screenshot for an in-world avatar who "
    "must answer as if she is looking through these eyes right now. Write at most "
    f"{SCENE_MAX_CHARS} characters of plain prose. Cover: the world or setting; "
    "who is actually in frame (avatars, bodies, faces — only people you can see); "
    "readable signs, screens, or nameplates; and the camera (distance, height, "
    "what is centered). No intro, no markdown, no quotes, no advice. Do not invent "
    "people, objects, or text that are not in the image."
)


class SceneDescriber(SceneDescriberProtocol):
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._model = model or (
            settings.vision_photo_caption_model or settings.deepseek_vision_model
        )

    @property
    def _openai_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client

    async def describe(self, image: ImageAttachment) -> str | None:
        if not image or not image.data_url:
            return None
        try:
            response = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SCENE_SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe what you see in this screenshot now.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image.data_url},
                            },
                        ],
                    },
                ],
                max_tokens=256,
                temperature=0.3,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("scene_description_failed model=%s", self._model)
            return None
        if not text:
            return None
        return text[:SCENE_MAX_CHARS]
