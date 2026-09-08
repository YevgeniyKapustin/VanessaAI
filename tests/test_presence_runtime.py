from __future__ import annotations

import asyncio
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.presence.avatar import load_avatar, resolve_avatar_path
from services.presence.broker import PresenceBroker
from services.presence.capture import default_grab
from services.presence.capture.grab import grab_win32_rgb
from services.presence.capture.jpeg_bits import BitWriter
from services.presence.capture.jpeg_encode import _flush_zeros, _write_ac
from services.presence.capture.scale import default_encode, jpeg_under_cap
from services.presence.container import (
    _try_listen,
    start_ingress_osc,
    stdin_producer,
)
from services.presence.loop import _handle_or_log, run_queue
from services.presence.main import async_main, main
from services.presence.models import PresenceTurn
from services.presence.osc.client import RecordingOsc
from services.presence.osc.listener import OscListenProtocol
from services.presence.osc.packets import decode_osc, encode_osc
from services.presence.playback.audio import DefaultPlayer, play_wav_bytes
from services.presence.playback.viseme import (
    chunk_bytes,
    iter_pcm_chunks,
    viseme_unit,
    voice_from_unit,
)
from services.presence.turn_request import (
    _is_optional_int,
    try_build_turn_request,
    vrchat_contract_ready,
)
from vanessa.infrastructure.broker.streams import BrokerStreams


def test_flush_zeros_emits_zrl() -> None:
    writer = BitWriter()
    left = _flush_zeros(writer, 16)
    assert left == 0
    writer = BitWriter()
    _write_ac(writer, [0] * 20 + [1])
    assert writer.flush()


def test_optional_int_and_contract_pending(monkeypatch) -> None:
    assert _is_optional_int(int) is False
    monkeypatch.setattr(
        "services.presence.turn_request.vrchat_contract_ready",
        lambda: False,
    )
    built = try_build_turn_request(
        PresenceTurn("hi", "Ada"),
        correlation_id="c",
        reply_to="r",
    )
    assert built is None


async def test_broker_logs_when_contract_pending(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.presence.broker.try_build_turn_request",
        lambda *_a, **_k: None,
    )
    streams = BrokerStreams(prefix="vanessa", turns="t", tasks="k")
    presence = PresenceBroker(SimpleNamespace(), streams=streams, timeout=1.0)
    assert await presence.process(PresenceTurn("hi", "Ada")) is None


def test_build_turn_request_validation_error(monkeypatch) -> None:
    def boom(**_kwargs):
        raise TypeError("bad payload")

    monkeypatch.setattr(
        "services.presence.turn_request.TurnRequest",
        boom,
    )
    monkeypatch.setattr(
        "services.presence.turn_request.vrchat_contract_ready",
        lambda: True,
    )
    assert (
        try_build_turn_request(
            PresenceTurn("hi", "Ada"),
            correlation_id="c",
            reply_to="r",
        )
        is None
    )


def test_viseme_chunks_and_voice_gate() -> None:
    pcm = b"\x00\x40" * 40
    chunks = iter_pcm_chunks(pcm, 8000)
    min_chunk = 2
    half = 0.5
    assert chunks
    assert chunk_bytes(8000) >= min_chunk
    assert viseme_unit(chunks[0]) >= 0.0
    assert voice_from_unit(half) == half


def test_grab_non_windows_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("services.presence.capture.grab.sys.platform", "linux")
    assert grab_win32_rgb() is None


def test_grab_swallows_oserror(monkeypatch) -> None:
    monkeypatch.setattr("services.presence.capture.grab.sys.platform", "win32")

    def boom() -> None:
        raise OSError("gdi")

    monkeypatch.setattr(
        "services.presence.capture.grab._capture_desktop",
        boom,
    )
    assert grab_win32_rgb() is None


def test_default_grab_pil_then_win32(monkeypatch) -> None:
    width = 2
    monkeypatch.setattr(
        "services.presence.capture._grab_pil",
        lambda: (width, width, b"\x00" * 12),
    )
    shot = default_grab()
    assert shot is not None
    assert shot[0] == width


def test_default_encode_pil_and_fallback(monkeypatch) -> None:
    rgb = b"\x10\x20\x30" * 64
    shot = (8, 8, rgb)

    class FakeImage:
        @staticmethod
        def frombytes(_mode, _size, _data):
            class Saved:
                def save(self, buffer, **_kwargs) -> None:
                    buffer.write(b"\xff\xd8pil\xff\xd9")

            return Saved()

    monkeypatch.setattr("services.presence.capture.scale.Image", FakeImage)
    blob = default_encode(shot, quality=40)
    assert blob == b"\xff\xd8pil\xff\xd9"

    monkeypatch.setattr("services.presence.capture.scale.Image", None)

    def boom(_shot, *, quality: int) -> bytes:
        del quality
        raise ValueError("encode")

    monkeypatch.setattr(
        "services.presence.capture.scale.rgb_to_jpeg",
        boom,
    )
    assert default_encode(shot, quality=40) is None


def test_jpeg_under_cap_skips_none_blobs() -> None:
    def encode(_shot, *, quality: int) -> bytes | None:
        del quality
        return None

    assert jpeg_under_cap((4, 4, b"\x00" * 48), encode=encode) is None


