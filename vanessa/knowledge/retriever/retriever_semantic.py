"""Semantic (embedding) retrieval over vault notes."""

from __future__ import annotations

from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.schema import KnowledgeBlock


def _effective_query(knowledge_query: str, query: str, user_message: str) -> str:
    return (knowledge_query or query or user_message or "").strip()


def _semantic_indexes(
    knowledge_indexes: tuple[str, ...], humor_query: str, *, humor_ok: bool
) -> set[str]:
    indexes = set(knowledge_indexes)
    if humor_ok and humor_query.strip():
        indexes.add("lore")
    return indexes


def _people_aliases_map(people_index: object) -> dict:
    if not isinstance(people_index, dict):
        return {}
    raw = people_index.get("aliases")
    if isinstance(raw, dict):
        return raw
    return {}


def _unique_alias_files(match_aliases, aliases: dict, query_text: str) -> list[str]:
    target_files: list[str] = []
    for entry in match_aliases(aliases, query_text):
        file = entry.get("file")
        if not file or file in target_files:
            continue
        target_files.append(file)
    return target_files


def _extend_unique(target_files: list[str], extra: list[str] | None) -> None:
    for path in extra or []:
        if path in target_files:
            continue
        target_files.append(path)


class RetrieverSemanticMixin:
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

        effective = _effective_query(knowledge_query, query, user_message)
        if not effective:
            return []

        indexes = _semantic_indexes(
            knowledge_indexes, humor_query, humor_ok=humor_ok
        )
        chunked_detail = self._chunked_people_detail(
            indexes, people_detail=people_detail
        )
        self_paths, target_files, has_non_self_target = (
            await self._people_search_targets(
                indexes, knowledge_query, query, user_message, people_files
            )
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
            return await self._semantic_span(
                span,
                effective=effective,
                indexes=indexes,
                knowledge_query=knowledge_query,
                humor_ok=humor_ok,
                humor_query=humor_query,
                user_message=user_message,
                top_k=top_k,
                people_detail=people_detail,
                chunked_detail=chunked_detail,
                self_paths=self_paths,
                target_files=target_files,
                has_non_self_target=has_non_self_target,
            )

    def _chunked_people_detail(self, indexes: set[str], *, people_detail: bool) -> bool:
        if not people_detail:
            return False
        if not self._people_chunks_enabled:
            return False
        return "people" in indexes

    async def _people_search_targets(
        self,
        indexes: set[str],
        knowledge_query: str,
        query: str,
        user_message: str,
        people_files: list[str] | None,
    ) -> tuple[set[str], list[str], bool]:
        if "people" not in indexes:
            return set(), [], False
        people_aliases = _people_aliases_map(await self._index.load_folder(PEOPLE))
        self_paths = self._self_card_paths(people_aliases)
        query_text = _effective_query(knowledge_query, query, user_message)
        target_files = _unique_alias_files(
            self._match_aliases, people_aliases, query_text
        )
        _extend_unique(target_files, people_files)
        has_non_self_target = any(path not in self_paths for path in target_files)
        return self_paths, target_files, has_non_self_target
