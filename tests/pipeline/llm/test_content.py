from vanessa.config.content import get_content
from vanessa.core.messages import ContextBlock, ContextMessage, ImageAttachment
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder


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
    # The compose prompt must instruct the model to ALWAYS reason first (chain
    # of thought on every reply), then emit the final message after the
    # [answer] tag.
    llm = get_content().llm
    assert "ALWAYS reason before you answer" in llm.answer_text()
    assert "every time, no exceptions" in llm.answer_text()
    assert "[answer]" in llm.answer_text()
    assert "final message" in llm.answer_text()


def test_compose_prompt_ignore_tag_carries_debug_reason():
    # When ignoring a repeat, the model writes the tag followed by a short
    # internal reason — for debugging only, never shown in the chat.
    llm = get_content().llm
    assert "[ignore]" in llm.answer_text()
    assert "reason after the tag" in llm.answer_text()
    assert "never shown" in llm.answer_text()


def test_compose_prompt_never_ignores_real_questions():
    # The ignore rules must not swallow legitimate questions: a question is
    # never ignored just because it was asked before, and when in doubt the
    # model should answer rather than stay silent.
    llm = get_content().llm
    assert "always gets an answer" in llm.answer_text()
    assert "When in doubt, answer" in llm.answer_text()


def test_compose_prompt_sender_identity_is_authoritative():
    # Vanessa must never burn chain-of-thought guessing who the sender "really"
    # is (e.g. whether «Ну я» == «Гриша»): the `sender` attribute is
    # authoritative, already resolved by the system, and attached notes/directives
    # refer to the current sender — no name reconciliation in the reasoning.
    llm = get_content().llm
    task = llm.task_text()
    assert "the sender is authoritative" in task
    assert "never spend reasoning on names" in task
    assert "don't reconcile names" in task


def test_compose_prompt_answers_deferred_questions():
    # When someone pokes the bot to answer an earlier message it never answered,
    # the model must reply to that earlier question's substance, not to the poke.
    llm = get_content().llm
    assert "Deferred questions" in llm.task_text()
    assert "not to the poke" in llm.task_text()
    # Substring must not cross a line break inside the YAML block scalar.
    assert "substance of that earlier question, not the poke itself" in llm.answer_text()


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
    assert 'sender="Евгений"' in prompt
    assert "<text>Привет</text>" in prompt


def test_prompt_builder_includes_aliases_block(monkeypatch):
    import vanessa.pipeline.llm.prompts.prompt_builder as pb

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
    import vanessa.pipeline.llm.prompts.prompt_builder as pb

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
    assert "<reply_text>Личь не делает карты</reply_text>" in prompt
    # the reply hint comment appears before the current message line
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
        "vanessa.pipeline.llm.prompts.prompt_builder.settings.required_user_telegram_id",
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


def test_prompt_builder_includes_detailed_note():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "давай подробнее",
        [],
        detail="detailed",
    )

    assert get_content().llm.detail_note_detailed.strip() in prompt
    assert "Do NOT compress the answer" in prompt


def test_prompt_builder_includes_brief_note():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "в двух словах",
        [],
        detail="brief",
    )

    assert get_content().llm.detail_note_brief.strip() in prompt


def test_prompt_builder_omits_detail_note_when_normal():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [], detail="normal")

    assert get_content().llm.detail_note_detailed.strip() not in prompt
    assert get_content().llm.detail_note_brief.strip() not in prompt


def test_prompt_builder_suppresses_detailed_note_when_attitude_note_present():
    """An annoyed Vanessa stays brief — the cold/annoyance note wins over
    a request for a detailed answer (no contradictory directives)."""
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "давай подробнее",
        [],
        detail="detailed",
        attitude_note="reply coldly and briefly",
    )

    assert get_content().llm.detail_note_detailed.strip() not in prompt


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

    assert "NEVER call the addressee by name" in prompt


def test_prompt_builder_renders_album_instruction_when_candidates():
    from vanessa.core.messages import PhotoCandidate

    builder = PromptBuilder()
    candidates = [
        PhotoCandidate(index=1, telegram_file_id="f1", caption="кот на диване"),
    ]
    prompt = builder.build_user_prompt(
        "скинь фото с котом", [], photo_candidates=candidates
    )
    llm = get_content().llm
    assert llm.photo_album_header.strip() in prompt
    assert llm.photo_album_instruction.strip() in prompt


def test_prompt_builder_requires_marker_on_explicit_photo_request():
    from vanessa.core.messages import PhotoCandidate

    builder = PromptBuilder()
    candidates = [PhotoCandidate(index=1, telegram_file_id="f1", caption="кот")]
    prompt = builder.build_user_prompt(
        "отправь картинку", [], photo_candidates=candidates
    )
    assert get_content().llm.photo_request_required_note.strip() in prompt


def test_prompt_builder_omits_required_note_without_photo_request():
    from vanessa.core.messages import PhotoCandidate

    builder = PromptBuilder()
    candidates = [PhotoCandidate(index=1, telegram_file_id="f1", caption="кот")]
    prompt = builder.build_user_prompt("как дела", [], photo_candidates=candidates)
    assert get_content().llm.photo_request_required_note.strip() not in prompt


