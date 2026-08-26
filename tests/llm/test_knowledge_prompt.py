from app.config.content import get_content
from app.knowledge.schema import KnowledgeBlock
from app.llm.prompts.prompt_builder import PromptBuilder


def test_build_user_prompt_includes_knowledge_blocks():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "что там у Лича",
        [],
        knowledge_blocks=[
            KnowledgeBlock(
                path="People/личь.md",
                title="личь",
                kind="person",
                content="## Контекст жизни\nживёт в Астралии",
            )
        ],
    )

    assert "From my archive on the topic:" in prompt
    assert "личь" in prompt
    assert "Астралии" in prompt


def test_build_user_prompt_without_knowledge():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "From my archive on the topic:" not in prompt


def test_system_prompt_stickers_list_only_catalog_tags():
    """The Stickers section must advertise exactly the tags that have stickers."""
    builder = PromptBuilder()
    prompt = builder.system_prompt
    stickers = get_content().stickers
    if not stickers.enabled or not stickers.available_tags:
        return  # stickers not configured — nothing to assert

    assert "## Stickers" in prompt
    section = prompt.split("## Stickers", 1)[1]
    assert "Available sticker tags" in section
    for line in stickers.tag_lines():
        assert line in section
    # every advertised tag is a real catalog tag
    advertised: set[str] = set()
    for part in section.split("Available sticker tags", 1)[1].split("\n")[1:]:
        stripped = part.strip()
        if stripped.startswith("- "):
            advertised.add(stripped[2:].split("(", 1)[0].strip())
    assert advertised == set(stickers.available_tags)
