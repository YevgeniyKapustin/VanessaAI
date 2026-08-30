from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Per-request signal fired by the pipeline the moment the decision gate passes
# and Vanessa commits to an actual answer (as opposed to ignoring the message).
# The API chat route wires this to the SSE stream so the bot only shows the
# "typing..." indicator while a real reply is being composed — never for
# messages that get filtered out.
PlanningStartedSignal = Callable[[], Awaitable[None]]
planning_started_signal_var: ContextVar[PlanningStartedSignal | None] = ContextVar(
    "planning_started_signal",
    default=None,
)


def get_planning_started_signal() -> PlanningStartedSignal | None:
    return planning_started_signal_var.get()


def set_planning_started_signal(signal: PlanningStartedSignal | None) -> None:
    planning_started_signal_var.set(signal)


def get_request_id() -> str:
    return request_id_var.get()


def new_request_id() -> str:
    return str(uuid4())
