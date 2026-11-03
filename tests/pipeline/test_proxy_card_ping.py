"""A card ping from an agent guarantees a work lookup with the card id."""

from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.proxy.card_ping import apply_proxy_card_lookup, card_ids

PING = (
    "Женя, фон спринта: ABC-123 (в работе остались копии) — без движения, "
    "26 ч. Двигай или скажи, что мешает."
)


def _plan(**overrides) -> TurnPlan:
    values = {
        "original": PING,
        "text": PING,
        "skip_search": True,
        "should_reply": True,
    }
    values.update(overrides)
    return TurnPlan(**values)


def test_card_ids_read_work_cards_only() -> None:
    assert card_ids(PING) == ("ABC-123",)
    assert card_ids("ABC и 26 ч") == ()
    assert card_ids("ABC-123, затем ABC-123 и VAN-12") == ("ABC-123", "VAN-12")


def test_proxy_card_ping_forces_the_lookup() -> None:
    result = apply_proxy_card_lookup(_plan(), PING, proxy_question=True)

    assert result.ask_hermes is True
    assert "ABC-123" in result.hermes_query
    assert "что мешает" in result.hermes_query
    assert len(result.hermes_query) <= 500


def test_non_proxy_ping_keeps_the_plan() -> None:
    plan = _plan()

    assert apply_proxy_card_lookup(plan, PING, proxy_question=False) is plan


def test_good_query_with_the_card_is_kept() -> None:
    query = "Что с карточкой ABC-123: что осталось и что мешает?"
    plan = _plan(ask_hermes=True, hermes_query=query)

    assert apply_proxy_card_lookup(plan, PING, proxy_question=True) is plan


def test_query_without_the_card_gets_the_ping() -> None:
    plan = _plan(ask_hermes=True, hermes_query="статус задачи")

    result = apply_proxy_card_lookup(plan, PING, proxy_question=True)

    assert result.ask_hermes is True
    assert "ABC-123" in result.hermes_query
