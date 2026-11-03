import pytest

from vanessa.core.generate_request import GenerateRequest
from vanessa.core.turn import ChatDestination, ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.format.cross_chat_send import extract_cross_chat_send
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.stages import ComposeStage

TARGET_ID = -100123
TARGET = ChatDestination(TARGET_ID, "Other group", "supergroup")


class _ScriptedLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def generate(self, *_args, **_kwargs) -> str:
        return self.reply


def test_extracts_only_one_known_destination_for_owner() -> None:
    reply = f'Done.\n<send_to_chat id="{TARGET_ID}">Hello</send_to_chat>'

    cleaned, chat_id, text = extract_cross_chat_send(
        reply,
        known_chat_ids={TARGET_ID},
        sender_is_owner=True,
    )

    assert cleaned == "Done."
    assert chat_id == TARGET_ID
    assert text == "Hello"


def test_drops_unknown_destination_and_internal_tag() -> None:
    reply = 'Done. <send_to_chat id="-999">Hello</send_to_chat>'

    cleaned, chat_id, text = extract_cross_chat_send(
        reply,
        known_chat_ids={TARGET_ID},
        sender_is_owner=True,
    )

    assert cleaned == "Done."
    assert chat_id is None
    assert text is None


def test_drops_send_for_non_owner_and_multiple_actions() -> None:
    one = f'<send_to_chat id="{TARGET_ID}">Hello</send_to_chat>'
    cleaned, chat_id, text = extract_cross_chat_send(
        one,
        known_chat_ids={TARGET_ID},
        sender_is_owner=False,
    )
    assert cleaned == ""
    assert chat_id is None
    assert text is None

    two = f"{one}{one}"
    _, chat_id, text = extract_cross_chat_send(
        two,
        known_chat_ids={TARGET_ID},
        sender_is_owner=True,
    )
    assert chat_id is None
    assert text is None


def test_relayed_text_has_no_owner_attribution() -> None:
    variants = (
        "Евгений просит передать: релиз в пятницу",
        "Передаю от Евгения: релиз в пятницу",
        "По просьбе Евгения: релиз в пятницу",
        "Евгений сказал, что релиз в пятницу",
        "Евгений: релиз в пятницу",
    )

    for variant in variants:
        reply = f'<send_to_chat id="{TARGET_ID}">{variant}</send_to_chat>'
        _, _, text = extract_cross_chat_send(
            reply,
            known_chat_ids={TARGET_ID},
            sender_is_owner=True,
            owner_names=("Евгений",),
        )
        assert text == "релиз в пятницу", variant


def test_plain_relayed_text_is_unchanged() -> None:
    reply = f'<send_to_chat id="{TARGET_ID}">релиз в пятницу</send_to_chat>'

    _, _, text = extract_cross_chat_send(
        reply,
        known_chat_ids={TARGET_ID},
        sender_is_owner=True,
        owner_names=("Евгений",),
    )

    assert text == "релиз в пятницу"


def test_only_attribution_means_no_send() -> None:
    reply = (
        f'<send_to_chat id="{TARGET_ID}">'
        "Евгений просит передать:</send_to_chat>"
    )

    _, chat_id, text = extract_cross_chat_send(
        reply,
        known_chat_ids={TARGET_ID},
        sender_is_owner=True,
        owner_names=("Евгений",),
    )

    assert chat_id is None
    assert text is None


def test_prompt_lists_known_groups_only_for_owner() -> None:
    owner_prompt = PromptBuilder().build_user_prompt(
        GenerateRequest(
            user_message="Send it to the other group",
            context_blocks=[],
            telegram_chat_id=-1001,
            known_chats=(TARGET,),
            sender_is_owner=True,
        )
    )
    other_prompt = PromptBuilder().build_user_prompt(
        GenerateRequest(
            user_message="Send it to the other group",
            context_blocks=[],
            telegram_chat_id=-1001,
            known_chats=(TARGET,),
            sender_is_owner=False,
        )
    )

    assert "Other group (id: -100123)" in owner_prompt
    assert '<send_to_chat id="CHAT_ID">' in owner_prompt
    assert "Never write there that" in owner_prompt
    assert "Other group (id: -100123)" not in other_prompt


@pytest.mark.asyncio
async def test_compose_stage_extracts_owner_send_action() -> None:
    turn = ChatTurnInput(
        telegram_chat_id=-1001,
        message="Vanessa, send it to the other group",
        sender_telegram_id=7,
        known_chats=(TARGET,),
        sender_is_owner=True,
    )
    ctx = TurnPipelineContext(turn=turn)
    ctx.turn_plan = TurnPlan(
        original=turn.message,
        text=turn.message,
        skip_search=True,
    )
    llm = _ScriptedLLM(
        f'Done.\n<send_to_chat id="{TARGET_ID}">Hello</send_to_chat>'
    )

    assert await ComposeStage(llm).run(ctx) is True
    assert ctx.reply == "Done."
    assert ctx.outbound_chat_id == TARGET_ID
    assert ctx.outbound_text == "Hello"
