"""Exercise the deploy bridge's range logic without GitLab."""

import importlib
from pathlib import Path

import pytest

BRIDGE_DIR = Path(__file__).resolve().parents[2] / "deploy" / "vanessa-bridge"


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.syspath_prepend(str(BRIDGE_DIR))
    return importlib.import_module("bridge")


class GitLab:
    """Stand-in for ``GitLabView._api``: one route function, recorded calls."""

    def __init__(self, route):
        self._route = route
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        return self._route(path)


def fixed(payload):
    """A route that answers every path the same way."""

    def route(path: str):
        return payload

    return route


def pipeline_id(path: str) -> int:
    return int(path.split("/pipelines/")[1].split("/", maxsplit=1)[0])


def view(bridge, api: GitLab):
    gitlab = bridge.GitLabView(
        "glab", 29, "production", "deploy:production", "deploy:production:start"
    )
    gitlab._api = api
    return gitlab


def pipeline(pid: int, sha: str) -> dict:
    return {"id": pid, "sha": sha, "status": "success"}


def job(sha: str) -> dict:
    return {"name": "deploy:production", "status": "success", "pipeline": {"sha": sha}}


def test_the_previous_deploy_is_found_past_the_first_page(bridge):
    ids = list(range(100, 80, -1))

    def route(path: str):
        if "/pipelines?" in path:
            page = ids if "page=1" in path else [80]
            return [pipeline(pid, f"s{pid}") for pid in page]
        if "/jobs" in path:
            pid = pipeline_id(path)
            return [job(f"s{pid}")] if pid in {100, 80} else []
        raise AssertionError(path)

    api = GitLab(route)
    found = view(bridge, api)._scan()

    assert [deploy["pipeline"]["sha"] for deploy, _ in found] == ["s100", "s80"]
    assert any("page=2" in path for path in api.calls)


def test_the_range_runs_from_the_previous_deploy_to_the_new_one(bridge):
    sha = {100: "new", 99: "previous"}

    def route(path: str):
        if "/pipelines?" in path:
            return [pipeline(pid, sha[pid]) for pid in sha]
        if "/jobs" in path:
            return [job(sha[pipeline_id(path)])]
        return {"commits": [{"short_id": "a1", "title": "only change"}]}

    api = GitLab(route)
    payload = view(bridge, api)._fetch()["deploy"]

    assert any("from=previous" in path for path in api.calls)
    assert any("to=new" in path for path in api.calls)
    assert [commit["short_id"] for commit in payload["commits"]] == ["a1"]
    assert payload["commit_total"] == 1


def test_commits_are_newest_first_and_a_long_release_keeps_the_newest(bridge):
    commits = [
        {"short_id": f"c{index}", "title": f"commit {index}"} for index in range(50)
    ]
    gitlab = view(bridge, GitLab(fixed({"commits": commits})))

    got, total = gitlab._commits(
        {"pipeline": {"sha": "old"}}, {"pipeline": {"sha": "new"}}
    )

    assert total == 50
    assert len(got) == 40
    assert got[0]["short_id"] == "c49"
    assert got[-1]["short_id"] == "c10"


def test_the_same_commit_deployed_twice_has_no_range(bridge):
    def route(path: str):
        pytest.fail(f"unexpected GitLab call: {path}")

    api = GitLab(route)

    got, total = view(bridge, api)._commits(
        {"pipeline": {"sha": "abc"}}, {"pipeline": {"sha": "abc"}}
    )

    assert (got, total) == ([], 0)


def test_without_a_previous_deploy_the_branch_tip_comes_newest_first(bridge):
    tip = [{"short_id": "n2", "title": "newest"}, {"short_id": "n1", "title": "older"}]

    got, total = view(bridge, GitLab(fixed(tip)))._commits(
        None, {"pipeline": {"sha": "abc"}}
    )

    assert [commit["short_id"] for commit in got] == ["n2", "n1"]
    assert total == 2
