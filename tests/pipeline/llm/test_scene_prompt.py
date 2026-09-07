from vanessa.config.channels import load_channel_profile
from vanessa.config.content import get_content
from vanessa.core.messages import PhotoCandidate
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.llm.prompts.prompt_system import build_system_prompt


def test_scene_block_injected_when_description_present() -> None:
    prompt = PromptBuilder().build_user_prompt(
        "what is that",
        [],
        scene_description="a neon plaza with two avatars",
    )
    assert "<scene>" in prompt
    assert "a neon plaza with two avatars" in prompt
    assert "off-camera" in prompt or "not in the block" in prompt


def test_scene_block_omitted_when_missing() -> None:
    prompt = PromptBuilder().build_user_prompt("привет", [])
    assert "<scene>" not in prompt
    assert "I see nothing" not in prompt


def test_vrchat_system_prompt_skips_stickers_and_adds_addendum() -> None:
    content = get_content()
    profile = load_channel_profile("vrchat")
    prompt = build_system_prompt(content, profile=profile)
    assert "## Stickers" not in prompt
    assert "[next]" in prompt or "single spoken" in prompt
    assert "VRChat" in prompt
    telegram = build_system_prompt(content)
    if content.stickers.enabled:
        assert "## Stickers" in telegram


def test_telegram_system_prompt_unchanged_without_profile() -> None:
    content = get_content()
    assert build_system_prompt(content) == build_system_prompt(
        content, profile=load_channel_profile("telegram")
    )


def test_photos_off_skips_album_chunks() -> None:
    profile = load_channel_profile("vrchat")
    prompt = PromptBuilder().build_user_prompt(
        "скинь фото кота",
        [],
        channel_profile=profile,
        photo_candidates=[
            PhotoCandidate(
                index=1,
                telegram_file_id="file-1",
                caption="кот",
            )
        ],
    )
    assert get_content().llm.photo_album_header not in prompt
