import pytest

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentDetector
from vanessa.pipeline.decision.detectors.noise import NoiseFilter, NoiseHeuristics
from vanessa.pipeline.decision.detectors.rate_limit import RateLimiter
from vanessa.pipeline.decision.detectors.session_window import SessionWindowAnalyzer
from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker
from vanessa.pipeline.decision.engine import DecisionEngine
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason


@pytest.fixture
def intent_detector() -> IntentDetector:
    return IntentDetector()


@pytest.fixture
def trigger_checker() -> TriggerKeywordChecker:
    return TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи"))


def test_intent_detects_question_mark(intent_detector: IntentDetector):
    result = intent_detector.detect("Как дела?")

    assert result.detected is True
    assert result.has_question is True


def test_intent_detects_bot_name(intent_detector: IntentDetector):
    result = intent_detector.detect("Vanessa, подскажи")

    assert result.detected is True
    assert result.mentions_bot is True


def test_intent_ignores_small_talk(intent_detector: IntentDetector):
    result = intent_detector.detect("ок понял")

    assert result.detected is False


def test_trigger_detects_keyword(trigger_checker: TriggerKeywordChecker):
    result = trigger_checker.detect("Помоги с задачей")

    assert result.detected is True
    assert result.keyword == "помоги"


def test_session_window_requires_request_in_history(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="просто болтовня"),
    ]

    assert analyzer.has_active_request(messages) is False


def test_session_window_detects_prior_question(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="Vanessa, как дела?"),
        ContextMessage(id=2, role="assistant", content="Хорошо"),
    ]

    assert analyzer.has_active_request(messages) is True


def test_session_window_closes_after_dismissal(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="Vanessa, как дела?"),
        ContextMessage(id=2, role="assistant", content="Хорошо"),
        ContextMessage(id=3, role="user", content="хватит"),
        ContextMessage(id=4, role="user", content="а про токены?"),
    ]

    assert analyzer.has_active_request(messages) is False


def test_rate_limiter_blocks_after_max_replies():
    limiter = RateLimiter(max_replies=2, window_seconds=60)

    limiter.record_reply(1)
    limiter.record_reply(1)

    assert limiter.is_limited(1) is True


def test_rate_limiter_vrchat_key_is_not_int_zero():
    limiter = RateLimiter(max_replies=2, window_seconds=60)
    limiter.record_reply(0)
    limiter.record_reply("vrchat")
    assert limiter.is_limited(0) is True
    assert limiter.is_limited("vrchat") is True
    assert limiter.is_limited(1) is False


def test_rate_limiter_telegram_session_key_is_not_vrchat():
    limiter = RateLimiter(max_replies=1, window_seconds=60)
    limiter.record_reply("telegram:-1001")
    assert limiter.is_limited("telegram:-1001") is True
    assert limiter.is_limited("vrchat") is False


def test_decision_engine_record_reply_uses_session_key(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    limiter = RateLimiter(max_replies=1, window_seconds=60)
    engine = DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=limiter,
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
    )
    engine.record_reply("vrchat")
    assert limiter.is_limited("vrchat") is True
    assert limiter.is_limited("telegram:-1001") is False


def test_noise_filter_ignores_short_ack():
    noise = NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12))

    assert noise.is_noise("ок") is True
    assert noise.is_noise("👍") is True
    assert noise.is_noise("лол") is True
    assert noise.is_noise("Vanessa, как дела?") is False
    assert noise.is_noise("продолжай мысль") is False
    assert noise.is_noise("где там") is False
    assert noise.is_noise("скажи мне") is False
    assert noise.is_noise("ок понял") is False


def build_engine(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
    *,
    block_consecutive: bool = False,
) -> DecisionEngine:
    return DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        block_consecutive_replies=block_consecutive,
    )


