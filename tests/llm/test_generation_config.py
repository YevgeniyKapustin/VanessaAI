from app.config.content import get_content
from app.llm.planner.generation_config import LLMGenerationParams


def test_composer_generation_loaded_from_content():
    content = get_content()
    params = content.llm.generation.composer.to_params()
    assert isinstance(params, LLMGenerationParams)
    assert params.temperature == 0.8
    assert params.top_p == 0.9
    assert params.max_tokens == 512
    assert params.presence_penalty == 0.4
    assert params.frequency_penalty == 0.35


def test_planner_generation_is_more_deterministic():
    params = get_content().llm.generation.planner.to_params()
    assert params.temperature == 0.1
    assert params.top_p == 0.85
    assert params.max_tokens == 192


def test_anthropic_kwargs_include_sampling_params():
    params = LLMGenerationParams(
        temperature=0.7,
        top_p=0.9,
        max_tokens=512,
    )
    assert params.to_anthropic_kwargs() == {
        "max_tokens": 512,
        "temperature": 0.7,
    }


def test_conversation_config_from_content():
    from app.config.conversation_config import load_conversation_config

    config = load_conversation_config()
    assert config.session_window_size == 12
    assert config.session_idle_seconds == 300.0
    assert config.post_reply_listen_count == 2
