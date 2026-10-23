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
from vanessa.contracts.outbound import OutboundMessage

PAGE = "<!doctype html><html><body><h1>Баги недели</h1></body></html>"
ANSWER = f'<vanessa_file name="bugs.html">\n{PAGE}\n</vanessa_file>\nГлавное: 3 бага.'


def _runner(client, completer, broker, *, file_max_bytes: int = 262_144):
    return HermesRunner(
        client,
        make_composer(completer),
        broker,
        outbound_stream="vanessa:outbound",
        instructions="work only",
        poll_seconds=0.0,
        max_wait_seconds=60.0,
        file_max_bytes=file_max_bytes,
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
    assert message.text == "Держи отчёт, три бага."
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
    assert message.text == "Отчёт не собрался."
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
    assert "Главное: 3 бага." in message.text


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
