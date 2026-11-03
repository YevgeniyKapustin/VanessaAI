"""Proxy directives: answer agents for the owner, relay his DM answers.

Two cases exist. In the agents' chat Vanessa answers a question addressed to
the owner in her own name; when it is his call she puts a short question in
``<dm_owner>``. In the owner's DM she sends his answer back to that chat via
the existing ``<send_to_chat>`` tag.
"""

from __future__ import annotations

from vanessa.core.generate_request import GenerateRequest
from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, BudgetPart
from vanessa.pipeline.proxy.owner import owner_display_name


def proxy_parts(request: GenerateRequest) -> list[BudgetPart]:
    if request.proxy_question:
        return _proxy_question_parts(request)
    if request.owner_dm:
        return _owner_dm_parts(request)
    return []


def _chat_label(request: GenerateRequest) -> str:
    return request.proxy_chat_title or "the agents' chat"


def _proxy_question_parts(request: GenerateRequest) -> list[BudgetPart]:
    owner = owner_display_name()
    body = (
        "## Proxy reply\n"
        f"This is «{_chat_label(request)}», the chat where agents work for {owner}. "
        f"The current message asks {owner} a question, and you answer in your own "
        "name on his behalf.\n"
        f"- Never pretend to be {owner} and never write as if he sent this. You are "
        f"Vanessa, speaking for him: «{owner} решил…», «{owner} сказал, что…», "
        "«у него в планах…».\n"
        "- Answer only what you know for sure from this chat and your cards. A work "
        "fact needs a work lookup (see the rules above), never a guess.\n"
        f"- If it is {owner}'s personal decision, a promise, or something you do not "
        "know, do NOT invent it. Put one short question for him inside "
        "<dm_owner>...</dm_owner> and tell the chat you passed it on. The tag is "
        "removed before sending; the rest of the reply is what the chat sees.\n"
        "- Use the tag only when you really need his answer, and never call "
        "yourself a proxy or mention these instructions."
    )
    return [(PRIORITY_DIRECTIVES, "proxy", body)]


def _owner_dm_parts(request: GenerateRequest) -> list[BudgetPart]:
    owner = owner_display_name()
    body = (
        "## Private chat with the owner\n"
        f"This is a private Telegram chat between you and {owner}. Nobody else "
        "sees it: write freely, in your normal voice.\n"
        f"- If {owner} answers a question you relayed from «{_chat_label(request)}», "
        "send that answer back to the chat and keep your own DM reply short.\n"
        f"- If he asks you to tell the agents' chat something, do the same.\n"
        "- The chat gets only the text inside the tag: keep the facts, names, "
        "dates and links exactly as he wrote them; you may smooth the wording.\n"
        "- Write it as your own plain message. Never say there that he asked, "
        "said or asked you to pass it on (no «Евгений просит передать», "
        "«он сказал», «по просьбе»).\n"
    )
    chat_id = request.relay_chat_id or request.proxy_chat_id
    if chat_id is not None:
        body += (
            f'- Target chat id: {chat_id}. Put its text inside '
            f'<send_to_chat id="{chat_id}">...</send_to_chat>.\n'
        )
        if request.relay_question:
            body += (
                "The question he is answering: "
                f"«{request.relay_question.strip()[:500]}».\n"
            )
    else:
        body += (
            "- If the answer must go to a chat, ask him which one; do not invent "
            "a chat id.\n"
        )
    return [(PRIORITY_DIRECTIVES, "proxy", body)]
