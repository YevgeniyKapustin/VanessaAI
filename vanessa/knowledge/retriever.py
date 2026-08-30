"""KnowledgeRetriever: intent-routed lookup over the vault indexes.

The bot never scans the whole vault: it consults per-folder ``_index.yaml``
manifests and resolves aliases/terms to files in O(1), then reads the matched
notes. Which parts are queried is driven by the turn intent:

- ``people`` — resolve nicknames → participant dossiers;
- ``lore``   — glossary aliases + event titles (also always queried for humor);
- ``culture`` — recommendation entries by kind/status;
- ``logs``   — recent weekly/daily logs.

When an embedding provider and a knowledge vector store are configured,
:meth:`fetch_semantic` additionally ranks the vault notes by embedding
similarity to the composed query — this is the primary semantic search (the
vault's notes are already semantic summaries), with alias/token matching kept
as an exact-hit complement.
"""

from __future__ import annotations

import logging
import re

from vanessa.config.content import get_bot_name_aliases
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
)
from vanessa.infrastructure.observability.metrics import record_rag_search
from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.knowledge.chunks import split_dossier_chunks
from vanessa.knowledge.entities import resolve_mentioned_people
from vanessa.knowledge.format import (
    CULTURE,
    LOGS,
    LORE_EVENTS,
    LORE_GLOSSARY,
    PEOPLE,
)
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import knowledge_kind_for_path

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-zа-яё]{3,}", re.IGNORECASE)

# Compaction archive area (top-level, excluded from the People alias index but
# embedded for RAG). Its notes are chunked like dossiers, so a retrieved
# archive hit must be rendered as the matching chunk, never the whole file.
_ARCHIVE_PREFIX = "_archive/"


