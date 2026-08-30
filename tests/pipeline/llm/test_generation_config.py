from vanessa.config.content import get_content
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams


def test_composer_generation_loaded_from_content():
    content = get_content()
    params = content.llm.generation.composer.to_params()
    assert isinstance(params, LLMGenerationParams)
    assert params.temperature == 0.8
    assert params.top_p == 0.9
    # The composer runs on a reasoning (V4) model whose chain-of-thought counts
    # against max_tokens — the budget must cover reasoning + [answer] tag + the
    # reply itself, not just the final message.
    assert params.max_tokens == 2048
    assert params.presence_penalty == 0.4
    assert params.frequency_penalty == 0.35
    # The composer runs a medium chain of thought on every reply — the default
    # tradeoff vs low (faster) and high (more careful, slower). reasoning_effort
    # is forwarded to the DeepSeek V4 API.
    assert params.reasoning_effort == "medium"
    assert params.to_llm_kwargs()["reasoning_effort"] == "medium"


def test_planner_generation_is_more_deterministic():
    params = get_content().llm.generation.planner.to_params()
    assert params.temperature == 0.1
    assert params.top_p == 0.85
    # The planner is a fast classification step (strict JSON, ~300 tokens) that
    # deliberately runs WITHOUT reasoning — 2048 comfortably covers the JSON.
    assert params.max_tokens == 2048
    assert params.reasoning_effort is None
    assert "reasoning_effort" not in params.to_llm_kwargs()


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


def test_planner_does_not_configure_reasoning():
    # The planner must NOT request a chain of thought: reasoning_effort stays
    # unset (None → the API's default normal mode), so the flag-classification
    # step does not eat response time and the parameter never reaches the API.
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
    from vanessa.config.conversation_config import load_conversation_config

    config = load_conversation_config()
    assert config.session_window_size == 20
    assert config.session_idle_seconds == 300.0
    assert config.post_reply_listen_count == 4
