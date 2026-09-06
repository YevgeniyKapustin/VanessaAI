"""Render vault notes as KnowledgeBlocks for KnowledgeRetriever."""

from __future__ import annotations

from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.knowledge.vectors.chunks import split_dossier_chunks


class RetrieverBlocksMixin:
    def _use_chunked_detail(self, note, *, detail: bool) -> bool:
        if not detail:
            return False
        if not self._is_person(note):
            return False
        return self._people_chunks_enabled

    async def _blocks_for_entry(
        self, entry: dict, *, detail: bool
    ) -> list[KnowledgeBlock]:
        file = entry.get("file")
        if not file:
            return []
        note = await self._vault.read_note(file)
        if note is None:
            return []
        if self._use_chunked_detail(note, detail=detail):
            return self._chunk_blocks(
                note, list(range(self._people_detail_blocks))
            )
        return [self._block_from_note(note, people_detail=detail)]

    async def _read_blocks(
        self,
        entries: list[dict],
        *,
        detail: bool = False,
    ) -> list[KnowledgeBlock]:
        blocks: list[KnowledgeBlock] = []
        for entry in entries:
            blocks.extend(await self._blocks_for_entry(entry, detail=detail))
        return blocks

    def _chunk_blocks(
        self,
        note,
        indices: list[int],
    ) -> list[KnowledgeBlock]:
        """Build one KnowledgeBlock per dossier chunk index for a People card."""
        chunks = split_dossier_chunks(
            note.body or "",
            self._people_chunk_chars,
            self._people_chunk_overlap,
        )
        base_title = str(note.meta.get("id") or note.relative_path)
        result: list[KnowledgeBlock] = []
        for index in indices:
            if 0 <= index < len(chunks):
                # Label each block so the model can tell fragments apart and
                # reference the right one ("второй фрагмент про доллары").
                title = (
                    f"{base_title} · фрагмент {index + 1}"
                    if len(chunks) > 1
                    else base_title
                )
                result.append(
                    KnowledgeBlock(
                        path=note.relative_path,
                        title=title,
                        kind="person",
                        content=chunks[index],
                        chunk_index=index,
                    )
                )
        return result

    def _block_from_note(self, note, *, people_detail: bool = False) -> KnowledgeBlock:
        kind = str(note.meta.get("type") or "")
        if kind == "person":
            content = self._people_content(note, detail=people_detail)
        elif kind == "archive":
            # Safety net: archive notes are huge; only a bounded slice may ever
            # be rendered as a whole note (normally they are chunk-injected).
            content = self._trim(note.body or "", self._people_raw_max_chars)
        else:
            content = note.body or ""
        return KnowledgeBlock(
            path=note.relative_path,
            title=str(note.meta.get("id") or note.relative_path),
            kind=kind,
            content=content,
        )

    def _people_content(self, note, *, detail: bool) -> str:
        """People-block body: compact portrait, or the raw (bounded) dossier.

        Background context (``detail=False``) injects the LLM portrait stored in
        the card's frontmatter, falling back to a bounded raw slice when no
        portrait has been generated yet. A concrete-fact question
        (``detail=True``) pulls the raw dossier, bounded to keep the prompt lean
        (when per-chunk embeddings are disabled; with them, ``_chunk_blocks``
        supplies the top matching dossier blocks instead).
        """
        meta = note.meta or {}
        portrait = str(meta.get("portrait") or "").strip()
        if not detail and portrait:
            return portrait
        body = (note.body or "").strip()
        return self._trim(body, self._people_raw_max_chars)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        head = text[:limit]
        # Cut at the last sentence/line boundary inside the cap to avoid a
        # mid-sentence break.
        for boundary in (head.rfind(". "), head.rfind(".\n"), head.rfind("\n")):
            if boundary >= limit // 2:
                return head[: boundary + 1].rstrip() + "\n…"
        return head.rstrip() + "\n…"

    def _detail_cap(self, *, detail: bool) -> int:
        """Max blocks returned: allow the full chunk budget on detail queries."""
        if detail and self._people_chunks_enabled:
            return max(self._max_blocks, self._people_detail_blocks)
        return self._max_blocks

    @staticmethod
    def _is_person(note) -> bool:
        return str(note.meta.get("type") or "") == "person"

    @staticmethod
    def _dedupe(blocks: list[KnowledgeBlock]) -> list[KnowledgeBlock]:
        seen: set[tuple[str, int | None]] = set()
        result: list[KnowledgeBlock] = []
        for block in blocks:
            key = (block.path, block.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            result.append(block)
        return result
