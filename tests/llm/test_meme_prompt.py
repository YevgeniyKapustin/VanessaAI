from vanessa.config.content import MemeDefContent
from vanessa.llm.prompts.prompt_builder import PromptBuilder


def test_build_user_prompt_includes_meme_blocks():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "ну и окаешь тут",
        [],
        meme_blocks=[
            MemeDefContent(
                name="Окак",
                keywords=["окаешь"],
                meaning="недоумение на абсурд",
                usage="абсурдная ситуация",
            )
        ],
    )

    assert "Curated memes I know" in prompt
    assert "Окак" in prompt
    assert "недоумение на абсурд" in prompt
    assert "абсурдная ситуация" in prompt


def test_build_user_prompt_without_meme_blocks():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "Curated memes I know" not in prompt


def test_build_user_prompt_includes_compact_meme_menu():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "привет",
        [],
        meme_menu=[
            MemeDefContent(
                name="Окак",
                keywords=["окаешь"],
                meaning="недоумение на абсурд",
                usage="абсурдная ситуация",
            ),
            MemeDefContent(
                name="Бурмалда",
                keywords=["бурмалда"],
                meaning="нелепица",
                usage="странная ситуация",
            ),
        ],
    )

    assert "Memes I can use if one fits" in prompt
    # compact form: name + usage (no full meaning dumped)
    assert "Окак — абсурдная ситуация" in prompt
    assert "Бурмалда — странная ситуация" in prompt


def test_build_user_prompt_without_meme_menu():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "Memes I can use if one fits" not in prompt
