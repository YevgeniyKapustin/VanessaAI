from vanessa.config.content import AppContent


def _base_system_sections(content: AppContent) -> list[str]:
    persona = content.persona
    llm = content.llm
    sections = [
        ("Persona", persona.identity_text()),
        ("Voice", persona.voice_text()),
        ("Content rules", persona.rules_text()),
        ("Context handling", llm.task_text()),
        ("Answer formulation", llm.answer_format_text()),
        ("Reply language", llm.language_text()),
    ]
    return [f"## {title}\n{body}" for title, body in sections if body]


def _profanity_section(content: AppContent) -> str | None:
    profanity = content.profanity
    if not profanity.enabled:
        return None
    instruction = profanity.instruction.strip()
    if not instruction:
        return None
    return f"## Emotional language\n{instruction}"


def _sticker_chunks(content: AppContent) -> list[str]:
    sections: list[str] = []
    instruction = content.llm.sticker_instruction.strip()
    if instruction:
        sections.append(instruction)
    xml_block = content.stickers.xml_system_block()
    if xml_block:
        sections.append(xml_block)
    return sections


def _sticker_section(content: AppContent) -> str | None:
    if not content.stickers.enabled:
        return None
    chunks = _sticker_chunks(content)
    if not chunks:
        return None
    return "## Stickers\n" + "\n\n".join(chunks)


def build_system_prompt(content: AppContent) -> str:
    # Recommended block order for the system message (blocks 1-3):
    #   role/persona -> constraints/rules -> few-shot examples.
    # The examples close the system message so they sit right before the
    # dynamic input data that opens the user prompt (block 4) and the final
    # task that closes it (block 5).
    parts = _base_system_sections(content)
    profanity = _profanity_section(content)
    if profanity is not None:
        parts.append(profanity)
    stickers = _sticker_section(content)
    if stickers is not None:
        parts.append(stickers)
    # Few-shot examples — their own block, after every constraint (the
    # recommended "lower middle" position). The yaml block already carries
    # its own "## Examples" header, so it is appended whole.
    examples = content.llm.examples_text()
    if examples:
        parts.append(examples)
    return "\n\n".join(parts)
