from vanessa.config.channels import ChannelProfile
from vanessa.config.content import AppContent

_SPLIT_OFF_NOTE = (
    "## Reply shape\n"
    "Reply as a single spoken message. Do not split the answer "
    "and do not emit [next] block markers."
)


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


def _stickers_enabled(
    content: AppContent, profile: ChannelProfile | None
) -> bool:
    if profile is not None and not profile.stickers:
        return False
    return content.stickers.enabled


def _sticker_section(
    content: AppContent, profile: ChannelProfile | None
) -> str | None:
    if not _stickers_enabled(content, profile):
        return None
    chunks = _sticker_chunks(content)
    if not chunks:
        return None
    return "## Stickers\n" + "\n\n".join(chunks)


def _split_section(profile: ChannelProfile | None) -> str | None:
    if profile is None or profile.split_messages:
        return None
    return _SPLIT_OFF_NOTE


def _channel_addendum(profile: ChannelProfile | None) -> str | None:
    if profile is None:
        return None
    text = profile.prompt_addendum.strip()
    if not text:
        return None
    return f"## Channel\n{text}"


def _profile_sections(
    content: AppContent, profile: ChannelProfile | None
) -> list[str]:
    parts: list[str] = []
    for section in (
        _profanity_section(content),
        _sticker_section(content, profile),
        _split_section(profile),
        _channel_addendum(profile),
    ):
        if section is not None:
            parts.append(section)
    return parts


def build_system_prompt(
    content: AppContent,
    profile: ChannelProfile | None = None,
) -> str:
    # Recommended block order for the system message (blocks 1-3):
    #   role/persona -> constraints/rules -> few-shot examples.
    # The examples close the system message so they sit right before the
    # dynamic input data that opens the user prompt (block 4) and the final
    # task that closes it (block 5).
    parts = _base_system_sections(content)
    parts.extend(_profile_sections(content, profile))
    # Few-shot examples — their own block, after every constraint (the
    # recommended "lower middle" position). The yaml block already carries
    # its own "## Examples" header, so it is appended whole.
    examples = content.llm.examples_text()
    if examples:
        parts.append(examples)
    return "\n\n".join(parts)
