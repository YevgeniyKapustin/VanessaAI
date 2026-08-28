from app.config.content import get_content
from app.llm.prompts.prompt_builder import PromptBuilder


def test_content_loads_persona_and_templates():
    content = get_content()

    assert "Ванесса" in content.persona.identity_text()
    assert content.llm.context_header
    assert content.decision.noise_max_words >= 1


def test_planner_prompt_rejects_empty_meaningless_phrases():
    prompt = get_content().rag.planner_prompt
    assert "чего и следовало ожидать" in prompt
    assert "это правда" in prompt
    assert "empty/meaningless" in prompt
    assert "skip=true" in prompt


def test_reaction_gate_prompt_rejects_empty_meaningless_phrases():
    prompt = get_content().decision.reaction_gate_prompt
    assert "чего и следовало ожидать" in prompt
    assert "это правда" in prompt
    assert "empty/meaningless" in prompt


def test_compose_prompt_uses_context_selectively():
    llm = get_content().llm
    assert "Use the provided information selectively" in llm.task_text()
    assert "don't dump everything" in llm.answer_text()


def test_compose_prompt_teaches_chain_of_thought_answer_tag():
    # The compose prompt must instruct the model to think first, then emit the
    # final message after the [answer] tag.
    llm = get_content().llm
    assert "Output format — think first, then answer" in llm.answer_text()
    assert "[answer]" in llm.answer_text()
    assert "final message" in llm.answer_text()


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
    assert "[user:Евгений] text: Привет" in prompt


def test_prompt_builder_includes_aliases_block(monkeypatch):
    import app.llm.prompts.prompt_builder as pb

    monkeypatch.setattr(
        pb,
        "format_aliases_for_prompt",
        lambda: "Гриша = Ну я",
    )
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("кто такой гриша", [])

    content = get_content()
    assert content.llm.aliases_header.strip() in prompt
    assert "Гриша = Ну я" in prompt


def test_prompt_builder_omits_aliases_block_when_empty(monkeypatch):
    import app.llm.prompts.prompt_builder as pb

    monkeypatch.setattr(pb, "format_aliases_for_prompt", lambda: "")
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])

    assert get_content().llm.aliases_header.strip() not in prompt


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
    assert "[Личь] text: Личь не делает карты" in prompt
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


def test_compose_prompt_instructs_message_blocks():
    # The compose prompt must teach the model to split long replies into short
    # 1-2 sentence blocks separated by the [next] marker, so the bot can send
    # them as separate messages instead of one wall of text.
    llm = get_content().llm
    assert llm.block_marker == "[next]"
    assert "Message blocks" in llm.answer_text()
    assert "[next]" in llm.answer_text()


def test_compose_prompt_examples_show_multiblock_reply():
    assert "[next]" in get_content().llm.answer_examples


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


def test_prompt_builder_system_forbids_addressing_by_name():
    builder = PromptBuilder()
    prompt = builder.system_prompt

    # The "Addressing" rule (persona) is a categorical ban, present in the
    # final answer system prompt.
    assert "NEVER call the addressee by name" in prompt
    # The owner-naming constraint («Евгений»/«Капуста», never «Женя»…) lives in
    # persona rules; the llm.yaml checklist no longer repeats it (dedup).
    assert "«Женя», «Жень», «Женечка»" in prompt


def test_prompt_builder_owner_note_forbids_calling_owner_by_name(monkeypatch):
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
    # The per-turn owner note (injected into the user prompt) must NOT tell the
    # model to address the owner by name — it must forbid it.
    assert "Never call him by name" in prompt
