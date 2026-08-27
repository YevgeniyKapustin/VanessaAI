from app.config.content import get_content
from app.llm.prompts.prompt_builder import PromptBuilder


def test_content_loads_persona_and_templates():
    content = get_content()

    assert "Ванесса" in content.persona.identity_text()
    assert content.llm.context_header
    assert content.decision.noise_max_words >= 1


def test_prompt_builder_assembles_system_prompt_from_persona():
    builder = PromptBuilder()
    prompt = builder.system_prompt
    content = get_content()

    assert "Ванесса" in prompt
    assert "## Persona" in prompt
    assert "## Voice" in prompt
    assert "## Content rules" in prompt
    assert content.llm.task_text() in prompt
    if content.profanity.enabled:
        assert "## Emotional language" in prompt


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


def test_prompt_builder_includes_reply_context():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "а я про то и говорю",
        [],
        reply_to_text="Личь не делает карты",
        reply_to_sender_telegram_id=99,
        reply_to_sender_name="Личь",
    )

    content = get_content()
    assert content.llm.reply_message_header.strip() in prompt
    assert "[Личь] Личь не делает карты" in prompt
    # the reply block appears before the current message line
    assert prompt.index(content.llm.reply_message_header) < prompt.index(
        content.llm.current_message_header
    )


def test_prompt_builder_omits_reply_context_when_absent():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert get_content().llm.reply_message_header.strip() not in prompt


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


def test_prompt_builder_includes_critic_feedback_section():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "ну ладно поработаю",
        [],
        critic_feedback="добавь гиперболу",
    )

    content = get_content()
    assert content.llm.critic.fix_instruction_header.strip() in prompt
    assert "добавь гиперболу" in prompt


def test_prompt_builder_omits_critic_feedback_when_empty():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("ну ладно поработаю", [])
    assert "Humor editor's note" not in prompt


def test_prompt_builder_system_includes_answer_checklist():
    builder = PromptBuilder()
    prompt = builder.system_prompt

    assert "## Answer formulation" in prompt
    assert "Before replying, check" in prompt
    assert "Bad:" in prompt
    assert "Good:" in prompt


def test_prompt_builder_includes_owner_note_for_host(monkeypatch):
    monkeypatch.setattr(
        "app.llm.prompts.prompt_builder.settings.required_user_telegram_id",
        7714154251,
    )
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "привет",
        [],
        sender_telegram_id=7714154251,
        sender_name="Евгений",
    )
    assert get_content().llm.owner_message_note.strip() in prompt


def test_prompt_builder_includes_reply_language_rule():
    builder = PromptBuilder()
    prompt = builder.system_prompt

    assert "## Reply language" in prompt
    assert "Default: Russian" in prompt


def test_prompt_builder_includes_tone_note():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "нужно срочно починить сервер",
        [],
        tone="serious",
    )

    assert "Detected tone of the user's message: serious." in prompt
    assert "answer the substance straight" in prompt


def test_prompt_builder_omits_tone_note_when_not_provided():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "Detected tone of the user's message" not in prompt


def test_prompt_builder_includes_clarification_instruction():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "ванесса я думаю ты виновата",
        [],
        needs_clarification=True,
        clarification_hint="почему",
    )

    content = get_content()
    assert content.llm.clarification_instruction.strip() in prompt
    assert "What is unclear: почему" in prompt


def test_prompt_builder_omits_clarification_instruction_when_not_needed():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert get_content().llm.clarification_instruction.strip() not in prompt


def test_portrait_content_configured():
    content = get_content()
    assert content.portrait.enabled
    assert "{dossier}" in content.portrait.portrait_prompt
    assert "{nickname}" in content.portrait.portrait_prompt
    # The prompt must ask for a compact portrait, not raw facts.
    assert "3-5" in content.portrait.portrait_prompt
    assert "compact" in content.portrait.portrait_prompt
