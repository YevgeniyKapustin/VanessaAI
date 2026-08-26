from unittest.mock import AsyncMock

import pytest

from app.llm.humor.critic import (
    CriticStatus,
    CriticVerdict,
    HumorCritic,
    parse_critic_verdict,
)


def test_parse_verdict_plain_approved():
    raw = (
        '{"status": "APPROVED", "score": 4, "reason": "ок", '
        '"fix_instruction": ""}'
    )
    verdict = parse_critic_verdict(raw)
    assert verdict.status is CriticStatus.APPROVED
    assert verdict.approved is True
    assert verdict.score == 4
    assert verdict.reason == "ок"
    assert verdict.fix_instruction == ""


def test_parse_verdict_fenced_json():
    raw = '```json\n{"status": "REJECTED", "score": 2, "reason": "нет юмора", "fix_instruction": "добавь иронию"}\n```'
    verdict = parse_critic_verdict(raw)
    assert verdict.status is CriticStatus.REJECTED
    assert verdict.approved is False
    assert verdict.score == 2
    assert verdict.fix_instruction == "добавь иронию"


def test_parse_verdict_rejected_with_fix_instruction():
    verdict = parse_critic_verdict(
        '{"status": "REJECTED", "score": 1, "reason": "плоско", '
        '"fix_instruction": "используй гиперболу"}'
    )
    assert verdict.status is CriticStatus.REJECTED
    assert verdict.fix_instruction == "используй гиперболу"


def test_parse_verdict_invalid_status_falls_back_approved():
    verdict = parse_critic_verdict(
        '{"status": "MAYBE", "score": 5, "reason": "?", "fix_instruction": ""}'
    )
    assert verdict.status is CriticStatus.APPROVED


def test_parse_verdict_unparseable_falls_back_approved():
    verdict = parse_critic_verdict("совершенно не json")
    assert verdict.status is CriticStatus.APPROVED
    assert verdict.score == 3


def test_parse_verdict_non_object_falls_back_approved():
    verdict = parse_critic_verdict("[1, 2, 3]")
    assert verdict.status is CriticStatus.APPROVED


def test_parse_verdict_score_clamped():
    verdict = parse_critic_verdict('{"status": "REJECTED", "score": 99}')
    assert verdict.score == 5
    low = parse_critic_verdict('{"status": "REJECTED", "score": -3}')
    assert low.score == 1
    missing = parse_critic_verdict('{"status": "APPROVED", "score": null}')
    assert missing.score == 3


def test_verdict_approved_property():
    assert CriticVerdict(status=CriticStatus.APPROVED, score=5).approved is True
    assert CriticVerdict(status=CriticStatus.REJECTED, score=2).approved is False


class FakeCompleter:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls: list[list[dict]] = []

    async def complete(self, model: str, messages: list[dict], **kwargs) -> str:
        self.calls.append(messages)
        return self.raw


@pytest.mark.asyncio
async def test_humor_critic_review_approved():
    critic = HumorCritic(
        llm_client=FakeCompleter(
            '{"status": "APPROVED", "score": 5, "reason": "отлично", '
            '"fix_instruction": ""}'
        ),
        model="critic-model",
    )
    verdict = await critic.review("шутка", user_message="привет", humor_quotes=["найди работу"])
    assert verdict.approved is True
    assert verdict.score == 5
    assert critic._client.calls[0][0]["role"] == "system"
    user_prompt = critic._client.calls[0][1]["content"]
    assert "шутка" in user_prompt
    assert "найди работу" in user_prompt


@pytest.mark.asyncio
async def test_humor_critic_review_rejected():
    critic = HumorCritic(
        llm_client=FakeCompleter(
            '{"status": "REJECTED", "score": 2, "reason": "плоско", '
            '"fix_instruction": "добавь мем"}'
        ),
        model="critic-model",
    )
    verdict = await critic.review("ответ", user_message="тема", humor_quotes=[])
    assert verdict.status is CriticStatus.REJECTED
    assert verdict.fix_instruction == "добавь мем"


@pytest.mark.asyncio
async def test_humor_critic_review_exception_falls_back_approved():
    completer = AsyncMock()
    completer.complete = AsyncMock(side_effect=RuntimeError("boom"))
    critic = HumorCritic(llm_client=completer, model="critic-model")
    verdict = await critic.review("ответ", user_message="тема", humor_quotes=[])
    assert verdict.approved is True
    assert verdict.reason == "critic unavailable"
