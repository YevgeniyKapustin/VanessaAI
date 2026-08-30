from dataclasses import dataclass

from vanessa.config.content import StickerDefContent


@dataclass(slots=True)
class StickerDef:
    """A single sticker of the pack plus the personality tags it can play."""

    name: str
    tags: tuple[str, ...] = ()
    weight: float = 1.0
    file_id: str | None = None
    index: int | None = None
    emoji: str | None = None
    resolved_file_id: str | None = None

    @classmethod
    def from_content(cls, item: StickerDefContent) -> "StickerDef":
        return cls(
            name=item.name,
            tags=tuple(tag.lower() for tag in item.tags),
            weight=item.weight,
            file_id=item.file_id or None,
            index=item.index,
            emoji=item.emoji,
        )

    @property
    def available_file_id(self) -> str | None:
        """Explicit config id takes priority over the runtime-resolved one."""
        return self.file_id or self.resolved_file_id


@dataclass(frozen=True, slots=True)
class StickerPick:
    """Result of a successful decision: which tag and which file to send."""

    tag: str
    file_id: str


class StickerCatalog:
    """Sticker registry indexed by personality tag."""

    def __init__(self, set_name: str, stickers: list[StickerDef]) -> None:
        self.set_name = set_name
        self._stickers = list(stickers)
        self._by_tag: dict[str, list[StickerDef]] = {}
        for sticker in self._stickers:
            for tag in sticker.tags:
                self._by_tag.setdefault(tag, []).append(sticker)

    @property
    def stickers(self) -> list[StickerDef]:
        return list(self._stickers)

    @property
    def has_resolved_files(self) -> bool:
        return any(sticker.available_file_id for sticker in self._stickers)

    def stickers_for_tag(self, tag: str) -> list[StickerDef]:
        """Stickers with the tag that actually have a file id to send."""
        return [
            sticker
            for sticker in self._by_tag.get(tag.lower(), ())
            if sticker.available_file_id
        ]
