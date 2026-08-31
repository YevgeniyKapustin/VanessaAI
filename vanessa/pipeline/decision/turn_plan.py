from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TurnPlan:
    original: str
    text: str
    skip_search: bool
    tone: str = "neutral"
    humor_ok: bool = False
    humor_query: str = ""
    should_reply: bool | None = None
    deep_search: bool = False
    knowledge_indexes: tuple[str, ...] = ()
    knowledge_query: str = ""
    # True when the user asks a concrete fact about a person ("во что играет
    # Крабер?") -> the compose prompt injects the raw dossier; False (default)
    # injects only the compact LLM portrait as background context.
    knowledge_detail: bool = False
    # Live web search (the "googling" skill): when true, the Retrieve stage
    # runs a search API with ``web_query`` and injects the results into the
    # compose prompt as a "live web results" block. Used for fresh or external
    # facts the archive cannot hold (news, prices, current versions, unknown
    # people and things). ``web_query`` falls back to ``text`` when empty.
    web_search: bool = False
    web_query: str = ""
    needs_clarification: bool = False
    clarification_hint: str = ""
    # True when the turn needs the upscaled compose model (deepseek-v4-pro):
    # super-complex synthesis, coding, long multi-step reasoning. The gate
    # planner decides; the composer routes the generation call accordingly.
    uses_pro_model: bool = False
    # Short reason for declining a reply — filled only when should_reply=false
    # (planner skip=true means stay silent; the parser forces should_reply=false).
    reason: str = ""
    # Loop-repetition signal: the SAME sender keeps asking about the SAME TOPIC
    # in the recent context (different phrasings, same meaning — a loop «по
    # кругу»). ``repeated_topic`` is the boolean verdict; ``loop_level`` 0..3 is
    # how deep the loop is (1 = re-asked once, 2 = several times, 3 = stuck in a
    # constant loop). Feeds Vanessa's annoyance mechanic: a high loop level drops
    # her attitude, raises her ignore tendency and turns her replies cold.
    repeated_topic: bool = False
    loop_level: int = 0
    # Desired reply length chosen by the planner + the deterministic heuristic:
    # "brief" | "normal" | "detailed" ("normal" = the default persona voice).
    # Feeds a compose directive so Vanessa gives a fuller answer when the user
    # asks for detail and a one-liner when brevity is requested.
    detail: str = "normal"

    def to_trace_dict(self) -> dict[str, Any]:
        """Serialize the plan for the Langfuse trace (gate span output).

        Bounded, debugging-friendly projection of the planner's output. Omits
        ``original`` (the raw user message is already on the trace root) so the
        Langfuse observation panel stays readable while still showing every
        decision the planner made.
        """
        return {
            "search_query": self.text,
            "skip_search": self.skip_search,
            "should_reply": self.should_reply,
            "tone": self.tone,
            "humor_ok": self.humor_ok,
            "humor_query": self.humor_query,
            "deep_search": self.deep_search,
            "knowledge_indexes": list(self.knowledge_indexes),
            "knowledge_query": self.knowledge_query,
            "knowledge_detail": self.knowledge_detail,
            "web_search": self.web_search,
            "web_query": self.web_query,
            "needs_clarification": self.needs_clarification,
            "clarification_hint": self.clarification_hint,
            "uses_pro_model": self.uses_pro_model,
            "repeated_topic": self.repeated_topic,
            "loop_level": self.loop_level,
            "detail": self.detail,
            "reason": self.reason,
        }
