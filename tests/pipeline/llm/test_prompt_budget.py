from vanessa.config.content import PromptBudgetContent
from vanessa.core.messages import ContextBlock, ContextMessage
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.llm.prompts.budget import (
    PRIORITY_CONTEXT,
    PRIORITY_CURRENT,
    PRIORITY_KNOWLEDGE,
    apply_budget,
    truncate_body,
)
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder


def test_truncate_body_under_limit_unchanged() -> None:
    assert truncate_body("короткий текст", 100) == "короткий текст"


def test_truncate_body_cuts_at_sentence_boundary() -> None:
    text = "Первое предложение. Второе предложение с длинным хвостом."
    result = truncate_body(text, 24)
    assert len(result) <= 24
    assert result.startswith("Первое предложение")


def test_truncate_body_without_boundary_appends_ellipsis() -> None:
    result = truncate_body("а" * 100, 10)
    assert len(result) <= 10
    assert result.endswith("…")


def test_apply_budget_disabled_returns_all_parts() -> None:
    parts = [(PRIORITY_CURRENT, "current_message", "x" * 10)]
    budget = PromptBudgetContent(enabled=True, max_chars=1)
    result = apply_budget(parts, budget, enabled=False)
    assert result == parts


def test_apply_budget_per_section_cap() -> None:
    budget = PromptBudgetContent(enabled=True, max_chars=0, context_blocks=10)
    parts = [(PRIORITY_CONTEXT, "context_blocks", "c" * 100)]
    result = apply_budget(parts, budget, enabled=True)
    assert len(result) == 1
    assert len(result[0][2]) <= 10


def test_apply_budget_global_cap_keeps_high_priority() -> None:
    budget = PromptBudgetContent(enabled=True, max_chars=400)
    current = "CURRENT_" * 20  # 160 chars
    parts = [
        (PRIORITY_CURRENT, "current_message", current),
        (PRIORITY_KNOWLEDGE, "knowledge_blocks", "k" * 300),
        (PRIORITY_CONTEXT, "context_blocks", "c" * 300),
    ]
    result = apply_budget(parts, budget, enabled=True)
    bodies = {section: body for _, section, body in result}
    # Highest-priority section survives whole; lowest is dropped.
    assert bodies["current_message"] == current
    assert "context_blocks" not in bodies
    total = sum(len(body) for body in bodies.values())
    assert total <= 400


def test_apply_budget_global_cap_keeps_order() -> None:
    budget = PromptBudgetContent(enabled=True, max_chars=1000)
    parts = [
        (PRIORITY_CONTEXT, "context_blocks", "c" * 100),
        (PRIORITY_KNOWLEDGE, "knowledge_blocks", "k" * 100),
        (PRIORITY_CURRENT, "current_message", "m" * 100),
    ]
    result = apply_budget(parts, budget, enabled=True)
    # All fit — original order preserved.
    assert [section for _, section, _ in result] == [
        "context_blocks",
        "knowledge_blocks",
        "current_message",
    ]


def test_build_user_prompt_applies_budget_and_keeps_current() -> None:
    builder = PromptBuilder()
    current = "привет, ванесса"
    prompt = builder.build_user_prompt(
        current,
        context_blocks=[
            ContextBlock(
                anchor_id=1,
                messages=(
                    ContextMessage(id=1, role="user", content="старое сообщение"),
                ),
            )
        ],
        knowledge_blocks=[
            KnowledgeBlock(
                path="People/личь.md",
                title="личь",
                kind="people",
                content="Личь — сварщик и философ.",
            )
        ],
        session_messages=[
            ContextMessage(id=2, role="user", content="недавняя реплика")
        ],
    )
    assert current in prompt
    assert "личь" in prompt
    # The real configured global cap (llm.yaml) is never exceeded.
    budget = builder._content.llm.budget
    if budget.max_chars > 0:
        assert len(prompt) <= budget.max_chars
