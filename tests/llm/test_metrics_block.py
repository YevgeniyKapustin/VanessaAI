from app.llm.prompts.prompt_builder import PromptBuilder


def test_build_user_prompt_renders_metrics_block():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "привет",
        [],
        metrics_block="- крабер: toxicity 0.15, trust 70/100, tone friendly, mood ?",
    )
    assert "My mood and relationship notes about the sender:" in prompt
    assert "крабер" in prompt


def test_build_user_prompt_without_metrics_block():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "My mood and relationship notes about the sender:" not in prompt
