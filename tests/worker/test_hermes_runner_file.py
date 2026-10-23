"""The runner sends a generated HTML file as a document, never as text."""

from services.worker.hermes.runner import HermesRunner
from tests.worker.hermes_fakes import (
    FakeBroker,
    FakeClient,
    FakeCompleter,
    make_ask,
    make_composer,
)
from vanessa.config.content_hermes import get_hermes_content
from vanessa.contracts.outbound import DOCUMENT_MAX_CHARS, OutboundMessage

PAGE = "<!doctype html><html><body><h1>Баги недели</h1></body></html>"
ANSWER = f'<vanessa_file name="bugs.html">\n{PAGE}\n</vanessa_file>\nГлавное: 3 бага.'


DEFAULT_FILE_MAX_BYTES = 262_144


def _runner(
    client,
    completer,
    broker,
    *,
    file_max_bytes: int = DEFAULT_FILE_MAX_BYTES,
    report_css: str = "",
):
    return HermesRunner(
        client,
        make_composer(completer),
        broker,
        outbound_stream="vanessa:outbound",
        instructions="work only",
        poll_seconds=0.0,
        max_wait_seconds=60.0,
        file_max_bytes=file_max_bytes,
        report_css=report_css,
    )


def _message(broker: FakeBroker) -> OutboundMessage:
    [(_stream, message)] = broker.published
    return message


def _prompt(completer: FakeCompleter) -> str:
    return completer.calls[0]["messages"][-1]["content"]


async def test_file_goes_as_document_and_llm_never_sees_html() -> None:
    broker = FakeBroker()
    completer = FakeCompleter("[answer]\nДержи отчёт, три бага.")
    await _runner(FakeClient(output=ANSWER), completer, broker).run(make_ask())
    message = _message(broker)
    assert message.text == "Держи отчёт, три бага"
    assert message.more_texts == []
    assert message.document is not None
    assert message.document.file_name == "bugs.html"
    assert message.document.content == PAGE
    prompt = _prompt(completer)
    assert "<html" not in prompt
    assert "[HTML file attached: bugs.html" in prompt
    assert get_hermes_content().file_attached_task.strip() in prompt


async def test_refused_file_sends_text_only() -> None:
    broker = FakeBroker()
    completer = FakeCompleter("[answer]\nОтчёт не собрался.")
    runner = _runner(FakeClient(output=ANSWER), completer, broker, file_max_bytes=10)
    await runner.run(make_ask())
    message = _message(broker)
    assert message.document is None
    assert message.text == "Отчёт не собрался"
    prompt = _prompt(completer)
    assert "[HTML file not sent: too big]" in prompt
    assert get_hermes_content().file_refused_task.strip() in prompt


async def test_llm_failure_with_file_still_sends_no_html() -> None:
    broker = FakeBroker()
    completer = FakeCompleter(error=RuntimeError("provider 500"))
    await _runner(FakeClient(output=ANSWER), completer, broker).run(make_ask())
    message = _message(broker)
    assert message.document is not None
    assert "<html" not in message.text
    assert "Главное: 3 бага" in message.text


async def test_file_caption_is_first_block_and_style_is_added() -> None:
    broker = FakeBroker()
    completer = FakeCompleter("[answer]\nСобрала отчёт.\n[next]\nТри бага горят.")
    runner = _runner(
        FakeClient(output=ANSWER), completer, broker, report_css=".sheet{color:red}"
    )
    await runner.run(make_ask())
    message = _message(broker)
    assert message.text == "Собрала отчёт"
    assert message.more_texts == ["Три бага горят"]
    assert message.document is not None
    content = message.document.content
    assert content.startswith("<!doctype html><html><style>\n.sheet{color:red}")
    assert content.endswith("</body></html>")


async def test_style_leaves_room_under_the_wire_cap() -> None:
    css = "x" * 1000
    runner = _runner(FakeClient(), FakeCompleter(), FakeBroker(), report_css=css)
    assert runner._file_max_bytes == DEFAULT_FILE_MAX_BYTES
    huge = _runner(
        FakeClient(), FakeCompleter(), FakeBroker(), file_max_bytes=10**9, report_css=css
    )
    assert huge._file_max_bytes + len(css) < DOCUMENT_MAX_CHARS


async def test_plain_answer_has_no_file_task() -> None:
    broker = FakeBroker()
    completer = FakeCompleter("[answer]\nVAN-1 в работе")
    await _runner(FakeClient(output="VAN-1 In Progress"), completer, broker).run(
        make_ask()
    )
    assert _message(broker).document is None
    prompt = _prompt(completer)
    prompts = get_hermes_content()
    assert prompts.file_attached_task.strip() not in prompt
    assert prompts.file_refused_task.strip() not in prompt


def test_file_tasks_are_configured() -> None:
    prompts = get_hermes_content()
    assert prompts.file_attached_task.strip()
    assert prompts.file_refused_task.strip()
    assert "<vanessa_file" in prompts.run_instructions
