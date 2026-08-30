from collections.abc import Callable
from typing import Any

from vanessa.core.protocols import IncomingTurnHandlerProtocol

HandlerBuilder = Callable[[Any], IncomingTurnHandlerProtocol]
