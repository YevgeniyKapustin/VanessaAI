from vanessa.pipeline.decision.gate.reaction.reaction_gate_prompt import (
    ReactionGateResult,
)


def _reply_to_bot_bypass(*, bypass_reply_to_bot: bool, reply_to_bot: bool) -> ReactionGateResult | None:
    if not bypass_reply_to_bot:
        return None
    if not reply_to_bot:
        return None
    return ReactionGateResult(respond=True, reason="reply_to_bot")


def _listen_window_bypass(
    *,
    bypass_listen_window: bool,
    in_listen_window: bool,
) -> ReactionGateResult | None:
    if not bypass_listen_window:
        return None
    if not in_listen_window:
        return None
    return ReactionGateResult(respond=True, reason="listen_window")


def gate_bypass_result(
    *,
    enabled: bool,
    bypass_reply_to_bot: bool,
    reply_to_bot: bool,
    bypass_listen_window: bool,
    in_listen_window: bool,
) -> ReactionGateResult | None:
    if not enabled:
        return ReactionGateResult(respond=True, reason="disabled")
    reply_bypass = _reply_to_bot_bypass(
        bypass_reply_to_bot=bypass_reply_to_bot,
        reply_to_bot=reply_to_bot,
    )
    if reply_bypass is not None:
        return reply_bypass
    return _listen_window_bypass(
        bypass_listen_window=bypass_listen_window,
        in_listen_window=in_listen_window,
    )
