"""Read-only GitLab bridge for Vanessa's production-deploy announcements.

Why it exists: the internal GitLab refuses the Vanessa server's IP (nginx
403), while the owner's PC has an authenticated ``glab``. This process runs
on the PC, answers one question over plain HTTP and is reached through the
same reverse SSH tunnel as Hermes:

    GET /health          -> {"ok": true}
    GET /deploy/latest   -> {"deploy": {...} | null}   (Bearer token)

``deploy`` is the newest successful ``deploy:production`` job with the
commits between it and the previous production deploy. All business logic
(announcing, dedupe, wording) lives on the server; this file only reads
GitLab. No writes, no tokens on the command line: the bearer token comes
from a file.
"""

from __future__ import annotations

import argparse
import contextlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from subprocess import SubprocessError, run
from urllib.parse import urlsplit

MAX_COMMITS = 40
PIPELINES_SCANNED = 8
DEPLOYS_NEEDED = 2
#: One glab call may not hang the whole bridge.
GLAB_TIMEOUT_SECONDS = 25


def _glab_env() -> dict[str, str]:
    """No update checks, no prompts: both can hang a hidden background process."""
    return {
        **os.environ,
        "GLAB_CHECK_UPDATE": "false",
        "GLAB_NO_PROMPT": "true",
        "GIT_TERMINAL_PROMPT": "0",
    }


class GitLabError(RuntimeError):
    """A glab call failed; the message is safe to return to the caller."""


