from __future__ import annotations

import socket

import pytest

from services.presence.osc import client as osc_client
from services.presence.osc.client import (
    PythonOsc,
    RecordingOsc,
    SocketOsc,
    build_sender,
)
from services.presence.osc.messages import (
    avatar_param,
    chatbox_input,
    jaw_open,
    parameter_message,
    voice_level,
)
from services.presence.osc.packets import (
    decode_osc,
    decode_values,
    encode_osc,
    encode_value,
)


def test_avatar_param_and_clamped_visemes() -> None:
    assert avatar_param("JawOpen") == "/avatar/parameters/JawOpen"
    assert jaw_open(0.5) == ("/avatar/parameters/JawOpen", 0.5)
    assert jaw_open(2.0)[1] == 1.0
    assert jaw_open(-1.0)[1] == 0.0
    assert voice_level(0.25, parameter="Voice") == (
        "/avatar/parameters/Voice",
        0.25,
    )


def test_chatbox_and_gesture_shaping() -> None:
    assert chatbox_input("hi") == ("/chatbox/input", "hi", True)
    assert parameter_message("GestureWave", 1) == (
        "/avatar/parameters/GestureWave",
        1,
    )


def test_osc_encode_decode_roundtrip() -> None:
    packet = encode_osc("/vanessa/input", "Kapusta", "hello")
    parsed = decode_osc(packet)
    assert parsed is not None
    address, values = parsed
    assert address == "/vanessa/input"
    assert values == ("Kapusta", "hello")


def test_osc_bool_and_float_tags() -> None:
    payload = ["hi", True]
    packet = encode_osc("/chatbox/input", *payload)
    address, values = decode_osc(packet)
    assert address == "/chatbox/input"
    assert values[0] == "hi"
    assert values[1] is True
    packet_f = encode_osc("/avatar/parameters/JawOpen", 0.5)
    _addr, nums = decode_osc(packet_f)
    assert float(nums[0]) == pytest.approx(0.5)


def test_fake_udp_socket_records_payload() -> None:
    captured: list[bytes] = []

    class FakeSock:
        def sendto(self, data: bytes, addr) -> None:
            del addr
            captured.append(data)

        def close(self) -> None:
            return None

    sender = SocketOsc("127.0.0.1", 9000, sock=FakeSock())
    sender.send("/avatar/parameters/JawOpen", 0.4)
    assert captured
    address, values = decode_osc(captured[0])
    assert address == "/avatar/parameters/JawOpen"
    assert float(values[0]) == pytest.approx(0.4)


def test_build_sender_with_sock_skips_pythonosc() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender = build_sender("127.0.0.1", 9000, sock=sock)
        assert isinstance(sender, SocketOsc)
    finally:
        sock.close()


def test_recording_osc_appends() -> None:
    osc = RecordingOsc()
    flag = True
    osc.send("/x", 1, flag)
    assert osc.sent == [("/x", (1, flag))]


def test_osc_packet_edges() -> None:
    with pytest.raises(TypeError):
        encode_value(object())
    assert decode_osc(b"") is None
    assert decode_osc(b"xxxx") is None
    assert decode_values(b"") == ()


def test_pythonosc_missing_uses_socket_fallback(monkeypatch) -> None:
    monkeypatch.setattr(osc_client, "SimpleUDPClient", None)
    with pytest.raises(ImportError):
        PythonOsc("127.0.0.1", 9000)
    sender = build_sender("127.0.0.1", 9000)
    assert isinstance(sender, SocketOsc)
    sender.close()


def test_build_sender_prefers_pythonosc_when_present() -> None:
    if osc_client.SimpleUDPClient is None:
        pytest.skip("python-osc not installed")
    sender = build_sender("127.0.0.1", 9000)
    assert isinstance(sender, PythonOsc)


def test_socket_osc_owns_and_closes() -> None:
    sender = SocketOsc("127.0.0.1", 9000)
    sender.send("/ping", 1)
    sender.close()


def test_pythonosc_send_payload_shapes(monkeypatch) -> None:
    recorded: list = []

    class FakeUDP:
        def __init__(self, host: str, port: int) -> None:
            del host, port

        def send_message(self, address: str, payload: object) -> None:
            recorded.append((address, payload))

    monkeypatch.setattr(osc_client, "SimpleUDPClient", FakeUDP)
    client = osc_client.PythonOsc("127.0.0.1", 9000)
    client.send("/empty")
    client.send("/one", 1)
    client.send("/two", 1, 2)
    assert recorded[0][1] == []
    assert recorded[1][1] == 1
    assert recorded[2][1] == [1, 2]
