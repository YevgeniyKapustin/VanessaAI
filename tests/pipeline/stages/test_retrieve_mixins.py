from types import SimpleNamespace
from unittest.mock import AsyncMock

from vanessa.config.settings import settings
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages.retrieve import RetrieveStage
from vanessa.pipeline.stages.retrieve_extras import _RetrieveExtrasMixin


class _Extras(_RetrieveExtrasMixin):
    def __init__(self, catalog=None, decider=None, web=None) -> None:
        self._meme_catalog = catalog
        self._meme_decider = decider
        self._web_search = web


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


async def test_retrieve_stage_commits_and_runs_extras(monkeypatch) -> None:
    monkeypatch.setattr(settings, "web_search_enabled", True)
    uow = SimpleNamespace(commit=AsyncMock())
    web = SimpleNamespace(search=AsyncMock(return_value=["hit"]))
    stage = RetrieveStage(uow, web_search=web)
    ctx = _ctx(web=True)
    assert await stage.run(ctx) is True
    uow.commit.assert_awaited_once()
    assert ctx.web_blocks == ["hit"]
    assert ctx.knowledge_blocks == []
    assert await RetrieveStage(None).run(_ctx()) is True
