"""Build KnowledgeBlocks from scored vector hits and FTS notes."""

from __future__ import annotations

from vanessa.knowledge.retriever.retriever_hit_filters import (
    fts_kind_excluded,
    is_people_chunk_hit,
    skip_vector_hit,
)
from vanessa.knowledge.schema import KnowledgeBlock


class RetrieverHitBlocksMixin:
    async def _block_from_vault_path(
        self,
        path: str,
        *,
        people_detail: bool,
    ) -> KnowledgeBlock | None:
        note = await self._vault.read_note(path)
        if note is None:
            return None
        return self._block_from_note(note, people_detail=people_detail)

    async def _people_blocks_from_path_hits(
        self,
        path: str,
        path_hits: list[dict],
    ) -> list[KnowledgeBlock] | None:
        note = await self._vault.read_note(path)
        if note is None:
            return None
        path_hits.sort(key=lambda hit: float(hit["score"]), reverse=True)
        indices = [
            int(hit["chunk_index"])
            for hit in path_hits[: self._people_detail_blocks]
        ]
        return self._chunk_blocks(note, indices)

    async def _append_path_block(
        self,
        path: str,
        *,
        people_detail: bool,
        vector_blocks: list[KnowledgeBlock],
        seen_paths: set[str],
    ) -> None:
        if path in seen_paths:
            return
        seen_paths.add(path)
        block = await self._block_from_vault_path(
            path, people_detail=people_detail
        )
        if block is None:
            return
        vector_blocks.append(block)

    async def _absorb_vector_hit(
        self,
        hit,
        *,
        indexes: set[str],
        people_detail: bool,
        chunked_detail: bool,
        self_paths: set[str],
        has_non_self_target: bool,
        vector_blocks: list[KnowledgeBlock],
        seen_paths: set[str],
        people_chunk_hits: dict[str, list[dict]],
    ) -> None:
        if skip_vector_hit(
            hit,
            min_score=self._vector_min_score,
            indexes=indexes,
            self_paths=self_paths,
            has_non_self_target=has_non_self_target,
        ):
            return
        path = hit["path"]
        if is_people_chunk_hit(hit, chunked_detail=chunked_detail):
            people_chunk_hits.setdefault(path, []).append(hit)
            return
        await self._append_path_block(
            path,
            people_detail=people_detail,
            vector_blocks=vector_blocks,
            seen_paths=seen_paths,
        )

    async def _blocks_from_hits(
        self,
        hits: list,
        *,
        indexes: set[str],
        people_detail: bool,
        chunked_detail: bool,
        self_paths: set[str],
        has_non_self_target: bool,
    ) -> tuple[list[KnowledgeBlock], set[str], dict[str, list[dict]]]:
        vector_blocks: list[KnowledgeBlock] = []
        seen_paths: set[str] = set()
        people_chunk_hits: dict[str, list[dict]] = {}
        for hit in hits:
            await self._absorb_vector_hit(
                hit,
                indexes=indexes,
                people_detail=people_detail,
                chunked_detail=chunked_detail,
                self_paths=self_paths,
                has_non_self_target=has_non_self_target,
                vector_blocks=vector_blocks,
                seen_paths=seen_paths,
                people_chunk_hits=people_chunk_hits,
            )
        return vector_blocks, seen_paths, people_chunk_hits

    async def _append_people_chunks(
        self,
        vector_blocks: list[KnowledgeBlock],
        seen_paths: set[str],
        people_chunk_hits: dict[str, list[dict]],
    ) -> None:
        for path, path_hits in people_chunk_hits.items():
            if path in seen_paths:
                continue
            blocks = await self._people_blocks_from_path_hits(path, path_hits)
            if blocks is None:
                continue
            seen_paths.add(path)
            vector_blocks.extend(blocks)

    async def _append_fts_blocks(
        self,
        vector_blocks: list[KnowledgeBlock],
        seen_paths: set[str],
        fts_notes,
        indexes: set[str],
        *,
        people_detail: bool,
    ) -> None:
        for note in fts_notes:
            if note.relative_path in seen_paths:
                continue
            if fts_kind_excluded(note.relative_path, indexes):
                continue
            seen_paths.add(note.relative_path)
            vector_blocks.append(
                self._block_from_note(note, people_detail=people_detail)
            )
