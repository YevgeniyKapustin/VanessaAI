"""A Hermes job writes its trace under the turn request_id."""

from __future__ import annotations

import asyncio

from services.worker.hermes.trace import turn_request_id
from tests.trace_helpers import ReadTrace
from tests.worker.hermes_fakes import (
    CHAT_ID,
    FakeBroker,
    FakeClient,
    FakeCompleter,
    make_ask,
    make_runner,
)


async def test_job_records_query_answer_and_parts(
    trace_records: ReadTrace,
) -> None:
    completer = FakeCompleter("[answer]\nвсё готово")
    runner = make_runner(FakeClient(output="raw data"), completer, FakeBroker())
    await asyncio.create_task(runner.run(make_ask()))
    records = trace_records()
    stages = [record["stage"] for record in records]
    assert stages[0] == "hermes_query"
    assert "hermes_answer" in stages
    assert stages[-1] == "hermes_sent"
    assert {record["request_id"] for record in records} == {"-100123:42"}
    assert {record["chat_id"] for record in records} == {CHAT_ID}
    by_stage = {record["stage"]: record for record in records}
    assert by_stage["hermes_query"]["instructions"] == "work only"
    assert by_stage["hermes_answer"]["answer"] == "raw data"
    assert by_stage["hermes_sent"]["parts"]


def test_request_id_falls_back_to_the_job_key() -> None:
    ask = make_ask(telegram_message_id=None)
    assert turn_request_id(ask) == ask.idempotency_key
