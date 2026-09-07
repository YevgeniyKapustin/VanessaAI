from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from services.presence.avatar import IdleSection, OscSection, load_avatar
from services.presence.broker import PresenceBroker
from services.presence.capture.scale import default_encode
from services.presence.container import (
    create_presence_services,
    run_presence,
    stdin_producer,
)
from services.presence.ingress import parse_ingress_line, turn_from_osc
from services.presence.loop import handle_turn, run_queue, spoken_text
from services.presence.main import parse_args
from services.presence.models import PresenceReply, PresenceTurn
from services.presence.osc.client import RecordingOsc, SocketOsc
from services.presence.osc.listener import start_osc_listener
from services.presence.playback.audio import (
    DefaultPlayer,
    NullPlayer,
    RecordingPlayer,
    pcm16_to_wav,
)
from services.presence.playback.gestures import pick_gesture
from services.presence.playback.idle import (
    idle_breath,
    idle_look,
    idle_loop,
    send_idle_frame,
)
from services.presence.playback.speak import speak_reply
from services.presence.playback.speech import (
    NullSynthesizer,
    _call_factory,
    load_synthesizer,
)
from services.presence.playback.viseme import (
    pcm16_rms,
    rms_to_unit,
    viseme_unit,
    voice_from_unit,
)
from services.presence.turn_request import (
    presence_turn_payload,
    try_build_turn_request,
    vrchat_contract_ready,
)
from vanessa.contracts.messages import TurnReply, TurnRequest, TurnStarted
from vanessa.core import SpeechAudio
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams
from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech


def test_payload_matches_vrchat_contract() -> None:
    turn = PresenceTurn(message="hello", display_name="Kapusta", scene_jpeg=None)
    payload = presence_turn_payload(turn)
    assert payload["channel"] == "vrchat"
    assert payload["telegram_chat_id"] is None
    assert payload["sender_telegram_id"] is None
    assert payload["sender_first_name"] == "Kapusta"
    assert payload["mentions_bot"] is True
    assert payload["images"] == []
    assert payload["scene_image"] is None


def test_directed_stdin_and_osc_ingress() -> None:
    line = parse_ingress_line("Kapusta: hi there", default_name="You")
    assert line is not None
    assert line.display_name == "Kapusta"
    assert line.message == "hi there"
    bare = parse_ingress_line("ping", default_name="You")
    assert bare is not None
    assert bare.display_name == "You"
    osc = turn_from_osc("/vanessa/input", ("Ada", "wave"), default_name="You")
    assert osc is not None
    assert osc.display_name == "Ada"
    assert osc.message == "wave"
    assert parse_ingress_line("  ", default_name="You") is None
    assert turn_from_osc("/other", ("x",), default_name="You") is None


def test_try_build_turn_request_isolated_until_contract() -> None:
    turn = PresenceTurn(message="hello", display_name="Ada")
    built = try_build_turn_request(
        turn, correlation_id="vrchat:1", reply_to="vanessa:replies:p:1"
    )
    if vrchat_contract_ready():
        assert built is not None
        assert built.channel == "vrchat"
        assert built.telegram_chat_id is None
        assert built.scene_image is None
        return
    assert built is None


async def test_broker_process_none_when_contract_pending() -> None:
    if vrchat_contract_ready():
        pytest.skip("slice 1a contract already landed")
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    presence = PresenceBroker(broker, streams=streams, timeout=1.0, presence_id="p1")
    result = await presence.process(PresenceTurn(message="hi", display_name="Ada"))
    assert result is None


