"""RPC reply scanning for Redis Streams private reply channels."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from vanessa.contracts.messages import BrokerMessage
from vanessa.infrastructure.broker.errors import BrokerError, BrokerTimeoutError
from vanessa.infrastructure.broker.serialization import decode
from vanessa.infrastructure.observability.metrics import record_broker_rpc


@dataclass(frozen=True, slots=True)
class _RpcScan:
    message: BrokerMessage
    expect_kinds: set[str]
    on_message: Callable[[BrokerMessage], Any] | None
    started: float


def _rpc_reply_matches(decoded: BrokerMessage, scan: _RpcScan) -> bool:
    return (
        decoded.correlation_id == scan.message.correlation_id
        and decoded.message_kind() in scan.expect_kinds
    )


async def _forward_rpc_message(
    on_message: Callable[[BrokerMessage], Any] | None,
    decoded: BrokerMessage,
) -> None:
    if on_message is None:
        return
    result = on_message(decoded)
    if asyncio.iscoroutine(result):
        await result


async def _match_rpc_entry(fields: Any, scan: _RpcScan) -> BrokerMessage | None:
    decoded = decode(fields)
    await _forward_rpc_message(scan.on_message, decoded)
    if not _rpc_reply_matches(decoded, scan):
        return None
    record_broker_rpc(scan.message.message_kind(), time.monotonic() - scan.started)
    return decoded


async def _scan_rpc_batch(
    response: Any,
    last_id: Any,
    scan: _RpcScan,
) -> tuple[BrokerMessage | None, Any]:
    for _stream_name, entries in response:
        for entry_id, fields in entries:
            last_id = entry_id
            matched = await _match_rpc_entry(fields, scan)
            if matched is not None:
                return matched, last_id
    return None, last_id


async def _poll_rpc_response(client: Any, reply_stream: str, last_id: Any) -> Any:
    # Non-blocking read (no BLOCK option — BLOCK 0 would wait forever).
    response = await client.xread({reply_stream: last_id}, count=32)
    if response:
        return response
    await asyncio.sleep(0.05)
    return None


async def _read_rpc_match(
    client: Any,
    reply_stream: str,
    last_id: Any,
    scan: _RpcScan,
) -> tuple[BrokerMessage | None, Any]:
    response = await _poll_rpc_response(client, reply_stream, last_id)
    if response is None:
        return None, last_id
    return await _scan_rpc_batch(response, last_id, scan)


def _expect_kinds(
    expect: type[BrokerMessage] | tuple[type[BrokerMessage], ...],
) -> set[str]:
    kinds = expect if isinstance(expect, tuple) else (expect,)
    return {model.message_kind() for model in kinds}


def _raise_if_rpc_timeout(
    remaining: float,
    expect_kinds: set[str],
    message: BrokerMessage,
    timeout: float,
) -> None:
    if remaining > 0:
        return
    raise BrokerTimeoutError(
        f"no {sorted(expect_kinds)} reply for "
        f"{message.message_kind()} {message.correlation_id} "
        f"within {timeout}s"
    )


async def _rpc_request(
    client: Any,
    *,
    publish: Callable[..., Awaitable[str]],
    stream: str,
    message: BrokerMessage,
    timeout: float,
    expect: type[BrokerMessage] | tuple[type[BrokerMessage], ...],
    on_message: Callable[[BrokerMessage], Any] | None = None,
) -> BrokerMessage:
    """Publish an RPC request and block until the expected reply arrives.

    Replies are read from ``message.reply_to`` — a private per-request
    channel — so concurrent requests never steal each other's replies.
    Intermediate messages (e.g. ``TurnStarted``) are forwarded to
    ``on_message`` and skipped.
    """
    if not message.reply_to:
        raise BrokerError("RPC request requires a reply_to stream")
    expect_kinds = _expect_kinds(expect)
    await publish(stream, message)
    started = time.monotonic()
    reply_stream = message.reply_to
    # Start from the beginning of the PRIVATE reply stream ("0", not "$"):
    # "$" only returns entries appended after the call, so a fast reply
    # published before the first read would be missed forever.
    last_id = "0"
    deadline = started + timeout
    scan = _RpcScan(message, expect_kinds, on_message, started)
    while True:
        remaining = deadline - time.monotonic()
        _raise_if_rpc_timeout(remaining, expect_kinds, message, timeout)
        matched, last_id = await _read_rpc_match(
            client, reply_stream, last_id, scan
        )
        if matched is not None:
            return matched