class KnowledgeRetriever:
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
        *,
        max_blocks: int = 3,
        people_max_blocks: int = 1,
        embeddings: EmbeddingProviderProtocol | None = None,
        vector_store: KnowledgeVectorStoreProtocol | None = None,
        vector_top_k: int | None = None,
        vector_min_score: float | None = None,
        people_raw_max_chars: int | None = None,
        people_chunks_enabled: bool | None = None,
        people_chunk_chars: int | None = None,
        people_chunk_overlap: int | None = None,
        people_detail_blocks: int | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)
        self._max_blocks = max_blocks
        self._people_max_blocks = people_max_blocks
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._vector_top_k = (
            vector_top_k
            if vector_top_k is not None
            else settings.knowledge_vector_top_k
        )
        self._vector_min_score = (
            vector_min_score
            if vector_min_score is not None
            else settings.knowledge_vector_min_score
        )
        self._people_raw_max_chars = (
            people_raw_max_chars
            if people_raw_max_chars is not None
            else settings.knowledge_people_raw_max_chars
        )
        self._people_chunks_enabled = (
            settings.knowledge_people_chunks_enabled
            if people_chunks_enabled is None
            else people_chunks_enabled
        )
        self._people_chunk_chars = (
            people_chunk_chars
            if people_chunk_chars is not None
            else settings.knowledge_people_chunk_chars
        )
        self._people_chunk_overlap = (
            people_chunk_overlap
            if people_chunk_overlap is not None
            else settings.knowledge_people_chunk_overlap
        )
        self._people_detail_blocks = (
            people_detail_blocks
            if people_detail_blocks is not None
            else settings.knowledge_people_detail_blocks
        )

    async def fetch(
        self,
        *,
        knowledge_indexes: tuple[str, ...] = (),
        knowledge_query: str = "",
        humor_ok: bool = False,
        humor_query: str = "",
        user_message: str = "",
        people_detail: bool = False,
        people_files: list[str] | None = None,
    ) -> list[KnowledgeBlock]:
        if not self._vault.is_configured:
            return []
        indexes = set(knowledge_indexes)
        if humor_ok and humor_query.strip():
            indexes.add("lore")
        if not indexes:
            return []

        query = (knowledge_query or user_message or "").strip()
        blocks: list[KnowledgeBlock] = []
        if "people" in indexes:
            if people_files:
                # Deterministic multi-person retrieval: fetch exactly the
                # resolved dossiers (all mentioned people), bounded. The bot's
                # own card is dropped when a real person is the target so it
                # never consumes the budget meant for the queried people.
                people_index = await self._index.load_folder(PEOPLE)
                raw_aliases = (
                    people_index.get("aliases")
                    if isinstance(people_index, dict)
                    else None
                )
                people_aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
                target_files = self._filter_self_cards(
                    people_files,
                    self._self_card_paths(people_aliases),
                )
                entries = [{"file": path} for path in target_files]
                blocks.extend(
                    await self._read_blocks(
                        entries[: self._people_max_blocks],
                        detail=people_detail,
                    )
                )
            else:
                blocks.extend(await self._fetch_people(query, detail=people_detail))
        if "lore" in indexes:
            blocks.extend(await self._fetch_lore(query or humor_query or ""))
        if "culture" in indexes:
            blocks.extend(await self._fetch_culture(query))
        if "logs" in indexes:
            blocks.extend(await self._fetch_logs())

        blocks = self._dedupe(blocks)
        logger.info(
            "knowledge_fetch indexes=%s query=%r blocks=%s",
            sorted(indexes),
            query,
            len(blocks),
        )
        return blocks[: self._detail_cap(detail=people_detail)]

    async def _fetch_people(self, query: str, *, detail: bool = False) -> list[KnowledgeBlock]:
        people_index = await self._index.load_folder(PEOPLE)
        aliases = people_index.get("aliases", {})
        hits = self._match_aliases(aliases, query, limit=self._people_max_blocks)
        return await self._read_blocks(hits, detail=detail)

    async def _fetch_lore(self, query: str) -> list[KnowledgeBlock]:
        glossary = (await self._index.load_folder(LORE_GLOSSARY)).get("glossary", {})
        aliases = glossary.get("aliases", {})
        hits = self._match_aliases(aliases, query)

        events = (await self._index.load_folder(LORE_EVENTS)).get("events", [])
        query_tokens = {t.lower() for t in _TOKEN.findall(query.lower())}
        for event in events:
            title = str(event.get("title") or "")
            title_tokens = {t.lower() for t in _TOKEN.findall(title.lower())}
            if query_tokens and (query_tokens & title_tokens):
                hits.append(event)
        return await self._read_blocks(hits)

    async def _fetch_culture(self, query: str) -> list[KnowledgeBlock]:
        culture = await self._index.load_folder(CULTURE)
        query_tokens = {t.lower() for t in _TOKEN.findall(query.lower())}
        hits: list[dict] = []
        for kind, items in culture.items():
            kind_match = kind in query_tokens
            for item in items:
                title = str(item.get("title") or "")
                title_tokens = {t.lower() for t in _TOKEN.findall(title.lower())}
                if not query or kind_match or (query_tokens & title_tokens):
                    hits.append(item)
        return await self._read_blocks(hits)

    async def _fetch_logs(self) -> list[KnowledgeBlock]:
        logs = await self._index.load_folder(LOGS)
        hits: list[dict] = []
        for sub in ("weekly", "daily"):
            entries = list(logs.get(sub, []))
            entries.sort(key=lambda item: str(item.get("file") or ""), reverse=True)
            hits.extend(entries)
        return await self._read_blocks(hits)

    @staticmethod
    def _match_aliases(aliases: dict, query: str, limit: int = 0) -> list[dict]:
        normalized = query.strip().lower()
        hits: list[dict] = []
        seen: set[str] = set()
        for alias, entry in sorted(aliases.items()):
            file = entry.get("file")
            if not file or file in seen:
                continue
            if normalized and (alias in normalized or normalized in alias):
                seen.add(file)
                hits.append(entry)
                if limit and len(hits) >= limit:
                    break
        return hits

    @staticmethod
    def _self_card_paths(aliases: dict) -> set[str]:
        """People-card paths that are the bot itself (aliases overlap bot names).

        The bot's own dossier ("ванесса" = self) is a normal card in the vault;
        marking it lets retrieval suppress it when another person is the target,
        keeping the block budget for the actually queried people.
        """
        if not isinstance(aliases, dict):
            return set()
        bot_names = {
            name.strip().lower()
            for name in get_bot_name_aliases()
            if name.strip()
        }
        if not bot_names:
            return set()
        self_paths: set[str] = set()
        for alias, entry in aliases.items():
            if not isinstance(entry, dict):
                continue
            if str(alias).strip().lower() in bot_names:
                file = entry.get("file")
                if file:
                    self_paths.add(str(file))
        return self_paths

    @staticmethod
    def _filter_self_cards(files: list[str], self_paths: set[str]) -> list[str]:
        """Drop the bot's own card(s) when at least one real person is targeted."""
        others = [path for path in files if path not in self_paths]
        return others if others else list(files)

    async def fetch_semantic(
        self,
        query: str = "",
        *,
        knowledge_indexes: tuple[str, ...] = (),
        knowledge_query: str = "",
        humor_ok: bool = False,
        humor_query: str = "",
        user_message: str = "",
        top_k: int | None = None,
        people_detail: bool = False,
        people_files: list[str] | None = None,
    ) -> list[KnowledgeBlock]:
        """Semantic retrieval over the vault notes.

        Embeds the composed query and returns the top matching notes (filtered by
        the requested kinds and a minimum score), merged with exact alias/token
        hits. Without an embedding/vector configuration it falls back to
        :meth:`fetch`.

        ``people_detail`` controls how People blocks are rendered: ``False``
        (default) injects the compact LLM portrait for background context;
        ``True`` injects the person's dossier in depth — with per-chunk
        embeddings enabled this is the top ``people_detail_blocks`` strongest
        text blocks of the dossier (ranked by embedding score), otherwise the
        raw (bounded) dossier as before.

        ``people_files`` (from the deterministic mention resolver) forces the
        People retrieval to exactly these dossiers — so a multi-person question
        ("крабер и личь") pulls every mentioned person, not a single match.
        """
        if not self._vault.is_configured:
            return []
        if self._embeddings is None or self._vector_store is None:
            return await self.fetch(
                knowledge_indexes=knowledge_indexes,
                knowledge_query=knowledge_query,
                humor_ok=humor_ok,
                humor_query=humor_query,
                user_message=user_message,
                people_detail=people_detail,
                people_files=people_files,
            )

        effective = (knowledge_query or query or user_message or "").strip()
        if not effective:
            return []

        indexes = set(knowledge_indexes)
        if humor_ok and humor_query.strip():
            indexes.add("lore")

        chunked_detail = (
            people_detail
            and self._people_chunks_enabled
            and "people" in indexes
        )

        # People targeting & self-card handling. The bot's own card ("ванесса" =
        # self) must never compete for the block budget when a real person is the
        # target. Deterministically resolved people (resolver output + the
        # planner query's alias) are guaranteed to survive the result cap, so a
        # stale vector index cannot silently drop the named person.
        self_paths: set[str] = set()
        target_files: list[str] = []
        has_non_self_target = False
        people_aliases: dict = {}
        if "people" in indexes:
            people_index = await self._index.load_folder(PEOPLE)
            raw_aliases = (
                people_index.get("aliases")
                if isinstance(people_index, dict)
                else None
            )
            people_aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
            self_paths = self._self_card_paths(people_aliases)
            query_text = (knowledge_query or query or user_message or "").strip()
            for entry in self._match_aliases(people_aliases, query_text):
                file = entry.get("file")
                if file and file not in target_files:
                    target_files.append(file)
            for path in people_files or []:
                if path not in target_files:
                    target_files.append(path)
            has_non_self_target = any(
                path not in self_paths for path in target_files
            )

        tracer = get_tracer()
        async with tracer.span(
            name="retrieve:knowledge_vault",
            metadata={
                "query": effective,
                "indexes": sorted(indexes) or "all",
                "user_message": user_message,
            },
        ) as span:
            query_vector = await self._embeddings.embed(effective)
            hits = await self._vector_store.search(
                query_vector,
                limit=top_k or self._vector_top_k,
            )
            from vanessa.infrastructure.observability.metrics import record_knowledge_search

            record_knowledge_search("qdrant", hits=len(hits))
            span.update(
                output={
                    "hits": [
                        {
                            "path": hit.get("path"),
                            "kind": hit.get("kind"),
                            "title": hit.get("title"),
                            "score": hit.get("score"),
                        }
                        for hit in hits[:12]
                    ]
                }
            )
            fts_notes = await self._vault.search_fts(
                effective, limit=top_k or self._vector_top_k
            )
            record_knowledge_search("postgres_fts", hits=len(fts_notes))

            vector_blocks: list[KnowledgeBlock] = []
            seen_paths: set[str] = set()
            people_chunk_hits: dict[str, list[dict]] = {}
            for hit in hits:
                if float(hit["score"]) < self._vector_min_score:
                    continue
                if indexes and hit["kind"] not in indexes:
                    continue
                path = hit["path"]
                if has_non_self_target and path in self_paths:
                    # The bot's own dossier is not the target — don't let it
                    # crowd out (or fill the budget meant for) real people.
                    continue
                chunk_index = hit.get("chunk_index")
                if (
                    hit["kind"] == "people"
                    and chunk_index is not None
                    and (chunked_detail or path.startswith(_ARCHIVE_PREFIX))
                ):
                    # Archive notes are chunked: always inject the matching
                    # chunk, otherwise a whole archive file would blow up the
                    # prompt.
                    people_chunk_hits.setdefault(path, []).append(hit)
                    continue
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                note = await self._vault.read_note(path)
                if note is None:
                    continue
                vector_blocks.append(
                    self._block_from_note(note, people_detail=people_detail)
                )

            # People detail: one block per top matching dossier chunk (ranked by
            # embedding score), so a "reveal the person in depth" task gets the
            # strongest blocks of the same file, not a single short portrait.
            for path, path_hits in people_chunk_hits.items():
                if path in seen_paths:
                    continue
                note = await self._vault.read_note(path)
                if note is None:
                    continue
                seen_paths.add(path)
                path_hits.sort(
                    key=lambda hit: float(hit["score"]), reverse=True
                )
                indices = [
                    int(hit["chunk_index"])
                    for hit in path_hits[: self._people_detail_blocks]
                ]
                vector_blocks.extend(self._chunk_blocks(note, indices))

            for note in fts_notes:
                if note.relative_path in seen_paths:
                    continue
                if indexes:
                    kind = knowledge_kind_for_path(note.relative_path)
                    if kind is None or kind not in indexes:
                        continue
                seen_paths.add(note.relative_path)
                vector_blocks.append(
                    self._block_from_note(note, people_detail=people_detail)
                )

            alias_blocks = await self.fetch(
                knowledge_indexes=tuple(sorted(indexes)),
                knowledge_query=knowledge_query,
                humor_ok=humor_ok,
                humor_query=humor_query,
                user_message=user_message,
                people_detail=people_detail,
                people_files=target_files or None,
            )
            # Resolved people come first (guaranteed to survive the cap), then
            # vector enrichment — a named person is never truncated by vector
            # -only hits that happen to rank above it.
            merged = self._dedupe(alias_blocks + vector_blocks)
            missing_targets = sorted(
                path
                for path in target_files
                if path not in self_paths
                and path not in seen_paths
                and path not in people_chunk_hits
            )
            if missing_targets:
                # Index-freshness guard: a deterministically resolved person with
                # no vector hit means the Qdrant "knowledge" collection is stale
                # for that card (rebuild with scripts/reindex_knowledge_vectors.py).
                logger.warning(
                    "knowledge_semantic_target_missing_from_vectors files=%s "
                    "-> run scripts/reindex_knowledge_vectors.py",
                    missing_targets,
                )
            logger.info(
                "knowledge_fetch_semantic query=%r vector_hits=%s blocks=%s "
                "indexes=%s people_chunks=%s",
                effective,
                len(hits),
                len(merged),
                sorted(indexes) or "all",
                len(people_chunk_hits),
            )
            top_score = float(hits[0]["score"]) if hits else None
            record_rag_search("semantic", hits=len(merged), top_score=top_score)
            return merged[: self._detail_cap(detail=people_detail)]

    async def resolve_people(
        self,
        message: str,
        recent_messages: list[ContextMessage] | None = None,
        *,
        recent_window: int | None = None,
    ) -> list[str]:
        """Deterministic People-card files mentioned in message + recent window.

        A cheap alias scan over the People index (no LLM). Used by the compose
        path to pick which dossiers to inject and to decide whether the
        deterministic resolver may force People retrieval.
        """
        if not self._vault.is_configured:
            return []
        people_index = await self._index.load_folder(PEOPLE)
        return resolve_mentioned_people(
            message,
            recent_messages,
            people_index,
            recent_window=(
                recent_window
                if recent_window is not None
                else settings.knowledge_participant_recent_window
            ),
        )

    async def _read_blocks(
        self,
        entries: list[dict],
        *,
        detail: bool = False,
    ) -> list[KnowledgeBlock]:
        blocks: list[KnowledgeBlock] = []
        for entry in entries:
            file = entry.get("file")
            if not file:
                continue
            note = await self._vault.read_note(file)
            if note is None:
                continue
            if detail and self._is_person(note) and self._people_chunks_enabled:
                # Deterministic (no-embedding) chunked detail: split the dossier
                # and take the leading blocks — the semantic path ranks them.
                blocks.extend(
                    self._chunk_blocks(note, list(range(self._people_detail_blocks)))
                )
            else:
                blocks.append(self._block_from_note(note, people_detail=detail))
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
