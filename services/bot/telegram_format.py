import html
import re
from functools import partial

_FENCED_CODE = re.compile(r"```(\w*)\n?(.*?)\n?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")


def markdown_to_telegram_html(text: str) -> str:
    parts: list[str] = []
    last_end = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > last_end:
            parts.append(_format_prose(text[last_end : match.start()]))
        code = match.group(2).strip("\n")
        parts.append(f"<pre><code>{html.escape(code, quote=False)}</code></pre>")
        last_end = match.end()
    if last_end < len(text):
        parts.append(_format_prose(text[last_end:]))
    return "".join(parts) if parts else _format_prose(text)


def _format_prose(text: str) -> str:
    if not text:
        return ""
    return "".join(_prose_chunks(text))


def _prose_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    last = 0
    for match in _INLINE_CODE.finditer(text):
        chunks.extend(_code_span(text, last, match))
        last = match.end()
    _append_markup_tail(chunks, text, last)
    return chunks


def _code_span(text: str, last: int, match: re.Match[str]) -> list[str]:
    prefix = text[last : match.start()]
    pieces: list[str] = []
    if prefix:
        pieces.append(_format_inline_markup(prefix))
    pieces.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
    return pieces


def _append_markup_tail(chunks: list[str], text: str, last: int) -> None:
    if last < len(text):
        chunks.append(_format_inline_markup(text[last:]))


def _format_inline_markup(text: str) -> str:
    if not text:
        return ""
    placeholders: list[str] = []
    marked = _BOLD.sub(partial(_stash_markup, placeholders, "b"), text)
    marked = _ITALIC.sub(partial(_stash_markup, placeholders, "i"), marked)
    escaped = html.escape(marked, quote=False)
    return _restore_placeholders(escaped, placeholders)


def _stash_markup(
    placeholders: list[str], tag: str, match: re.Match[str]
) -> str:
    inner = html.escape(match.group(1), quote=False)
    placeholders.append(f"<{tag}>{inner}</{tag}>")
    return f"\x00{len(placeholders) - 1}\x00"


def _restore_placeholders(escaped: str, placeholders: list[str]) -> str:
    for index, fragment in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", fragment)
    return escaped
