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


def test_build_user_prompt_injects_attitude_note():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt(
        "привет",
        [],
        attitude_note="Vanessa's mood note: крабер keeps repeating the same "
        "topic in a loop — reply coldly and briefly.",
    )
    assert "reply coldly and briefly" in prompt
    assert "крабер keeps repeating the same topic" in prompt


def test_build_user_prompt_without_attitude_note():
    builder = PromptBuilder()
    prompt = builder.build_user_prompt("привет", [])
    assert "keeps repeating the same topic" not in prompt


def test_render_annoyance_note_formats_template():
    from app.knowledge.metrics.feedback import render_annoyance_note

    note = render_annoyance_note(name="крабер", annoyance=0.85)
    assert note is not None
    assert "крабер" in note
    assert "0.85" in note
