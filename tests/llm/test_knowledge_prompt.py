from app.knowledge.schema import KnowledgeBlock
from app.llm.prompts.prompt_builder import PromptBuilder


def test_build_user_prompt_includes_knowledge_blocks():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "что там у Лича",
        [],
        knowledge_blocks=[
            KnowledgeBlock(
                path="People/lich.md",
                title="lich",
                kind="person",
                content="## Контекст жизни\nживёт в Астралии",
            )
        ],
    )

    assert "From my archive on the topic:" in prompt
    assert "lich" in prompt
    assert "Астралии" in prompt


def test_build_user_prompt_without_knowledge():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "From my archive on the topic:" not in prompt
