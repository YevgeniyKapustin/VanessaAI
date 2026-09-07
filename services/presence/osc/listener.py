from __future__ import annotations

import asyncio
from collections.abc import Callable

from services.presence.osc.packets import decode_osc


class OscListenProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        on_packet: Callable[[str, tuple[object, ...]], None],
    ) -> None:
        self._on_packet = on_packet

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        del addr
        parsed = decode_osc(data)
        if parsed is None:
            return
        address, values = parsed
        self._on_packet(address, values)


async def start_osc_listener(
    host: str,
    port: int,
    on_packet: Callable[[str, tuple[object, ...]], None],
) -> tuple[asyncio.DatagramTransport, asyncio.DatagramProtocol]:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: OscListenProtocol(on_packet),
        local_addr=(host, port),
    )
    return transport, protocol
