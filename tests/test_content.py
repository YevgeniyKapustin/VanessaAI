from app.config.content import get_content
from app.llm.prompt_builder import PromptBuilder


def test_content_loads_persona_and_templates():
    content = get_content()

    assert "Ванесса" in content.persona.role
    assert content.llm.context_header
    assert content.decision.noise_max_words >= 1


def test_prompt_builder_assembles_system_prompt_from_persona():
    builder = PromptBuilder()
    prompt = builder.system_prompt
    content = get_content()

    assert "Ванесса" in prompt
    assert "Стиль" in prompt
    assert content.llm.reply_instruction.strip() in prompt
    if content.profanity.enabled:
        assert content.profanity.instruction.strip() in prompt


def test_prompt_builder_builds_user_prompt():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "Привет",
        [],
        sender_telegram_id=7714154251,
        sender_name="Евгений",
    )

    assert get_content().llm.current_message_header in prompt
    assert "[user:Евгений] Привет" in prompt


def test_prompt_builder_includes_humor_quotes_block():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "ну ладно поработаю",
        [],
        humor_quotes=["найди работу"],
    )

    content = get_content()
    assert content.llm.humor_quotes_header in prompt
    assert "- найди работу" in prompt


def test_prompt_builder_system_includes_compose_instruction():
    builder = PromptBuilder()
    prompt = builder.system_prompt

    assert "Финальный ответ" in prompt
    assert "как было" in prompt.lower()
