from vanessa.config.channels import (
    ChannelProfile,
    _load_channel_file,
    load_channel_profile,
    resolve_channels_dir,
)


def test_telegram_profile_keeps_current_agent_flags() -> None:
    profile = load_channel_profile("telegram")
    assert profile.channel == "telegram"
    assert profile.stickers is True
    assert profile.photos is True
    assert profile.split_messages is True
    assert profile.scene is False
    assert profile.speech is False
    assert profile.listen_window == "current"
    assert profile.addressing == "telegram"
    assert profile.prompt_addendum.strip() == ""


def test_vrchat_profile_agent_flags() -> None:
    profile = load_channel_profile("vrchat")
    assert profile.channel == "vrchat"
    assert profile.stickers is False
    assert profile.photos is False
    assert profile.split_messages is False
    assert profile.scene is True
    assert profile.speech is True
    assert profile.listen_window == "on"
    assert profile.addressing == "addressed"
    assert "VRChat" in profile.prompt_addendum


def test_unknown_channel_falls_back_to_telegram() -> None:
    profile = load_channel_profile("discord")
    assert profile.channel == "telegram"
    assert profile.scene is False


def test_yaml_boolean_listen_window() -> None:
    on_profile = ChannelProfile.model_validate({"listen_window": True})
    off_profile = ChannelProfile.model_validate({"listen_window": False})
    assert on_profile.listen_window == "on"
    assert off_profile.listen_window == "current"


def test_load_channel_file_non_dict_yaml(tmp_path, monkeypatch) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    monkeypatch.setattr(
        "vanessa.config.channels.resolve_channels_dir",
        lambda: tmp_path,
    )
    _load_channel_file.cache_clear()
    try:
        profile = load_channel_profile("telegram")
        assert profile.channel == "telegram"
    finally:
        _load_channel_file.cache_clear()


def test_resolve_channels_dir_points_at_config() -> None:
    folder = resolve_channels_dir()
    assert folder.name == "channels"
    assert (folder / "telegram.yaml").is_file()
    assert (folder / "vrchat.yaml").is_file()
