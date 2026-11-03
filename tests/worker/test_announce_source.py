import httpx

from services.worker.announce.source import JsonSource
from services.worker.deploys.adapter import deploy_announcement

PAYLOAD = {
    "deploy": {
        "job_id": 839023,
        "finished_at": "2026-11-03T08:54:04.604Z",
        "web_url": "https://git.example/-/jobs/839023",
        "pipeline": {"id": 70795, "sha": "c" * 40, "web_url": "https://git.example/-/p/70795"},
        "started_by": {"username": "v.titov", "name": "Viacheslav Titov"},
        "commits": [{"short_id": "c1", "title": "feat: экран агента", "author_name": "dev"}],
        "commit_total": 44,
    }
}


def _source(handler) -> JsonSource:
    return JsonSource(
        "http://127.0.0.1:8643/",
        "secret",
        path="/deploy/latest",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_payload_is_fetched_with_the_token_and_mapped() -> None:
    seen: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["path"] = request.url.path
        return httpx.Response(200, json=PAYLOAD)

    announcement = deploy_announcement(await _source(handler).payload())
    assert announcement is not None
    assert announcement.key == 839023
    assert announcement.actor_label == "Viacheslav Titov (@v.titov)"
    assert announcement.item_total == 44
    assert announcement.url == "https://git.example/-/p/70795"
    assert seen == {"auth": "Bearer secret", "path": "/deploy/latest"}


async def test_no_event_yet_is_an_empty_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"deploy": None})

    assert await _source(handler).payload() == {"deploy": None}
    assert deploy_announcement({"deploy": None}) is None


async def test_http_error_and_garbage_are_empty() -> None:
    async def error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "gitlab_unavailable"})

    async def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    assert await _source(error).payload() == {}
    assert await _source(garbage).payload() == {}


async def test_unreachable_source_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    assert await _source(handler).payload() == {}


async def test_broken_event_payload_is_none() -> None:
    assert deploy_announcement({"deploy": {"job_id": "not-a-number"}}) is None
