from app.config.content import get_content
from app.llm.planner.generation_config import LLMGenerationParams


def test_composer_generation_loaded_from_content():
    content = get_content()
    params = content.llm.generation.composer.to_params()
    assert isinstance(params, LLMGenerationParams)
    assert params.temperature == 0.8
    assert params.top_p == 0.9
    # Headroom for the chain-of-thought prefix + [answer] tag on top of the
    # final message (reasoning must not eat the reply's token budget).
    assert params.max_tokens == 1024
    assert params.presence_penalty == 0.4
    assert params.frequency_penalty == 0.35


def test_planner_generation_is_more_deterministic():
    params = get_content().llm.generation.planner.to_params()
    assert params.temperature == 0.1
    assert params.top_p == 0.85
    assert params.max_tokens == 192


def test_llm_kwargs_include_sampling_params():
    params = LLMGenerationParams(
        temperature=0.7,
        top_p=0.9,
        max_tokens=512,
    )
    assert params.to_llm_kwargs() == {
        "max_tokens": 512,
        "temperature": 0.7,
    }


def test_reasoning_effort_omitted_by_default():
    # The gate planner must stay in the API's default normal mode — the
    # parameter is never sent unless explicitly configured.
    params = get_content().llm.generation.planner.to_params()
    assert params.reasoning_effort is None
    assert "reasoning_effort" not in params.to_llm_kwargs()


def test_reasoning_effort_sent_when_configured():
    params = LLMGenerationParams(
        temperature=0.1,
        top_p=0.85,
        max_tokens=192,
        reasoning_effort="high",
    )
    assert params.to_llm_kwargs()["reasoning_effort"] == "high"


def test_conversation_config_from_content():
    from app.config.conversation_config import load_conversation_config

    config = load_conversation_config()
    assert config.session_window_size == 10
    assert config.session_idle_seconds == 300.0
    assert config.post_reply_listen_count == 4
