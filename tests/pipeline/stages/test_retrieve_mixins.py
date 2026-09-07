from types import SimpleNamespace
from unittest.mock import AsyncMock

from vanessa.config.settings import settings
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages.retrieve_extras import _RetrieveExtrasMixin
from vanessa.pipeline.stages.retrieve_knowledge import _RetrieveKnowledgeMixin


class _Extras(_RetrieveExtrasMixin):
    def __init__(self, catalog=None, decider=None, web=None) -> None:
        self._meme_catalog = catalog
        self._meme_decider = decider
        self._web_search = web


class _Knowledge(_RetrieveKnowledgeMixin):
    def __init__(self, knowledge=None) -> None:
        self._knowledge = knowledge


def _ctx(*, humor: bool = True, web: bool = False) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=1,
            message="расскажи про ваню",
            sender_telegram_id=2,
        )
    )
    ctx.turn_plan = TurnPlan(
        original="x",
        text="x",
        skip_search=False,
        humor_ok=humor,
        web_search=web,
        web_query="news",
        knowledge_indexes=(),
    )
    ctx.sender_name = "Ada"
    return ctx


def test_memes_skipped_without_plan_or_catalog() -> None:
    extras = _Extras()
    ctx = _ctx()
    ctx.turn_plan = None
    extras._maybe_attach_memes(ctx)
    extras = _Extras(catalog=SimpleNamespace(enabled=True), decider=None)
    extras._maybe_attach_memes(_ctx())


def test_memes_matched_and_menu() -> None:
    catalog = SimpleNamespace(
        enabled=True,
        offer_on_humor=True,
        match=lambda _text: [SimpleNamespace(id="m1")],
        offerable=lambda: [SimpleNamespace(id="menu")],
    )
    decider = SimpleNamespace(decide=lambda _chat: True, register_meme=lambda _chat: None)
    extras = _Extras(catalog=catalog, decider=decider)
    ctx = _ctx()
    extras._maybe_attach_memes(ctx)
    assert ctx.meme_blocks
    catalog.match = lambda _text: []
    ctx2 = _ctx()
    extras._maybe_attach_memes(ctx2)
    assert ctx2.meme_menu


async def test_web_search_found_empty_and_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "web_search_enabled", True)
    extras = _Extras(web=SimpleNamespace(search=AsyncMock(return_value=["hit"])))
    ctx = _ctx(web=True)
    await extras._run_web_search(ctx)
    assert ctx.web_blocks == ["hit"]
    extras._web_search.search = AsyncMock(return_value=[])
    ctx = _ctx(web=True)
    await extras._run_web_search(ctx)
    extras._web_search.search = AsyncMock(side_effect=RuntimeError("down"))
    ctx = _ctx(web=True)
    await extras._run_web_search(ctx)
    assert ctx.web_blocks == []
    monkeypatch.setattr(settings, "web_search_enabled", False)
    ctx = _ctx(web=True)
    await extras._run_web_search(ctx)


async def test_knowledge_resolve_and_fetch() -> None:
    class Knowledge:
        async def resolve_people(self, *_a, **_k):
            return ["People/ada.md"]

        async def fetch_semantic(self, *_a, **_k):
            return [SimpleNamespace(content="note")]

    stage = _Knowledge(Knowledge())
    ctx = _ctx()
    files = await stage._resolve_people_files(ctx)
    assert files
    indexes = stage._knowledge_indexes(ctx, files)
    assert "people" in indexes
    assert await stage._fetch_knowledge(ctx, "q", indexes, files) is True
    ctx.turn_plan = TurnPlan(original="x", text="x", skip_search=True)
    stage._mark_embed_ms(ctx)


async def test_knowledge_fail_open() -> None:
    class Boom:
        async def resolve_people(self, *_a, **_k):
            raise RuntimeError("people")

        async def fetch_semantic(self, *_a, **_k):
            raise RuntimeError("qdrant")

    stage = _Knowledge(Boom())
    ctx = _ctx()
    assert await stage._resolve_people_files(ctx) == []
    assert await stage._fetch_knowledge(ctx, "q", ["people"], []) is False
    empty = _Knowledge(None)
    assert await empty._resolve_people_files(ctx) == []
    assert await empty._fetch_knowledge(ctx, "q", [], []) is False