class GitLabView:
    """Newest successful deploy job and its changelog, cached for a minute.

    A refresh never blocks a reader: if the previous answer is still in hand
    it is returned while one thread refreshes. A hung ``glab`` therefore costs
    freshness, not the endpoint.
    """

    def __init__(self, glab: str, project: int, branch: str, job: str,
                 start_job: str, *, cache_seconds: float = 60.0) -> None:
        self._glab = glab
        self._project = project
        self._branch = branch
        self._job = job
        self._start_job = start_job
        self._cache_seconds = cache_seconds
        self._cached: dict | None = None
        self._cached_at = 0.0
        self._refreshing = threading.Lock()

    def latest(self) -> dict:
        if self._cached is not None and self._fresh():
            return self._cached
        if self._refreshing.acquire(blocking=False):
            try:
                self._refresh()
            finally:
                self._refreshing.release()
        return self._cached if self._cached is not None else {"deploy": None}

    def _refresh(self) -> None:
        try:
            self._cached = self._fetch()
            self._cached_at = time.monotonic()
        except GitLabError as exc:
            if self._cached is None:
                raise
            # Serve the last answer; the next request retries the refresh.
            print(f"gitlab_refresh_failed {exc} (serving the cached answer)", flush=True)

    def _fresh(self) -> bool:
        return time.monotonic() - self._cached_at < self._cache_seconds

    def _api(self, path: str):
        try:
            done = run(
                [self._glab, "api", f"/{path.lstrip('/')}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GLAB_TIMEOUT_SECONDS,
                check=False,
                env=_glab_env(),
            )
        except (OSError, SubprocessError) as exc:
            raise GitLabError(f"glab did not run: {type(exc).__name__}") from exc
        if done.returncode != 0:
            raise GitLabError(f"glab exit {done.returncode}: {done.stderr.strip()[:160]}")
        try:
            return json.loads(done.stdout or "")
        except (TypeError, ValueError) as exc:
            raise GitLabError("glab returned no JSON") from exc

    def _fetch(self) -> dict:
        found = self._scan()
        if not found:
            return {"deploy": None}
        deploy, started = found[0]
        previous = found[1][0] if len(found) > 1 else None
        commits, total = self._commits(previous, deploy)
        return {"deploy": _payload(deploy, started, commits, total)}

    def _scan(self) -> list[tuple[dict, dict | None]]:
        pipelines = self._api(
            f"projects/{self._project}/pipelines"
            f"?ref={self._branch}&per_page={PIPELINES_SCANNED}"
        )
        found: list[tuple[dict, dict | None]] = []
        for pipeline in _as_list(pipelines):
            pair = self._pipeline_pair(pipeline)
            if pair is None:
                continue
            found.append(pair)
            if len(found) >= DEPLOYS_NEEDED:
                break
        return found

    def _pipeline_pair(self, pipeline: dict) -> tuple[dict, dict | None] | None:
        if pipeline.get("status") != "success":
            return None
        jobs = _as_list(
            self._api(f"projects/{self._project}/pipelines/{pipeline['id']}/jobs")
        )
        deploy = _job(jobs, self._job)
        if deploy is None:
            return None
        return deploy, _job(jobs, self._start_job)

    def _commits(self, previous: dict | None, deploy: dict) -> tuple[list[dict], int]:
        head = (deploy.get("pipeline") or {}).get("sha") or ""
        base = (previous or {}).get("pipeline", {}).get("sha") or ""
        commits = _as_list(self._raw_commits(base, head))
        return [_commit(commit) for commit in commits[:MAX_COMMITS]], len(commits)

    def _raw_commits(self, base: str, head: str):
        if base and head and base != head:
            data = self._api(
                f"projects/{self._project}/repository/compare?from={base}&to={head}"
            )
            return data.get("commits") if isinstance(data, dict) else None
        return self._api(
            f"projects/{self._project}/repository/commits"
            f"?ref_name={head or self._branch}&per_page={MAX_COMMITS}"
        )


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _job(jobs: list[dict], name: str) -> dict | None:
    for job in jobs:
        if job.get("name") == name and job.get("status") == "success":
            return job
    return None


def _person(user: dict | None) -> dict | None:
    if not user:
        return None
    return {"username": user.get("username") or "", "name": user.get("name") or ""}


def _commit(commit: dict) -> dict:
    return {
        "short_id": commit.get("short_id") or "",
        "title": (commit.get("title") or "").strip(),
        "author_name": commit.get("author_name") or "",
    }


def _payload(deploy: dict, started: dict | None, commits: list[dict], total: int) -> dict:
    pipeline = deploy.get("pipeline") or {}
    return {
        "job_id": deploy.get("id"),
        "finished_at": deploy.get("finished_at"),
        "web_url": deploy.get("web_url") or "",
        "pipeline": {
            "id": pipeline.get("id") or 0,
            "sha": pipeline.get("sha") or "",
            "web_url": pipeline.get("web_url") or "",
        },
        "started_by": _person((started or {}).get("user")),
        "runner": _person(deploy.get("user")),
        "commits": commits,
        "commit_total": max(total, len(commits)),
    }


class BridgeServer(ThreadingHTTPServer):
    """HTTP server carrying the GitLab view, the bearer token and the log path."""

    view: GitLabView
    token: str
    log_file: str


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "VanessaDeployBridge/1.0"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path.rstrip("/") or "/"
        route = {"/health": self._health, "/deploy/latest": self._latest}.get(path)
        if route is None:
            self._json(404, {"error": "not_found"})
            return
        route()

    def _health(self) -> None:
        self._json(200, {"ok": True})

    def _latest(self) -> None:
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            data = self.server.view.latest()
        except GitLabError as exc:
            self.log_line(f"gitlab_error {exc}")
            self._json(502, {"error": "gitlab_unavailable"})
            return
        except Exception as exc:  # noqa: BLE001 - keep the HTTP surface alive
            self.log_line(f"bridge_error {type(exc).__name__}")
            self._json(500, {"error": "bridge_failed"})
            return
        self._json(200, data)

    def _authorized(self) -> bool:
        expected = self.server.token
        header = self.headers.get("Authorization", "")
        given = header[7:] if header.lower().startswith("bearer ") else ""
        return bool(expected) and hmac.compare_digest(given, expected)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_line(self, text: str) -> None:
        log = self.server.log_file
        if not log:
            return
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n"
        try:
            with Path(log).open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


def _token(args) -> str:
    if args.token:
        return args.token
    if not args.token_file:
        raise SystemExit("no token: pass --token-file")
    try:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(f"cannot read token file: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glab", default="glab")
    parser.add_argument("--project", type=int, default=29)
    parser.add_argument("--branch", default="production")
    parser.add_argument("--job", default="deploy:production")
    parser.add_argument("--start-job", default="deploy:production:start")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8643)
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--log-file", default="")
    parser.add_argument("--check", action="store_true", help="fetch once and print a summary")
    return parser


def _run_check(view: GitLabView) -> int:
    deploy = view.latest().get("deploy")
    if not deploy:
        print("no successful deploy found")
        return 0
    started = (deploy.get("started_by") or {}).get("username")
    print(
        f"job {deploy['job_id']} finished {deploy['finished_at']} "
        f"by {started} commits {deploy['commit_total']}"
    )
    for commit in deploy["commits"][:5]:
        print(f"- {commit['title']}")
    return 0


def _serve(view: GitLabView, token: str, args) -> int:
    server = BridgeServer((args.host, args.port), BridgeHandler)
    server.view = view
    server.token = token
    server.log_file = args.log_file
    print(f"deploy bridge on http://{args.host}:{args.port}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    view = GitLabView(args.glab, args.project, args.branch, args.job, args.start_job)
    if args.check:
        return _run_check(view)
    return _serve(view, _token(args), args)


if __name__ == "__main__":
    sys.exit(main())
