import pytest

from vanessa.core.messages import ContextMessage
from vanessa.decision.gate.reaction_gate import ReactionGate

TEST_PROMPT = (
    "Message: {message}\n"
    "Recent:\n{recent}\n"
    "mentions_bot={mentions_bot} reply_to_bot={reply_to_bot} "
    "reply_to_other_user={reply_to_other_user} listen_window={listen_window}\n"
    "Answer YES or NO."
)

QUESTION_WORDS = ("что", "кто")
TRIGGER_KEYWORDS = ("помоги", "объясни")
MODAL_VERBS = ("можно",)
BOT_NAMES = ("ванесса", "vanessa")


class FakeCompleter:
    def __init__(self, response: str = "YES", *, error: bool = False):
        self.calls: list[tuple] = []
        self._response = response
        self._error = error

    async def complete(self, model, messages, *, kind="completion", **kwargs):
        self.calls.append((model, messages, kind, kwargs))
        if self._error:
            raise RuntimeError("boom")
        return self._response


def _gate(completer, **overrides) -> ReactionGate:
    defaults = dict(
        llm_client=completer,
        model="test-classifier",
        prompt=TEST_PROMPT,
        enabled=True,
        max_tokens=5,
        recent_window=4,
        bypass_reply_to_bot=True,
        bypass_listen_window=True,
        heuristics_enabled=True,
        continuation_enabled=True,
        continuation_phrases=("а ещё", "давай"),
        question_words=QUESTION_WORDS,
        trigger_keywords=TRIGGER_KEYWORDS,
        modal_verbs=MODAL_VERBS,
        bot_names=BOT_NAMES,
    )
    defaults.update(overrides)
    return ReactionGate(**defaults)


def _recent() -> list[ContextMessage]:
    return [
        ContextMessage(id=1, role="user", content="кто в дуо завтра", sender_name="Личь"),
        ContextMessage(id=2, role="user", content="я наверное", sender_name="Краб"),
    ]


def _follow_up_recent(sender: int = 1) -> list[ContextMessage]:
    """Bot just answered a user request; the user then follows up ("а ещё")."""
    return [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса расскажи анекдот",
            sender_telegram_id=sender,
            sender_name="Юзер",
        ),
        ContextMessage(
            id=2,
            role="assistant",
            content="Ладно, слушай. Идёт мужик по кладбищу...",
        ),
        ContextMessage(
            id=3,
            role="user",
            content="а ещё",
            sender_telegram_id=sender,
            sender_name="Юзер",
        ),
    ]


# --------------------------------------------------------------------------- #
# Tier 0 — bypasses / disabled (no LLM, no heuristics)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_disabled_always_responds_without_llm_call():
    completer = FakeCompleter()
    gate = _gate(completer, enabled=False)

    result = await gate.evaluate("ванесса, привет", [])

    assert result.respond is True
    assert result.reason == "disabled"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_bypasses_reply_to_bot_without_llm_call():
    completer = FakeCompleter()
    gate = _gate(completer)

    result = await gate.evaluate(
        "да, продолжай",
        _recent(),
        reply_to_bot=True,
    )

    assert result.respond is True
    assert result.reason == "reply_to_bot"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_bypasses_listen_window_without_llm_call():
    completer = FakeCompleter()
    gate = _gate(completer)

    result = await gate.evaluate(
        "а про токены?",
        _recent(),
        in_listen_window=True,
    )

    assert result.respond is True
    assert result.reason == "listen_window"
    assert completer.calls == []


# --------------------------------------------------------------------------- #
# Tier 1 — zero-cost deterministic short-circuit (no LLM call)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tier1_direct_address_at_start_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("ванесса, привет", [])

    assert result.respond is True
    assert result.reason == "heuristic_address"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_question_mark_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("а про токены?", [])

    assert result.respond is True
    assert result.reason == "heuristic_question"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_question_word_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("кто выиграл", [])

    assert result.respond is True
    assert result.reason == "heuristic_question"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_trigger_keyword_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("помоги собрать комп", [])

    assert result.respond is True
    assert result.reason == "heuristic_request"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_modal_verb_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("можно спросить", [])

    assert result.respond is True
    assert result.reason == "heuristic_request"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_imperative_request_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("напиши коротко", [])

    assert result.respond is True
    assert result.reason == "heuristic_request"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_noise_short_message_is_no_without_llm():
    completer = FakeCompleter("YES")
    gate = _gate(completer)

    # An unambiguous acknowledgment is definite noise — instant NO, no LLM.
    result = await gate.evaluate("ок", [])

    assert result.respond is False
    assert result.reason == "heuristic_noise"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_emoji_reaction_is_no_without_llm():
    completer = FakeCompleter("YES")
    gate = _gate(completer)

    result = await gate.evaluate("👍", [])

    assert result.respond is False
    assert result.reason == "heuristic_noise"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_ambiguous_short_message_defers_to_llm():
    completer = FakeCompleter("YES")
    gate = _gate(completer)

    # "го" ("let's go") is short but possibly meaningful — it is NOT hard
    # dropped as noise at Tier 1: it falls through to the Tier-2 LLM, which
    # decides when there is doubt.
    result = await gate.evaluate("го", [])

    assert result.respond is True
    assert result.reason == "yes"
    assert len(completer.calls) == 1


@pytest.mark.asyncio
async def test_heuristics_disabled_falls_through_to_llm():
    completer = FakeCompleter("YES")
    gate = _gate(completer, heuristics_enabled=False)

    result = await gate.evaluate("ванесса, привет", [])

    # With Tier 1 off, even a clear request is classified by the LLM.
    assert result.respond is True
    assert result.reason == "yes"
    assert len(completer.calls) == 1


