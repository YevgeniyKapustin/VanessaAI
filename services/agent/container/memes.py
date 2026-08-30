from __future__ import annotations

from vanessa.config.content import get_content
from vanessa.pipeline.llm.memes import MemeCatalog, MemeDecider


class MemeStack:
    def __init__(
        self,
        catalog: MemeCatalog | None = None,
        decider: MemeDecider | None = None,
    ) -> None:
        if catalog is None or decider is None:
            memes = get_content().memes
            catalog = catalog or MemeCatalog(memes)
            decider = decider or MemeDecider(
                enabled=memes.enabled,
                probability=memes.probability,
                min_messages_between=memes.min_messages_between,
            )
        self.catalog = catalog
        self.decider = decider
