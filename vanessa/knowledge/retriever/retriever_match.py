"""Alias matching and bot-self-card filters for KnowledgeRetriever."""

from __future__ import annotations

from vanessa.config.content import get_bot_name_aliases


class RetrieverMatchMixin:
    @staticmethod
    def _alias_query_hit(alias: str, normalized: str) -> bool:
        if not normalized:
            return False
        if alias in normalized:
            return True
        return normalized in alias

    @staticmethod
    def _append_alias_hit(
        hits: list[dict],
        seen: set[str],
        alias: str,
        entry: dict,
        normalized: str,
        limit: int,
    ) -> bool:
        file = entry.get("file")
        if not file or file in seen:
            return False
        if not RetrieverMatchMixin._alias_query_hit(alias, normalized):
            return False
        seen.add(file)
        hits.append(entry)
        if not limit:
            return False
        return len(hits) >= limit

    @staticmethod
    def _match_aliases(aliases: dict, query: str, limit: int = 0) -> list[dict]:
        normalized = query.strip().lower()
        hits: list[dict] = []
        seen: set[str] = set()
        for alias, entry in sorted(aliases.items()):
            if RetrieverMatchMixin._append_alias_hit(
                hits, seen, alias, entry, normalized, limit
            ):
                break
        return hits

    @staticmethod
    def _bot_name_set() -> set[str]:
        return {
            name.strip().lower()
            for name in get_bot_name_aliases()
            if name.strip()
        }

    @staticmethod
    def _add_self_path(
        self_paths: set[str], alias: object, entry: object, bot_names: set[str]
    ) -> None:
        if not isinstance(entry, dict):
            return
        if str(alias).strip().lower() not in bot_names:
            return
        file = entry.get("file")
        if file:
            self_paths.add(str(file))

    @staticmethod
    def _self_card_paths(aliases: dict) -> set[str]:
        """People-card paths that are the bot itself (aliases overlap bot names).

        The bot's own dossier ("ванесса" = self) is a normal card in the vault;
        marking it lets retrieval suppress it when another person is the target,
        keeping the block budget for the actually queried people.
        """
        if not isinstance(aliases, dict):
            return set()
        bot_names = RetrieverMatchMixin._bot_name_set()
        if not bot_names:
            return set()
        self_paths: set[str] = set()
        for alias, entry in aliases.items():
            RetrieverMatchMixin._add_self_path(
                self_paths, alias, entry, bot_names
            )
        return self_paths

    @staticmethod
    def _filter_self_cards(files: list[str], self_paths: set[str]) -> list[str]:
        """Drop the bot's own card(s) when at least one real person is targeted."""
        others = [path for path in files if path not in self_paths]
        return others if others else list(files)
