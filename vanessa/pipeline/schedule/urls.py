"""Keep links in scheduled posts exactly as the user wrote them."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s<>\"'«»\[\]]+", re.IGNORECASE)
_TRAILING = ".,;:!?…"


def _trim(url: str) -> str:
    url = url.rstrip(_TRAILING)
    # "(see https://x.y/a)" → drop the ")" that closes the prose bracket.
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(_TRAILING)
    return url


def extract_urls(text: str) -> list[str]:
    """Links in order of appearance, without duplicates."""
    found: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = _trim(match.group(0))
        if url and url not in found:
            found.append(url)
    return found


def keep_urls(text: str, source: str) -> str:
    """Append every link from ``source`` that ``text`` lost or changed."""
    missing = [url for url in extract_urls(source) if url not in text]
    if not missing:
        return text
    return "\n".join([text.rstrip(), *missing])


def urls_intact(text: str, urls: list[str]) -> bool:
    """True when each link is present and not hidden inside a markdown link."""
    return all(url in text and f"]({url}" not in text for url in urls)


__all__ = ["extract_urls", "keep_urls", "urls_intact"]