@pytest.mark.asyncio
async def test_decision_engine_replies_in_listen_window_when_planner_affirms(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса подскажи алгоритм генерации меша",
        ),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(id=3, role="user", content="а про текстуры?"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="а про текстуры?",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=True,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_replies_listen_window_follow_up_without_planner(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса..."),
        ContextMessage(id=2, role="assistant", content="Здесь, слушаю"),
        ContextMessage(id=3, role="user", content="втф чё с тобой"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="втф чё с тобой",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=None,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.REPLY


@pytest.mark.asyncio
async def test_decision_engine_replies_bot_pronoun_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="Ладно я не злюсь на ванессу"),
        ContextMessage(id=2, role="assistant", content="Это великодушно"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="Я её уважаю",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=None,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.REPLY


@pytest.mark.asyncio
async def test_decision_engine_replies_partner_continuation_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    # The user the bot just answered follows up inside the window ("ну чет
    # ваще мало" right after the dossier) — an explicit continuation even when
    # the LLM planner vetoed a reply.
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса досье на меня",
            sender_telegram_id=7,
        ),
        ContextMessage(id=2, role="assistant", content="Бегемот, рефлексирующий..."),
        ContextMessage(
            id=3,
            role="user",
            content="ну чет ваще мало",
            sender_telegram_id=7,
        ),
    ]

    result = await engine.decide(
        DecisionContext(
            text="ну чет ваще мало",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=False,
            in_listen_window=True,
            sender_telegram_id=7,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_replies_question_in_listen_window_neutral_planner(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    # A question inside the post-reply window warrants a reply even with a
    # neutral planner — has_question is now honored by the listen window.
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса расскажи про меш"),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(id=3, role="user", content="а про текстуры?"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="а про текстуры?",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=None,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_replies_out_of_window_question_in_active_session(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    # A question to the bot outside the window but inside an active session
    # ("хочешь закурить?" after the bot answered the same user's riddle) is
    # approved by the intent rule and survives the compose gate.
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="@vanessakap_bot вы идете по пустыне... черепаха",
        ),
        ContextMessage(id=2, role="assistant", content="Это классический тест на эмпатию"),
        ContextMessage(id=3, role="user", content="хочешь закурить?"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="хочешь закурить?",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=None,
            in_listen_window=False,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.INTENT


@pytest.mark.asyncio
async def test_decision_engine_ignores_side_talk_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса подскажи алгоритм генерации меша",
        ),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(
            id=3,
            role="user",
            content="Гриша меш гексы поле боя генерация",
        ),
    ]

    result = await engine.decide(
        DecisionContext(
            text="Гриша меш гексы поле боя генерация",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=False,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_listen_window_without_planner_affirm(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса подскажи меш"),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(id=3, role="user", content="ок"),
        ContextMessage(
            id=4,
            role="user",
            content="Гриша меш гексы поле боя генерация",
        ),
    ]

    result = await engine.decide(
        DecisionContext(
            text="Гриша меш гексы поле боя генерация",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=False,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_status_remark_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как дела"),
        ContextMessage(id=2, role="assistant", content="Норм"),
        ContextMessage(id=3, role="user", content="видите"),
        ContextMessage(id=4, role="user", content="гомункул работает"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="гомункул работает",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=False,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_third_party_gossip_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса про векторы"),
        ContextMessage(id=2, role="assistant", content="1500+ норма"),
        ContextMessage(id=3, role="user", content="почему она меня игнорирует"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="почему она меня игнорирует",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=True,
            in_listen_window=True,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOT_EXPECTED


@pytest.mark.asyncio
async def test_decision_engine_ignores_dismissal_even_when_addressed(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    result = await engine.decide(
        DecisionContext(
            text="ванесса хватит",
            telegram_chat_id=1,
            recent_messages=[],
            mentions_bot=True,
            should_reply=True,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.DISMISSAL


@pytest.mark.asyncio
async def test_decision_engine_ignores_side_talk_when_planner_says_no():

    engine = DecisionEngine(
        intent_detector=IntentDetector(),
        trigger_checker=TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи")),
        session_analyzer=SessionWindowAnalyzer(10, IntentDetector(), TriggerKeywordChecker(("помоги",))),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
    )

    result = await engine.decide(
        DecisionContext(
            text="что думаешь про тик така",
            telegram_chat_id=1,
            recent_messages=[],
            should_reply=False,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOT_EXPECTED


@pytest.mark.asyncio
async def test_decision_engine_replies_when_planner_says_yes_without_mention(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    result = await engine.decide(
        DecisionContext(
            text="модест",
            telegram_chat_id=1,
            recent_messages=[],
            should_reply=True,
        )
    )
    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.PLANNER


@pytest.mark.asyncio
async def test_decision_engine_replies_direct_address_despite_planner_veto(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    # "ванесса + императив" is a direct address: even when the LLM planner
    # misclassifies it as "общение между собой" (should_reply=False), the
    # deterministic intent layer sees the bot was addressed and replies.
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ванесса не тормози я написал",
            telegram_chat_id=1,
            recent_messages=[],
            should_reply=False,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.INTENT


@pytest.mark.asyncio
async def test_decision_engine_replies_on_reply_to_bot(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="да именно",
            telegram_chat_id=1,
            recent_messages=[],
            reply_to_bot=True,
            should_reply=False,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.ADDRESSING


@pytest.mark.asyncio
async def test_decision_engine_reply_on_intent(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="Vanessa, что нового?",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.INTENT


@pytest.mark.asyncio
async def test_decision_engine_reply_on_trigger(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="Помоги с отчётом",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY


@pytest.mark.asyncio
async def test_decision_engine_force_replies_on_trigger(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
    )

    result = await engine.decide(
        DecisionContext(
            text="расскажи про крабера",
            telegram_chat_id=1,
            recent_messages=[],
        ),
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY


@pytest.mark.asyncio
async def test_decision_engine_ignores_irrelevant_small_talk(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ага",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_noise(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ок",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOISE


@pytest.mark.asyncio
async def test_decision_engine_does_not_hard_drop_short_maybe(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="го",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    # A short but possibly meaningful message ("го") is no longer hard-dropped
    # as deterministic NOISE — it survived the LLM planner and the gates, so
    # the neural network's verdict (or the base fallback) decides instead.
    assert result.action == DecisionAction.IGNORE
    assert result.reason != DecisionReason.NOISE


@pytest.mark.asyncio
async def test_decision_engine_listen_window_short_maybe_replies_when_planner_affirms(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса подскажи алгоритм генерации меша",
        ),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(id=3, role="user", content="го"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="го",
            telegram_chat_id=1,
            recent_messages=recent,
            should_reply=True,
            in_listen_window=True,
        )
    )

    # In a post-reply listen window a short demand ("го") is not dropped as
    # noise: the planner's should_reply=True verdict leads to a reply.
    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_skips_noise_when_trigger_present(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="помоги",
            telegram_chat_id=1,
            recent_messages=[],
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY


@pytest.mark.asyncio
async def test_decision_engine_blocks_consecutive_replies(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, block_consecutive=True)
    recent = [
        ContextMessage(id=1, role="assistant", content="Уже ответила"),
    ]

    result = await engine.decide(
        DecisionContext(
            text="продолжай мысль",
            telegram_chat_id=1,
            recent_messages=recent,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.CONSECUTIVE


@pytest.mark.asyncio
async def test_decision_engine_ignores_closure_after_bot_chat(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="user", content="расскажи про кейт"),
        ContextMessage(id=2, role="assistant", content="Михась просил добавить"),
        ContextMessage(
            id=3,
            role="user",
            content="ну ладно надо будет поработать пойти",
        ),
    ]

    result = await engine.decide(
        DecisionContext(
            text="ну ладно надо будет поработать пойти",
            telegram_chat_id=1,
            recent_messages=recent,
        ),
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_quote_echo_reply_to_bot(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    bot_line = (
        "Котгаст, ты уже третий круг, скоро Данте тебя запишет в отдельный котёл"
    )
    engine = build_engine(intent_detector, trigger_checker)
    recent = [
        ContextMessage(id=1, role="assistant", content=bot_line),
    ]

    result = await engine.decide(
        DecisionContext(
            text=bot_line,
            telegram_chat_id=1,
            recent_messages=recent,
            reply_to_bot=True,
            should_reply=True,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.QUOTE_ECHO


@pytest.mark.asyncio
async def test_decision_engine_replies_on_bare_mention(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ванесса",
            telegram_chat_id=1,
            recent_messages=[],
            mentions_bot=True,
            should_reply=None,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.ADDRESSING


@pytest.mark.asyncio
async def test_decision_engine_ignores_status_remark_mention(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ванесса работает",
            telegram_chat_id=1,
            recent_messages=[],
            mentions_bot=True,
            should_reply=None,
        )
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_replies_on_mention_with_question(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker)

    result = await engine.decide(
        DecisionContext(
            text="ванесса, ты тут?",
            telegram_chat_id=1,
            recent_messages=[],
            mentions_bot=True,
            should_reply=None,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.ADDRESSING