async def test_broker_process_vrchat_turn() -> None:
    if not vrchat_contract_ready():
        pytest.skip("waiting for slice 1a contract")
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    presence = PresenceBroker(broker, streams=streams, timeout=3.0, presence_id="p-vr")
    captured: list = []

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        captured.append(req)
        await broker.publish(
            req.reply_to,
            TurnReply(
                correlation_id=req.correlation_id,
                action="reply",
                reason="intent",
                reply="pong",
            ),
        )

    task = asyncio.create_task(
        broker.consume_forever(streams.turns, "agent", "w-vr", agent_side, poll_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    jpeg = b"\xff\xd8\xff\xd9"
    result = await presence.process(
        PresenceTurn(message="hello", display_name="Kapusta", scene_jpeg=jpeg)
    )
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert result is not None
    assert result.text == "pong"
    req = captured[0]
    assert req.channel == "vrchat"
    assert req.telegram_chat_id is None
    assert req.sender_telegram_id is None
    assert req.sender_first_name == "Kapusta"
    assert req.mentions_bot is True
    assert req.images == []
    assert req.scene_image is not None
    assert req.scene_image.telegram_file_id is None


async def test_broker_request_turn_roundtrip() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    presence = PresenceBroker(broker, streams=streams, timeout=3.0, presence_id="p2")
    request = TurnRequest(
        correlation_id="vrchat:test",
        telegram_chat_id=0,
        message="hello",
        sender_telegram_id=0,
        reply_to=streams.reply("p2", "vrchat:test"),
    )

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        await broker.publish(
            req.reply_to,
            TurnReply(
                correlation_id=req.correlation_id,
                action="reply",
                reason="intent",
                reply="pong",
            ),
        )

    task = asyncio.create_task(
        broker.consume_forever(streams.turns, "agent", "w1", agent_side, poll_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    result = await presence.request_turn(request)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert result.action == "reply"
    assert result.text == "pong"


def test_spoken_text_skips_non_reply() -> None:
    assert spoken_text(None) is None
    assert spoken_text(PresenceReply("ignore", "noise", "x")) is None
    assert spoken_text(PresenceReply("reply", "ok", "  hi ")) == "hi"


def test_viseme_and_gesture_from_avatar_yaml() -> None:
    avatar = load_avatar()
    assert avatar.parameters.jaw_open == "JawOpen"
    loud = b"\x00\x40" * 32
    assert viseme_unit(loud) > 0
    assert pcm16_rms(b"") == 0.0
    gesture = pick_gesture("hello there", avatar)
    assert gesture is not None
    assert gesture.parameter == "GestureWave"
    assert pick_gesture("zzz", avatar) is None
    assert 0.0 <= idle_breath(1.0, period=4.0) <= 1.0


async def test_speak_sends_jaw_open_and_voice() -> None:
    avatar = load_avatar()
    osc = RecordingOsc()
    player = RecordingPlayer()

    class Tone:
        async def synthesize(self, text: str) -> SpeechAudio:
            del text
            return SpeechAudio(pcm=b"\x00\x30" * 240, sample_rate=12000)

    await speak_reply(
        "hello",
        avatar=avatar,
        osc=osc,
        synthesizer=Tone(),
        player=player,
        speaking=asyncio.Lock(),
    )
    addresses = [item[0] for item in osc.sent]
    assert "/avatar/parameters/JawOpen" in addresses
    assert "/avatar/parameters/Voice" in addresses
    assert "/avatar/parameters/GestureWave" in addresses
    assert player.played


def test_null_synthesizer_and_wav_header() -> None:
    wav = pcm16_to_wav(b"\x00\x00" * 8, 24000)
    assert wav.startswith(b"RIFF")
    assert b"WAVE" in wav[:16]


def test_load_synthesizer_wires_infrastructure_factory() -> None:
    synth = load_synthesizer()
    assert isinstance(synth, (ElevenLabsSpeech, NullSynthesizer))


async def test_null_synthesizer_returns_empty_audio() -> None:
    audio = await NullSynthesizer().synthesize("hi")
    assert audio is not None
    assert audio.pcm == b""
    assert audio.sample_rate > 0


async def test_handle_turn_capture_fail_still_speaks() -> None:
    avatar = load_avatar()
    osc = RecordingOsc()
    player = RecordingPlayer()

    class FakeBroker:
        async def process(self, turn: PresenceTurn) -> PresenceReply:
            assert turn.scene_jpeg is None
            return PresenceReply("reply", "ok", "hello")

    class Tone:
        async def synthesize(self, text: str) -> SpeechAudio:
            del text
            return SpeechAudio(pcm=b"\x00\x10" * 120, sample_rate=12000)

    def _drop_encode(_shot, *, quality: int) -> bytes | None:
        del _shot, quality
        return None

    services = SimpleNamespace(
        grab=lambda: None,
        encode=_drop_encode,
        broker=FakeBroker(),
        avatar=avatar,
        osc=osc,
        synthesizer=Tone(),
        player=player,
        speaking=asyncio.Lock(),
    )
    await handle_turn(PresenceTurn("hi", "Ada"), services)
    assert player.played


def test_idle_sends_breath_parameter() -> None:
    avatar = load_avatar()
    osc = RecordingOsc()
    send_idle_frame(osc, avatar, 0.5)
    assert any(addr.endswith("Breath") for addr, _ in osc.sent)


async def test_idle_loop_emits_then_stops() -> None:
    avatar = load_avatar()
    osc = RecordingOsc()
    stop = asyncio.Event()
    task = asyncio.create_task(
        idle_loop(osc, avatar, asyncio.Lock(), stop, step=0.01)
    )
    await asyncio.sleep(0.03)
    stop.set()
    await task
    assert osc.sent


async def test_run_queue_stops_without_turn() -> None:
    services = SimpleNamespace(
        stop=asyncio.Event(),
        turns=asyncio.Queue(),
    )
    services.stop.set()
    await run_queue(services)


async def test_osc_listener_receives_packet() -> None:
    received: asyncio.Queue = asyncio.Queue()

    def on_packet(address: str, values: tuple[object, ...]) -> None:
        received.put_nowait((address, values))

    transport, _protocol = await start_osc_listener("127.0.0.1", 0, on_packet)
    sock = transport.get_extra_info("sockname")
    port = sock[1]
    sender = SocketOsc("127.0.0.1", port)
    sender.send("/vanessa/input", "Ada", "hi")
    address, values = await asyncio.wait_for(received.get(), timeout=2)
    transport.close()
    sender.close()
    assert address == "/vanessa/input"
    assert values == ("Ada", "hi")


def test_parse_args_and_default_encode() -> None:
    args = parse_args([])
    assert args.avatar is None
    jpeg = default_encode((8, 8, b"\x80\x10\x20" * 64), quality=55)
    assert jpeg is not None
    assert jpeg.startswith(b"\xff\xd8")


async def test_create_presence_services_closes() -> None:
    services = create_presence_services()
    assert services.avatar.speaker_name
    await services.close()


async def test_null_player_and_empty_default_player() -> None:
    await NullPlayer().play(b"abc", 16000)
    await DefaultPlayer().play(b"", 16000)


def test_spoken_empty_and_idle_edges() -> None:
    assert spoken_text(PresenceReply("reply", "ok", "   ")) is None
    assert idle_breath(1.0, period=0) == idle_breath(2.0, period=0)
    assert idle_look(1.0, period=0, amplitude=1.0) == 0.0
    assert rms_to_unit(1.0, peak=0) == 0.0
    assert voice_from_unit(0.001) == 0.0


def test_speech_factory_fallback() -> None:
    def boom():
        raise TypeError("nope")

    assert isinstance(_call_factory(boom), NullSynthesizer)


async def test_handle_turn_silent_on_ignore() -> None:
    avatar = load_avatar()

    class IgnoreBroker:
        async def process(self, turn: PresenceTurn) -> PresenceReply:
            del turn
            return PresenceReply("ignore", "noise", "x")

    def _drop_encode(_shot, *, quality: int) -> bytes | None:
        del _shot, quality
        return None

    services = SimpleNamespace(
        grab=lambda: None,
        encode=_drop_encode,
        broker=IgnoreBroker(),
        avatar=avatar,
        osc=RecordingOsc(),
        synthesizer=NullSynthesizer(),
        player=RecordingPlayer(),
        speaking=asyncio.Lock(),
    )
    await handle_turn(PresenceTurn("hi", "Ada"), services)
    assert services.player.played == []


async def test_run_queue_processes_then_stops() -> None:
    stop = asyncio.Event()
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(PresenceTurn("hi", "Ada"))

    class SilentBroker:
        async def process(self, turn: PresenceTurn) -> PresenceReply:
            del turn
            stop.set()
            return PresenceReply("ignore", "n", None)

    def _drop_encode(_shot, *, quality: int) -> bytes | None:
        del _shot, quality
        return None

    services = SimpleNamespace(
        stop=stop,
        turns=queue,
        grab=lambda: None,
        encode=_drop_encode,
        broker=SilentBroker(),
        avatar=load_avatar(),
        osc=RecordingOsc(),
        synthesizer=NullSynthesizer(),
        player=RecordingPlayer(),
        speaking=asyncio.Lock(),
    )
    await run_queue(services)


async def test_idle_skips_while_speaking_and_disabled() -> None:
    avatar = load_avatar()
    osc = RecordingOsc()
    speaking = asyncio.Lock()
    await speaking.acquire()
    stop = asyncio.Event()
    task = asyncio.create_task(idle_loop(osc, avatar, speaking, stop, step=0.01))
    await asyncio.sleep(0.03)
    stop.set()
    await task
    assert osc.sent == []
    disabled = avatar.model_copy(update={"idle": IdleSection(enabled=False)})
    halt = asyncio.Event()
    halt.set()
    await idle_loop(RecordingOsc(), disabled, asyncio.Lock(), halt)


async def test_broker_ping_and_started_ignored() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    presence = PresenceBroker(broker, streams=streams, timeout=3.0, presence_id="p3")
    await presence.ping()
    request = TurnRequest(
        correlation_id="vrchat:started",
        telegram_chat_id=0,
        message="hello",
        sender_telegram_id=0,
        reply_to=streams.reply("p3", "vrchat:started"),
    )

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        await broker.publish(req.reply_to, TurnStarted(correlation_id=req.correlation_id))
        await broker.publish(
            req.reply_to,
            TurnReply(
                correlation_id=req.correlation_id,
                action="reply",
                reason="ok",
                reply="hi",
            ),
        )

    task = asyncio.create_task(
        broker.consume_forever(streams.turns, "agent", "w2", agent_side, poll_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    result = await presence.request_turn(request)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert result.text == "hi"


async def test_stdin_producer_directed_line(monkeypatch) -> None:
    lines = iter(["Ada: hello\n", ""])

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
    turn = services.turns.get_nowait()
    assert turn.display_name == "Ada"
    assert turn.message == "hello"
    assert services.stop.is_set()


async def test_run_presence_with_stop_already_set() -> None:
    class Ping:
        async def ping(self) -> None:
            return None

    def _drop_encode(_shot, *, quality: int) -> bytes | None:
        del _shot, quality
        return None

    osc_section = OscSection(host="127.0.0.1", port=0, listen_port=0)
    avatar = load_avatar().model_copy(update={"osc": osc_section})
    services = SimpleNamespace(
        broker=Ping(),
        osc=RecordingOsc(),
        avatar=avatar,
        speaking=asyncio.Lock(),
        stop=asyncio.Event(),
        turns=asyncio.Queue(),
        grab=lambda: None,
        encode=_drop_encode,
    )
    services.stop.set()
    await run_presence(services)


async def test_speak_does_not_echo_chatbox() -> None:
    osc = RecordingOsc()
    await speak_reply(
        "zzz",
        avatar=load_avatar(),
        osc=osc,
        synthesizer=NullSynthesizer(),
        player=RecordingPlayer(),
        speaking=asyncio.Lock(),
    )
    assert all(item[0] != "/chatbox/input" for item in osc.sent)


async def test_speak_none_audio_plays_silence() -> None:
    class Quiet:
        async def synthesize(self, text: str) -> SpeechAudio | None:
            del text
            return None

    player = RecordingPlayer()
    await speak_reply(
        "hi",
        avatar=load_avatar(),
        osc=RecordingOsc(),
        synthesizer=Quiet(),
        player=player,
        speaking=asyncio.Lock(),
    )
    assert player.played == [(b"", 24_000)]


def test_pipe_ingress_and_single_osc_value() -> None:
    turn = parse_ingress_line("Ada|yo", default_name="You")
    assert turn is not None
    assert turn.display_name == "Ada"
    osc = turn_from_osc("/vanessa/input", ("only",), default_name="You")
    assert osc is not None
    assert osc.display_name == "You"
    assert osc.message == "only"
    assert turn_from_osc("/vanessa/input", (1, 2), default_name="You") is None
