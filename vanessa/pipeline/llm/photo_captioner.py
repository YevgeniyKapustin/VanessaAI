"""Short photo captions for RAG-by-meaning enrichment.

After a photo turn, a background job asks the (cheap) vision model for a one-line
Russian description of the photo and stores it in ``messages.photo_caption``. The
FTS search_vector is then recomputed to include it, so a bare photo («[фото]»)
becomes findable "by meaning" when the user later asks e.g. «скинь то фото где
кот» — and the caption shows up in the photo album offered to the compose model.
"""

import logging

from openai import AsyncOpenAI

from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.core.protocols import PhotoCaptionerProtocol

logger = logging.getLogger(__name__)

_CAPTION_SYSTEM = (
    "You write one-line photo labels for a chat bot's search index. "
    "Describe what is in the image in ONE short Russian phrase (at most {max_chars} "
    "characters): the subject and scene, plus any readable text if it matters. "
    "No intro, no quotes, no trailing punctuation."
)


class PhotoCaptioner(PhotoCaptionerProtocol):
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

    async def generate(self, attachment: ImageAttachment) -> str | None:
        """Return a short Russian caption for the image, or None on failure."""
        if not attachment or not attachment.data_url:
            return None
        system = _CAPTION_SYSTEM.format(
            max_chars=settings.vision_photo_caption_max_chars
        )
        try:
            response = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this photo in one short phrase.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": attachment.data_url},
                            },
                        ],
                    },
                ],
                max_tokens=64,
                temperature=0.3,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("photo_caption_generation_failed model=%s", self._model)
            return None
        if not text:
            return None
        return text[: settings.vision_photo_caption_max_chars]
