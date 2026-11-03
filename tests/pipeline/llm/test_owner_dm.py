"""The private DM tag: allowed only for proxy questions, always stripped."""

from vanessa.core.generate_request import GenerateRequest
from vanessa.pipeline.llm.format.owner_dm import extract_owner_dm
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder


def test_extracts_the_dm_text_and_strips_the_tag() -> None:
    reply = "Передала ему вопрос.\n<dm_owner>Какой срок по релизу?</dm_owner>"

    cleaned, dm = extract_owner_dm(reply, allowed=True)

    assert cleaned == "Передала ему вопрос."
    assert dm == "Какой срок по релизу?"


def test_not_allowed_still_strips_but_returns_no_dm() -> None:
    cleaned, dm = extract_owner_dm("ок <dm_owner>вопрос</dm_owner>", allowed=False)

    assert cleaned == "ок"
    assert dm is None


def test_several_tags_are_rejected() -> None:
    reply = "<dm_owner>a</dm_owner><dm_owner>b</dm_owner>"

    cleaned, dm = extract_owner_dm(reply, allowed=True)

    assert cleaned == ""
    assert dm is None


def test_empty_tag_is_rejected() -> None:
    cleaned, dm = extract_owner_dm("текст <dm_owner> </dm_owner>", allowed=True)

    assert cleaned == "текст"
    assert dm is None


def test_no_tag_keeps_the_reply() -> None:
    assert extract_owner_dm("обычный ответ", allowed=True) == ("обычный ответ", None)


def test_proxy_question_adds_its_directive() -> None:
    request = GenerateRequest(
        user_message="Евгений, когда релиз?",
        context_blocks=[],
        proxy_question=True,
        proxy_chat_title="Work chat",
    )

    prompt = PromptBuilder().build_user_prompt(request)

    assert "## Proxy reply" in prompt
    assert "<dm_owner>" in prompt


def test_owner_dm_adds_the_relay_target() -> None:
    request = GenerateRequest(
        user_message="в пятницу",
        context_blocks=[],
        owner_dm=True,
        relay_chat_id=-1001,
        relay_chat_title="Work chat",
        relay_question="Когда релиз?",
    )

    prompt = PromptBuilder().build_user_prompt(request)

    assert "## Private chat with the owner" in prompt
    assert 'id="-1001"' in prompt
    assert "Когда релиз?" in prompt
