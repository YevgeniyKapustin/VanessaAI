"""VRChat presence adapter — a second channel adapter, not a pipeline role.

Run this process on the Windows PC that hosts VRChat. Do not put it in the
server Docker Compose or k8s manifests. OSC, screenshot, and TTS playback
stay on the game machine; the agent in Docker only sees Redis turns.

Host setup
----------
* Redis must be reachable from this PC. Set ``BROKER_REDIS_URL`` to the
  same broker the agent uses. If VRChat is not on the Docker host, do
  **not** use a container-only ``127.0.0.1`` — use the LAN IP, published
  port, or a tunnel.
* VRChat: Settings → OSC → Enable. This adapter sends UDP to localhost
  port **9000** (VRChat incoming). Optional listen port **9001** for
  harness input (``/vanessa/input``).
* Voice: play TTS to **VB-Cable** or VoiceMeeter, and select that cable
  as the VRChat microphone.

Start (repo root, poetry env)::

    python -m services.presence

Directed v1 ingress is stdin or OSC chatbox-style input (not STT).
Every such line is a directed turn. Format::

    DisplayName: hello
    hello

One session bucket: ``channel=vrchat`` (no fake Telegram chat id).
No stickers, photos, ``[next]``, HTML, or typing in this adapter.
"""