# --------------------------------------------------------------------------- #
# Tier 1 — sender-aware continuation follow-ups ("а ещё" after the bot's reply)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tier1_continuation_follow_up_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate(
        "а ещё",
        _follow_up_recent(sender=1),
        sender_telegram_id=1,
    )

    # The user who just got the bot's reply demands more — explicit request,
    # zero LLM call.
    assert result.respond is True
    assert result.reason == "heuristic_continuation"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_continuation_requires_matching_sender():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    # A different sender's "а ещё" is not an addressed continuation — the
    # ambiguous tail falls through to the LLM tier.
    result = await gate.evaluate(
        "а ещё",
        _follow_up_recent(sender=1),
        sender_telegram_id=2,
    )

    assert result.respond is False
    assert result.reason == "no"
    assert len(completer.calls) == 1


@pytest.mark.asyncio
async def test_tier1_continuation_beats_noise_short_circuit():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    # "давай" alone is noise (1 word), but as a continuation demand from the
    # user the bot just answered it is a request — checked before noise.
    recent = _follow_up_recent(sender=1)
    recent[-1] = ContextMessage(
        id=3,
        role="user",
        content="давай",
        sender_telegram_id=1,
        sender_name="Юзер",
    )

    result = await gate.evaluate("давай", recent, sender_telegram_id=1)

    assert result.respond is True
    assert result.reason == "heuristic_continuation"
    assert completer.calls == []


@pytest.mark.asyncio
async def test_tier1_continuation_disabled_falls_through_to_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer, continuation_enabled=False)

    result = await gate.evaluate(
        "а ещё",
        _follow_up_recent(sender=1),
        sender_telegram_id=1,
    )

    assert result.respond is False
    assert result.reason == "no"
    assert len(completer.calls) == 1


# --------------------------------------------------------------------------- #
# Tier 2 — ambiguous tail only (LLM call)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_ambiguous_message_positive_verdict_via_llm():
    completer = FakeCompleter("YES")
    gate = _gate(completer)

    result = await gate.evaluate("я думаю ванесса с этим справится", _recent())

    assert result.respond is True
    assert result.reason == "yes"
    assert len(completer.calls) == 1


@pytest.mark.asyncio
async def test_ambiguous_message_negative_verdict_short_circuits():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("я думаю ванесса с этим справится", _recent())

    assert result.respond is False
    assert result.reason == "no"
    assert len(completer.calls) == 1


@pytest.mark.asyncio
async def test_ambiguous_response_fails_open_to_respond():
    completer = FakeCompleter("maybe")
    gate = _gate(completer)

    result = await gate.evaluate("смотрите какой кот", _recent())

    assert result.respond is True
    assert result.reason == "ambiguous"


@pytest.mark.asyncio
async def test_error_fails_open_to_respond():
    completer = FakeCompleter(error=True)
    gate = _gate(completer)

    result = await gate.evaluate("смотрите какой кот", _recent())

    assert result.respond is True
    assert result.reason == "error"


@pytest.mark.asyncio
async def test_uses_fast_model_and_tiny_max_tokens_budget():
    completer = FakeCompleter("NO")
    gate = _gate(completer, model="deepseek-chat", max_tokens=5)

    await gate.evaluate("я думаю ванесса с этим справится", _recent())

    model, _messages, kind, kwargs = completer.calls[0]
    assert model == "deepseek-chat"
    assert kind == "reaction_gate"
    assert kwargs["max_tokens"] == 5
    assert kwargs["temperature"] == 0.0


@pytest.mark.asyncio
async def test_prompt_includes_message_recent_and_flags():
    completer = FakeCompleter("NO")
    gate = _gate(completer)
    recent = _recent()

    await gate.evaluate(
        "смотрите какой кот",
        recent,
        mentions_bot=True,
        reply_to_other_user=True,
    )

    prompt = completer.calls[0][1][0]["content"]
    assert "смотрите какой кот" in prompt
    assert "Личь" in prompt
    assert "mentions_bot=yes" in prompt
    assert "reply_to_bot=no" in prompt
    assert "reply_to_other_user=yes" in prompt
    assert "listen_window=no" in prompt


@pytest.mark.asyncio
async def test_tier1_direct_address_with_imperative_is_yes_without_llm():
    completer = FakeCompleter("NO")
    gate = _gate(completer)

    result = await gate.evaluate("ванесса не тормози я написал", [])

    # "ванесса + императив" starts with the bot name — a direct address, no LLM.
    assert result.respond is True
    assert result.reason == "heuristic_address"
    assert completer.calls == []


def test_configured_prompt_teaches_imperative_is_direct_address():
    from vanessa.config.content import get_content

    prompt = get_content().decision.reaction_gate_prompt
    assert "ванесса, не тормози, я написал" in prompt
    assert "imperative" in prompt.lower()
    assert "naming the bot is not that" in prompt


def test_default_prompt_teaches_imperative_is_direct_address():
    from vanessa.decision.gate.reaction_gate import DEFAULT_REACTION_GATE_PROMPT

    assert "ванесса, не тормози, я написал" in DEFAULT_REACTION_GATE_PROMPT
    assert "Общение между собой" in DEFAULT_REACTION_GATE_PROMPT


@pytest.mark.asyncio
async def test_recent_context_is_bounded():
    completer = FakeCompleter("NO")
    gate = _gate(completer, recent_window=1)
    recent = [
        ContextMessage(id=1, role="user", content="старое", sender_name="А"),
        ContextMessage(id=2, role="user", content="новое", sender_name="Б"),
    ]

    await gate.evaluate("смотрите какой кот", recent)

    prompt = completer.calls[0][1][0]["content"]
    assert "новое" in prompt
    assert "старое" not in prompt