def test_prompt_builder_renders_empty_note_on_photo_request_without_candidates():
    """The reported bug: «отправь любую картинку» with no album must make the
    model refuse honestly instead of faking a 'sent' claim."""
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("отправь любую картинку", [])
    assert get_content().llm.photo_album_empty_note.strip() in prompt


def test_prompt_builder_omits_empty_note_on_normal_message():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет как дела", [])
    assert get_content().llm.photo_album_empty_note.strip() not in prompt


def test_current_message_renders_attached_photos_in_same_msg():
    """A person wrote a message AND sent a picture: the photo must appear in the
    SAME <msg> as the text, so the bot never loses which photo goes with which
    caption (the reported confusion). All photos of the message stay together."""
    builder = PromptBuilder()
    photo = ImageAttachment(
        data_url="data:image/jpeg;base64,AAAA",
        mime_type="image/jpeg",
        telegram_file_id="file-1",
    )
    prompt = builder.build_user_prompt(
        "Ванесса что думаешь",
        [],
        sender_telegram_id=42,
        sender_name="Котгаст",
        current_images=[photo],
    )
    # The photo is rendered as an <attachment> child INSIDE the <msg> that
    # carries the <text> — not as a detached album entry.
    assert '<msg sender="Котгаст"' in prompt
    assert "Ванесса что думаешь" in prompt
    assert '<attachment type="photo"' in prompt
    # The attachment sits inside the same <msg> block as the text.
    msg_start = prompt.index("<msg")
    text_index = prompt.index("Ванесса что думаешь")
    attach_index = prompt.index('<attachment type="photo"')
    assert msg_start < text_index < attach_index


def test_current_message_renders_all_attached_photos():
    """If a message carried several photos, ALL of them are rendered with the
    message text (one <attachment> per photo inside the same <msg>)."""
    builder = PromptBuilder()
    photos = [
        ImageAttachment(
            data_url=f"data:image/jpeg;base64,{i}",
            mime_type="image/jpeg",
            telegram_file_id=f"file-{i}",
        )
        for i in range(2)
    ]
    prompt = builder.build_user_prompt("вот фото", [], current_images=photos)
    assert prompt.count('<attachment type="photo"') == 2
    # Both attachments appear after the text, inside the single current <msg>.
    assert prompt.index("вот фото") < prompt.index('<attachment type="photo"')
    assert prompt.count("<msg") == 1


def test_current_message_omits_attachments_without_images():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert '<attachment type="photo"' not in prompt


def test_system_prompt_block_order_role_constraints_examples():
    """Recommended order: role -> constraints -> examples (examples last)."""
    builder = PromptBuilder()
    prompt = builder.system_prompt
    assert "## Examples" in prompt
    before_examples = prompt.split("## Examples")[0]
    for header in (
        "## Persona",
        "## Content rules",
        "## Answer formulation",
        "## Reply language",
    ):
        assert header in before_examples


def test_system_prompt_examples_not_fused_into_answer_format():
    """The few-shot examples are a separate block, not part of Answer
    formulation (the answer checklist stays in the constraints section)."""
    builder = PromptBuilder()
    prompt = builder.system_prompt
    answer_section, _, examples_section = prompt.partition("## Examples")
    assert "Before replying, check" in answer_section
    assert "Before replying, check" not in examples_section
    assert "Bad:" in examples_section
    assert "Good:" in examples_section


def test_user_prompt_block_order_directives_then_input_then_task():
    """Recommended order: constraints/directives -> input data -> final task."""
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "расскажи подробнее про гошу",
        context_blocks=[
            ContextBlock(
                anchor_id=1,
                messages=(
                    ContextMessage(id=1, role="user", content="старое сообщение"),
                ),
            )
        ],
        session_messages=[
            ContextMessage(id=2, role="user", content="недавняя реплика")
        ],
        knowledge_blocks=[
            KnowledgeBlock(
                path="People/гоша.md",
                title="гоша",
                kind="people",
                content="Гоша — программист.",
            )
        ],
        detail="detailed",
    )
    llm = get_content().llm
    # Constraints (detail note) come before the input data.
    assert prompt.index(llm.detail_note_detailed.strip()) < prompt.index(
        llm.context_header
    )
    # Input data keeps the natural order: history -> knowledge -> session ->
    # current message.
    assert prompt.index(llm.context_header) < prompt.index(llm.knowledge_header)
    assert prompt.index(llm.knowledge_header) < prompt.index(llm.session_header)
    assert prompt.index(llm.session_header) < prompt.index(llm.current_message_header)
    # The final task closes the prompt, right after the current message.
    assert prompt.index(llm.current_message_header) < prompt.index(llm.final_task_text())
    assert prompt.rstrip().endswith(llm.final_task_text())


def test_user_prompt_includes_final_task_line():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert get_content().llm.final_task_text() in prompt
