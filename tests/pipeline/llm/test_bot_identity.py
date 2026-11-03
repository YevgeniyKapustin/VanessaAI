"""Keep bot identity through stored history, aliases and reply quotes."""

from xml.etree import ElementTree as ET

import pytest

from vanessa.core.generate_request import GenerateRequest
from vanessa.core.messages import ContextBlock, ContextMessage
from vanessa.knowledge.users import display_names
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.llm.prompts.session_format import format_session_messages


def test_session_distinguishes_same_named_human_peer_and_vanessa():
    history = [
        ContextMessage(id=1, role="user", content="hi", sender_name="Кирилл"),
        ContextMessage(id=2, role="user", content="hi", sender_name="[бот Кирилл]"),
        ContextMessage(id=3, role="assistant", content="hi"),
        ContextMessage(id=4, role="user", content="hi", sender_name="bot"),
    ]

    messages = ET.fromstring(format_session_messages(history)).findall("msg")

    assert [message.get("sender_type") for message in messages] == [
        "human",
        "bot",
        "self",
        "human",
    ]
    assert [message.get("sender") for message in messages] == [
        "Кирилл",
        "[бот Кирилл]",
        "bot",
        "bot",
    ]


def test_people_alias_cannot_replace_bot_label(monkeypatch):
    monkeypatch.setattr(display_names, "canonical_name_for", lambda _: "Кирилл")

    assert (
        display_names.resolve_sender_display_name(777, "[бот Кирилл]") == "[бот Кирилл]"
    )
    assert display_names.resolve_sender_display_name(123, "Кирюха") == "Кирилл"


def test_archive_keeps_bot_type_and_quoted_author():
    message = ContextMessage(
        id=1,
        role="user",
        content="ответ",
        sender_name="[бот Кирилл]",
        reply_to_text="вопрос",
        reply_to_sender_name="Евгений",
    )
    block = ContextBlock(anchor_id=1, messages=(message,))

    rendered = PromptBuilder().format_context_block(1, block)

    assert 'sender_type="bot"' in rendered
    assert 'reply_sender="Евгений"' in rendered
    assert "<reply_text>вопрос</reply_text>" in rendered


@pytest.mark.parametrize("section", ["session_messages", "earlier_messages"])
def test_human_quoting_bot_keeps_both_authors(section):
    message = ContextMessage(
        id=1,
        role="user",
        content="согласна?",
        sender_name="Евгений",
        reply_to_text="я человек",
        reply_to_sender_name='[бот Кирилл "AI"]',
    )

    prompt = PromptBuilder().build_user_prompt("дальше", [], **{section: [message]})

    assert 'sender="Евгений"' in prompt
    assert 'sender_type="human"' in prompt
    assert 'reply_sender="[бот Кирилл &quot;AI&quot;]"' in prompt
    assert "<reply_text>я человек</reply_text>" in prompt


@pytest.mark.parametrize("sender_name", ["Евгений", "[бот Кирилл]"])
def test_current_reply_keeps_bot_quote_author(sender_name):
    request = GenerateRequest(
        user_message="согласна?",
        context_blocks=[],
        sender_name=sender_name,
        reply_to_text="я человек",
        reply_to_sender_name="[бот Алиса]",
    )

    prompt = PromptBuilder().build_user_prompt(request)

    expected_type = "bot" if sender_name.startswith("[бот ") else "human"
    assert f'sender_type="{expected_type}"' in prompt
    assert 'reply_sender="[бот Алиса]"' in prompt
    assert "<reply_text>я человек</reply_text>" in prompt
