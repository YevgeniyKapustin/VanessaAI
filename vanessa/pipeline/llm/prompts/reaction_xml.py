"""Rendering of stored chat reactions for the compose / planner prompts.

A reaction is not a message: it has no <text>, no author message of its own,
and it always points at the message it was put on. It renders as a sibling of
``<msg>`` inside ``<messages>``::

    <reaction sender="Евгений" emoji="🔥" time="04.07.2026 08:08" to="17" />
"""

from vanessa.pipeline.llm.prompts.message_xml import xml_attr


def render_reaction(
    *,
    sender: str,
    emoji: str,
    time: str,
    to: int | None = None,
) -> str:
    """A ``<reaction>`` element: someone reacted to a message with one emoji.

    ``to`` is the ``<msg id>`` that was reacted to, when it could be resolved.
    """
    attrs = [
        f'sender="{xml_attr(sender)}"',
        f'emoji="{xml_attr(emoji)}"',
        f'time="{xml_attr(time)}"',
    ]
    if to is not None:
        attrs.append(f'to="{to}"')
    return f"<reaction {' '.join(attrs)} />"
