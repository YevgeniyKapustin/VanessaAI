from __future__ import annotations

import socket
from typing import Protocol

from services.presence.osc.packets import encode_osc

try:
    from pythonosc.udp_client import SimpleUDPClient
except ImportError:
    SimpleUDPClient = None


class OscSender(Protocol):
    def send(self, address: str, *values: object) -> None: ...


class RecordingOsc:
    def __init__(self) -> None:
        self.sent: list[tuple[str, tuple[object, ...]]] = []

    def send(self, address: str, *values: object) -> None:
        self.sent.append((address, values))


class SocketOsc:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        sock: socket.socket | None = None,
    ) -> None:
        self._addr = (host, port)
        self._owns = sock is None
        self._sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, *values: object) -> None:
        self._sock.sendto(encode_osc(address, *values), self._addr)

    def close(self) -> None:
        if self._owns:
            self._sock.close()


class PythonOsc:
    def __init__(self, host: str, port: int) -> None:
        if SimpleUDPClient is None:
            raise ImportError("pythonosc")
        self._client = SimpleUDPClient(host, port)

    def send(self, address: str, *values: object) -> None:
        payload: object
        if not values:
            payload = []
        elif len(values) == 1:
            payload = values[0]
        else:
            payload = list(values)
        self._client.send_message(address, payload)


def build_sender(
    host: str,
    port: int,
    *,
    sock: socket.socket | None = None,
) -> OscSender:
    if sock is not None:
        return SocketOsc(host, port, sock=sock)
    try:
        return PythonOsc(host, port)
    except ImportError:
        return SocketOsc(host, port)
