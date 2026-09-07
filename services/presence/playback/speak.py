from __future__ import annotations

import asyncio

from services.presence.avatar import AvatarConfig, Gesture
from services.presence.osc.client import OscSender
from services.presence.osc.messages import float_param, parameter_message
from services.presence.playback.audio import AudioPlayer
from services.presence.playback.gestures import pick_gesture
from vanessa.core import SpeechAudio, SpeechSynthesizer
from vanessa.infrastructure.speech import visemes_from_pcm

_EMPTY_RATE = 24_000
_FRAME_MS = 20


async def speak_reply(
    text: str,
    *,
    avatar: AvatarConfig,
    osc: OscSender,
    synthesizer: SpeechSynthesizer,
    player: AudioPlayer,
    speaking: asyncio.Lock,
) -> None:
    async with speaking:
        await _speak_locked(
            text,
            avatar=avatar,
            osc=osc,
            synthesizer=synthesizer,
            player=player,
        )


async def _speak_locked(
    text: str,
    *,
    avatar: AvatarConfig,
    osc: OscSender,
    synthesizer: SpeechSynthesizer,
    player: AudioPlayer,
) -> None:
    gesture = pick_gesture(text, avatar)
    _set_gesture(osc, gesture, on=True)
    pcm, rate = _pcm_and_rate(await synthesizer.synthesize(text))
    play_task = asyncio.create_task(player.play(pcm, rate))
    await drive_visemes(pcm, rate, osc=osc, avatar=avatar)
    await play_task
    _set_gesture(osc, gesture, on=False)
    _reset_mouth(osc, avatar)


def _pcm_and_rate(audio: SpeechAudio | None) -> tuple[bytes, int]:
    if audio is None:
        return b"", _EMPTY_RATE
    return audio.pcm, audio.sample_rate


def _set_gesture(osc: OscSender, gesture: Gesture | None, *, on: bool) -> None:
    if gesture is None:
        return
    value = gesture.value if on else 0
    osc.send(*parameter_message(gesture.parameter, value))


def _reset_mouth(osc: OscSender, avatar: AvatarConfig) -> None:
    osc.send(*float_param(avatar.parameters.jaw_open, 0.0))
    osc.send(*float_param(avatar.parameters.voice, 0.0))


async def drive_visemes(
    pcm: bytes,
    sample_rate: int,
    *,
    osc: OscSender,
    avatar: AvatarConfig,
) -> None:
    if not pcm:
        return
    delay = _FRAME_MS / 1000
    for frame in visemes_from_pcm(pcm, sample_rate, frame_ms=_FRAME_MS):
        osc.send(*float_param(avatar.parameters.jaw_open, frame.jaw_open))
        osc.send(*float_param(avatar.parameters.voice, frame.voice))
        await asyncio.sleep(delay)
