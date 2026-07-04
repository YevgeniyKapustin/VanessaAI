import html
import re

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
    chunks: list[str] = []
    last = 0
    for match in _INLINE_CODE.finditer(text):
        if match.start() > last:
            chunks.append(_format_inline_markup(text[last : match.start()]))
        chunks.append(
            f"<code>{html.escape(match.group(1), quote=False)}</code>"
        )
        last = match.end()
    if last < len(text):
        chunks.append(_format_inline_markup(text[last:]))
    return "".join(chunks)


def _format_inline_markup(text: str) -> str:
    if not text:
        return ""
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    def bold_repl(match: re.Match[str]) -> str:
        inner = html.escape(match.group(1), quote=False)
        return stash(f"<b>{inner}</b>")

    def italic_repl(match: re.Match[str]) -> str:
        inner = html.escape(match.group(1), quote=False)
        return stash(f"<i>{inner}</i>")

    marked = _BOLD.sub(bold_repl, text)
    marked = _ITALIC.sub(italic_repl, marked)
    escaped = html.escape(marked, quote=False)
    for index, fragment in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", fragment)
    return escaped
