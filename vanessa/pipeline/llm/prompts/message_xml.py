"""XML-like rendering of the compose prompt's dynamic input block.

The compose prompt follows a "Markdown system + XML input" architecture:

- the system prompt (Markdown) carries role, character and rules;
- the dynamic per-turn data — old chat history, the recent session, the current
  message, replies and photo descriptions — is rendered here with lightweight
  XML-like tags, so the model cleanly separates metadata (who wrote, when,
  reply links) from the verbatim message text and photo labels:

    <messages>
      <msg id="1" sender="Евгений" sender_type="human" time="04.07.2026 08:08">
        <text>привет, сколько стоит футболка?</text>
      </msg>
      <msg id="2" sender="bot" sender_type="self" time="04.07.2026 08:09">
        <text>вот фото модели в наличии</text>
        <attachment type="photo">
          <description>black oversized t-shirt with a print</description>
        </attachment>
      </msg>
    </messages>

- the reply is plain text (only the planner returns JSON).

Conventions (documented to the model in ``compose/system.yaml`` → ``task:``):

- ``<msg>`` — one chat message. Attributes: ``id`` (message number, target of
  ``reply_to`` links), ``sender`` (a participant's display name, or ``bot`` for
  Vanessa), ``sender_type`` (human, bot or self), ``time`` (when it was sent),
  ``reply_sender`` (the quoted author), ``anchor="true"`` (the RAG anchor of a
  context block), ``reply_to="<id>"`` (this message replies to message <id>).
- ``<text>`` — the only message content, a verbatim quote.
- ``<reply_text>`` — the text of the message this one replies to.
- ``<attachment type="photo">`` with a ``<description>`` child — a photo on the
  message and a short label of what is on it.

Message bodies are escaped so a literal ``<...>`` or ``&`` in a message never
breaks the markup. This module is intentionally plain (no XML parser): the
markup is a convention for the model, not something the app parses back.
"""

from __future__ import annotations

from html import escape

from vanessa.core.bot_senders import is_bot_sender_label

# Value placed in the ``sender`` attribute of Vanessa's own messages.
BOT_SENDER = "bot"


def message_sender_type(role: str, sender: str | None) -> str:
    if role == "assistant":
        return "self"
    if is_bot_sender_label(sender):
        return "bot"
    return "human"


def xml_text(value: str | None) -> str:
    """Escape text placed inside an XML element body (tags/entities)."""
    return escape(value or "", quote=False)


def xml_attr(value: object) -> str:
    """Escape a value placed inside an XML attribute (quotes + entities)."""
    return escape(str(value), quote=True)


def render_attachment(
    description: str | None = None,
    *,
    kind: str = "photo",
) -> str:
    """A ``<attachment type="...">`` element, indented for a ``<msg>`` body.

    ``kind`` is what the image is — ``photo`` for a user photo, ``sticker`` or
    ``gif`` for a Telegram sticker / GIF preview frame. With a description it
    carries a ``<description>`` child; a bare image (no description available)
    is rendered self-closing so the model still knows an image was attached.
    """
    attachment_type = xml_attr(kind or "photo")
    if description and description.strip():
        return (
            f'  <attachment type="{attachment_type}">\n'
            f"    <description>{xml_text(description)}</description>\n"
            "  </attachment>"
        )
    return f'  <attachment type="{attachment_type}" />'


def _reply_attrs(reply_to: int | None, reply_sender: str | None) -> list[str]:
    attrs = []
    if reply_to is not None:
        attrs.append(f'reply_to="{reply_to}"')
    if reply_sender:
        attrs.append(f'reply_sender="{xml_attr(reply_sender)}"')
    return attrs


def _msg_attrs(
    *,
    sender: str,
    sender_type: str,
    time: str,
    msg_id: int | None,
    anchor: bool,
    reply_to: int | None,
    reply_sender: str | None,
) -> list[str]:
    attrs: list[str] = []
    if msg_id is not None:
        attrs.append(f'id="{msg_id}"')
    attrs.append(f'sender="{xml_attr(sender)}"')
    attrs.append(f'time="{xml_attr(time)}"')
    attrs.append(f'sender_type="{xml_attr(sender_type)}"')
    if anchor:
        attrs.append('anchor="true"')
    attrs.extend(_reply_attrs(reply_to, reply_sender))
    return attrs


def _msg_children(
    content: str,
    reply_text: str | None,
    attachments: list[str] | None,
) -> list[str]:
    lines: list[str] = []
    if reply_text and reply_text.strip():
        lines.append(f"  <reply_text>{xml_text(reply_text)}</reply_text>")
    lines.append(f"  <text>{xml_text(content)}</text>")
    lines.extend(attachments or [])
    return lines


def render_msg(
    *,
    content: str,
    sender: str,
    sender_type: str,
    time: str,
    msg_id: int | None = None,
    anchor: bool = False,
    reply_to: int | None = None,
    reply_text: str | None = None,
    reply_sender: str | None = None,
    attachments: list[str] | None = None,
) -> str:
    """A ``<msg>`` element with a verbatim ``<text>`` and optional children.

    ``attachments`` must already be rendered via :func:`render_attachment` (or
    any ``<attachment>`` string). ``reply_text`` is shown in ``<reply_text>``
    before ``<text>``; ``reply_to`` links to the ``<msg id>`` it quotes.
    """
    attrs = _msg_attrs(
        sender=sender,
        sender_type=sender_type,
        time=time,
        msg_id=msg_id,
        anchor=anchor,
        reply_to=reply_to,
        reply_sender=reply_sender,
    )
    lines = [f"<msg {' '.join(attrs)}>"]
    lines.extend(_msg_children(content, reply_text, attachments))
    lines.append("</msg>")
    return "\n".join(lines)


def render_messages(messages: list[str]) -> str:
    """Wrap already-rendered ``<msg>`` elements in a ``<messages>`` root."""
    if not messages:
        return ""
    return "<messages>\n" + "\n".join(messages) + "\n</messages>"


def message_attachment_blocks(
    attachments: tuple | None,
    photo_caption: str | None = None,
) -> list[str]:
    """Rendered ``<attachment>`` children for a message's images.

    ``attachments`` is the message's ``ImageAttachment`` sequence; a description
    falls back to the message's generated ``photo_caption`` label.
    """
    blocks: list[str] = []
    for attachment in attachments or ():
        description = (getattr(attachment, "description", None) or "").strip()
        if not description:
            description = (photo_caption or "").strip()
        kind = getattr(attachment, "kind", "photo") or "photo"
        blocks.append(render_attachment(description or None, kind=kind))
    return blocks
