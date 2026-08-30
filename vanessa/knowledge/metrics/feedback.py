"""Feedback: translate a metrics snapshot into the compose-prompt tone block.

The block is a compact, human-readable line about the sender that the composer
uses to modulate tone — while the hard persona rules (owner protections, no
meta, specific spellings) stay authoritative and are never overridden here.
"""

from __future__ import annotations

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.knowledge.metrics.schema import PersonMetrics


def render_feedback_block(
    *,
    name: str,
    metrics: PersonMetrics | None,
    mood: str = "",
) -> str | None:
    """Render the tone-block line for the compose prompt, or None when no data."""
    if metrics is None or not settings.feedback_tone_enabled:
        return None
    toxicity = f"{metrics.toxicity:.2f}" if metrics.toxicity is not None else "-"
    trust = metrics.trust_score if metrics.trust_score is not None else "-"
    distance = metrics.distance.value if metrics.distance else "unknown"
    content = get_content()
    return content.metrics.feedback_line.format(
        name=name,
        toxicity=toxicity,
        trust=trust,
        distance=distance,
        mood=mood or "?",
    )


def render_annoyance_note(*, name: str, annoyance: float) -> str | None:
    """Render the cold-reply directive for the compose prompt, or None when the
    template is not configured. The note tells the composer the sender keeps
    repeating the same topic and Vanessa is annoyed — reply dry and brief."""
    content = get_content()
    template = content.metrics.annoyance_note.strip()
    if not template:
        return None
    return template.format(name=name, annoyance=f"{annoyance:.2f}")