def test_osc_decode_edges() -> None:
    packet = encode_osc("/only")
    parsed = decode_osc(packet)
    assert parsed is not None
    assert parsed[1] == ()
    assert decode_osc(b"/x\x00") is not None
    protocol = OscListenProtocol(lambda *_a: None)
    protocol.datagram_received(b"xxxx", ("127.0.0.1", 1))


def test_avatar_path_env_and_non_dict(tmp_path, monkeypatch) -> None:
    yaml_path = tmp_path / "avatar.yaml"
    yaml_path.write_text("- not a mapping\n", encoding="utf-8")
    avatar = load_avatar(yaml_path)
    assert avatar.speaker_name == "You"
    monkeypatch.setenv("PRESENCE_AVATAR_PATH", str(yaml_path))
    assert resolve_avatar_path() == yaml_path
    monkeypatch.delenv("PRESENCE_AVATAR_PATH", raising=False)
    default = resolve_avatar_path()
    assert default.name == "avatar.yaml"
    assert default.is_file()


async def test_play_wav_bytes_and_default_player(monkeypatch, tmp_path) -> None:
    played: list[str] = []

    def play_sound(path, _flags) -> None:
        played.append(path)

    class FakeWin:
        SND_FILENAME = 1
        PlaySound = staticmethod(play_sound)

    monkeypatch.setattr("services.presence.playback.audio.winsound", FakeWin)
    wav = b"RIFF" + b"\x00" * 8
    play_wav_bytes(wav)
    assert played
    await DefaultPlayer().play(b"\x00\x10" * 8, 16000)


async def test_play_wav_skips_without_winsound(monkeypatch) -> None:
    monkeypatch.setattr("services.presence.playback.audio.winsound", None)
    play_wav_bytes(b"RIFF")


async def test_handle_turn_logs_broker_error() -> None:
    class BoomBroker:
        async def process(self, turn: PresenceTurn) -> None:
            del turn
            raise RuntimeError("redis")

    services = SimpleNamespace(
        grab=lambda: None,
        encode=lambda *_a, **_k: None,
        broker=BoomBroker(),
        avatar=load_avatar(),
        osc=RecordingOsc(),
        synthesizer=AsyncMock(),
        player=AsyncMock(),
        speaking=asyncio.Lock(),
        stop=asyncio.Event(),
        turns=asyncio.Queue(),
    )
    await _handle_or_log(PresenceTurn("hi", "Ada"), services)


async def test_run_queue_returns_when_stop_during_wait() -> None:
    stop = asyncio.Event()
    services = SimpleNamespace(stop=stop, turns=asyncio.Queue())
    task = asyncio.create_task(run_queue(services))
    await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


async def test_stdin_blank_line_keeps_running(monkeypatch) -> None:
    lines = iter(["   \n", ""])

    class FakeStdin:
        def readline(self) -> str:
            return next(lines)

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    services = SimpleNamespace(
        stop=asyncio.Event(),
        turns=asyncio.Queue(),
        avatar=load_avatar(),
    )
    await stdin_producer(services)
    assert services.turns.empty()
    assert services.stop.is_set()


async def test_start_ingress_osc_enqueues(monkeypatch) -> None:
    received: list = []

    async def fake_listen(host, port, on_packet):
        del host, port
        on_packet("/vanessa/input", ("Ada", "hi"))
        return SimpleNamespace(close=lambda: None), None

    monkeypatch.setattr(
        "services.presence.container.start_osc_listener",
        fake_listen,
    )
    services = SimpleNamespace(
        avatar=load_avatar(),
        turns=SimpleNamespace(put_nowait=received.append),
    )
    transport, _protocol = await start_ingress_osc(services)
    transport.close()
    assert received


async def test_try_listen_oserror(monkeypatch) -> None:
    async def boom(_services):
        raise OSError("bind")

    monkeypatch.setattr("services.presence.container.start_ingress_osc", boom)
    assert await _try_listen(SimpleNamespace(avatar=load_avatar())) is None


async def test_async_main_closes(monkeypatch) -> None:
    closed = {"n": 0}

    class FakeServices:
        avatar = load_avatar()

        async def close(self) -> None:
            closed["n"] += 1

    async def fake_run(_services) -> None:
        return None

    monkeypatch.setattr(
        "services.presence.main.create_presence_services",
        lambda **_k: FakeServices(),
    )
    monkeypatch.setattr("services.presence.main.run_presence", fake_run)
    monkeypatch.setattr("services.presence.main.configure_logging", lambda _n: None)
    await async_main([])
    assert closed["n"] == 1


def test_main_invokes_asyncio(monkeypatch) -> None:
    async def fake_async_main(_argv=None) -> None:
        return None

    monkeypatch.setattr("services.presence.main.async_main", fake_async_main)
    main()


def test_presence_main_module(monkeypatch) -> None:
    monkeypatch.setattr("services.presence.main.main", lambda: None)
    runpy.run_module("services.presence.__main__", run_name="__main__")


def test_contract_ready_true_on_current_schema() -> None:
    assert vrchat_contract_ready() is True
