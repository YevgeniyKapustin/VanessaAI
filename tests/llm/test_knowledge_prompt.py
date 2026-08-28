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
    import xml.etree.ElementTree as ET

    builder = PromptBuilder()
    prompt = builder.system_prompt
    stickers = get_content().stickers
    if not stickers.enabled or not stickers.available_tags:
        return  # stickers not configured — nothing to assert

    assert "## Stickers" in prompt
    section = prompt.split("## Stickers", 1)[1]
    # The Examples block now follows Stickers (recommended order); stop at the
    # next section header so only the Stickers block is parsed.
    section = section.split("\n## ", 1)[0]
    assert "<sticker_system>" in section
    # the prose may mention the block, so slice from the last occurrence
    xml_start = section.rindex("<sticker_system>")
    root = ET.fromstring(section[xml_start:])  # raises on malformed XML
    advertised = {tag.get("name") for tag in root.find("available_tags")}
    assert advertised == set(stickers.available_tags)
    assert root.find("description") is not None
    assert root.find("tag_rules") is not None
