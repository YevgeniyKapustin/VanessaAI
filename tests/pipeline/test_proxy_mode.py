"""Proxy mode: chat resolution, question detection and owner addressing."""

from vanessa.config.settings import settings
from vanessa.core.turn import ChatDestination, ChatTurnInput
from vanessa.pipeline.proxy import detect_proxy_mode, looks_like_question
from vanessa.pipeline.proxy import owner as owner_module
from vanessa.pipeline.proxy.owner import addressed_to_owner, name_hit, owner_names

OWNER = 999
BOT = 777
PROXY_CHAT = -1001


def _turn(**overrides) -> ChatTurnInput:
    values = {
        "telegram_chat_id": PROXY_CHAT,
        "message": "Евгений, когда будет релиз?",
        "sender_telegram_id": BOT,
        "sender_first_name": "Agent",
        "chat_title": "Work chat | agents",
        "chat_type": "supergroup",
        "sender_is_bot": True,
    }
    values.update(overrides)
    return ChatTurnInput(**values)


def test_question_heuristic() -> None:
    assert looks_like_question("когда релиз")
    assert looks_like_question("скинь ссылку на макет")
    assert not looks_like_question("да, согласен")
    assert not looks_like_question("ок")


def test_proxy_question_by_reply_to_owner(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_telegram_id", 0)
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")

    mode = detect_proxy_mode(_turn(reply_to_sender_telegram_id=OWNER))

    assert mode.proxy_question is True
    assert mode.chat_id == PROXY_CHAT
    assert mode.owner_dm is False


def test_proxy_question_by_owner_name(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")
    monkeypatch.setattr(settings, "proxy_owner_aliases", "Евгений,Evgeny")

    assert detect_proxy_mode(_turn()).proxy_question is True


def test_plain_chat_in_agents_chat_is_not_a_proxy_question(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")
    monkeypatch.setattr(settings, "proxy_owner_aliases", "Евгений")

    mode = detect_proxy_mode(_turn(message="Евгений, я всё сделал"))

    assert mode.proxy_question is False


def test_human_question_is_not_a_proxy_question(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")

    mode = detect_proxy_mode(_turn(sender_is_bot=False))

    assert mode.proxy_question is False


def test_pinned_chat_does_not_leak_into_other_groups(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_telegram_id", -1001)

    turn = _turn(
        telegram_chat_id=-2002,
        chat_title="Рабочий чат",
        message="Евгений, когда будет релиз?",
    )

    assert detect_proxy_mode(turn).proxy_question is False


def test_owner_dm_resolves_the_known_agents_chat(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")

    turn = _turn(
        telegram_chat_id=OWNER,
        chat_title=None,
        chat_type="private",
        sender_telegram_id=OWNER,
        sender_is_bot=False,
        sender_is_owner=True,
        message="сделаем в пятницу",
        known_chats=(
            ChatDestination(chat_id=-1001, title="Work chat", chat_type="supergroup"),
        ),
    )

    mode = detect_proxy_mode(turn)

    assert mode.owner_dm is True
    assert mode.proxy_question is False
    assert mode.chat_id == PROXY_CHAT


def test_stranger_dm_is_not_owner_dm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")

    turn = _turn(
        telegram_chat_id=42,
        chat_title=None,
        chat_type="private",
        sender_telegram_id=42,
        sender_is_bot=False,
        message="привет",
    )

    assert detect_proxy_mode(turn).owner_dm is False


def test_owner_names_merge_card_aliases_and_settings(monkeypatch) -> None:
    monkeypatch.setattr(owner_module, "owner_telegram_ids", lambda: frozenset({OWNER}))
    monkeypatch.setattr(
        owner_module, "get_telegram_nicknames", lambda: {OWNER: "Евгений"}
    )
    monkeypatch.setattr(
        owner_module,
        "get_chat_aliases",
        lambda: {"Евгений": ("Женя", "@evgeny")},
    )
    monkeypatch.setattr(settings, "proxy_owner_aliases", "Evgeny")

    names = set(owner_names())

    assert names == {"Евгений", "Женя", "@evgeny", "Evgeny"}


def test_name_hit_respects_word_boundaries() -> None:
    assert name_hit("привет, евгений!", "Евгений")
    assert name_hit("спроси @evgeny, он знает", "@evgeny")
    assert not name_hit("спроси @evgeny_work", "@evgeny")
    assert not name_hit("евгеньевич", "Евгений")


def test_addressed_to_owner_by_reply_to_his_message(monkeypatch) -> None:
    monkeypatch.setattr(owner_module, "owner_telegram_ids", lambda: frozenset({OWNER}))
    monkeypatch.setattr(owner_module, "get_telegram_nicknames", dict)
    monkeypatch.setattr(owner_module, "get_chat_aliases", dict)
    monkeypatch.setattr(settings, "proxy_owner_aliases", "")

    assert addressed_to_owner(_turn(reply_to_sender_telegram_id=OWNER)) is True
    assert addressed_to_owner(_turn(reply_to_sender_telegram_id=BOT)) is False
