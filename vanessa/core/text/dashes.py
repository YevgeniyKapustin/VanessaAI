"""Plain punctuation: no typographic dashes in anything the bot says.

The em dash is the loudest tell of machine-written Russian, and the composer
reaches for it in almost every sentence. The swap lives here, in code, not in
the prompt: it holds when a prompt is edited and covers every producer (normal
replies, Hermes follow-ups, deploy announcements, owner DMs).

Fenced code is left alone — a dash inside a command or a snippet is data, and
rewriting it would break what the person is meant to copy.
"""

from __future__ import annotations

from vanessa.core.text.code_fences import map_outside_fences

#: Typographic dash code points and the plain hyphen each one becomes.
DASHES: dict[int, str] = {
    0x2012: "-",  # figure dash ‒
    0x2013: "-",  # en dash –
    0x2014: "-",  # em dash —
    0x2015: "-",  # horizontal bar ―
    0x2212: "-",  # minus sign −
}


def plain_dashes(text: str) -> str:
    """``«слово — слово»`` -> ``«слово - слово»``; fenced code untouched."""
    if not text:
        return text
    return map_outside_fences(text, _replace)


def _replace(chunk: str) -> str:
    return chunk.translate(DASHES)


__all__ = ["DASHES", "plain_dashes"]
