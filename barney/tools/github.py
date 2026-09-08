"""GitHub REST (and later GraphQL) client with a pluggable token provider."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

API = "https://api.github.com"


class TokenProvider(Protocol):
    def token(self) -> str: ...


@dataclass
class PatTokenProvider:
    """Fine-grained PAT from the environment (Phases 1 and 2)."""

    env_var: str = "BARNEY_GITHUB_TOKEN"

    def token(self) -> str:
        t = os.environ.get(self.env_var) or os.environ.get("GITHUB_TOKEN")
        if not t:
            raise RuntimeError(f"no GitHub token: set {self.env_var}")
        return t


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str, tokens: TokenProvider, client: httpx.Client | None = None) -> None:
        if "/" not in repo:
            raise ValueError("repo must be owner/name")
        self.repo = repo
        self.tokens = tokens
        self._client = client or httpx.Client(timeout=30)

    # -- plumbing -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tokens.token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "barney-bedrock",
        }

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        url = path if path.startswith("http") else f"{API}/repos/{self.repo}{path}"
        r = self._client.request(method, url, headers=self._headers(), **kw)
        if r.status_code >= 400:
            raise GitHubError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo}.git"

    # -- repo -----------------------------------------------------------------

    def default_branch(self) -> str:
        return self._req("GET", "")["default_branch"]

    # -- issues ---------------------------------------------------------------

    def issue(self, number: int) -> dict[str, Any]:
        return self._req("GET", f"/issues/{number}")

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/issues/{number}/comments", params={"per_page": 100})

    def comment(self, number: int, body: str) -> dict[str, Any]:
        return self._req("POST", f"/issues/{number}/comments", json={"body": body})

    # -- pull requests --------------------------------------------------------

    def pull(self, number: int) -> dict[str, Any]:
        return self._req("GET", f"/pulls/{number}")

    def create_pull(self, title: str, body: str, head: str, base: str, draft: bool = False) -> dict[str, Any]:
        return self._req(
            "POST", "/pulls", json={"title": title, "body": body, "head": head, "base": base, "draft": draft}
        )

    def pulls_for_branch(self, head: str) -> list[dict[str, Any]]:
        owner = self.repo.split("/")[0]
        return self._req("GET", "/pulls", params={"head": f"{owner}:{head}", "state": "open"})

    def pull_files(self, number: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/pulls/{number}/files", params={"per_page": 100})

    def pull_diff(self, number: int) -> str:
        r = self._client.get(
            f"{API}/repos/{self.repo}/pulls/{number}",
            headers={**self._headers(), "Accept": "application/vnd.github.diff"},
        )
        if r.status_code >= 400:
            raise GitHubError(f"diff {number} -> {r.status_code}")
        return r.text

    def review_comments(self, number: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/pulls/{number}/comments", params={"per_page": 100})

    def create_review(
        self, number: int, body: str, event: str, comments: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """event: APPROVE | REQUEST_CHANGES | COMMENT. comments: [{path, line, body}]"""
        payload: dict[str, Any] = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        return self._req("POST", f"/pulls/{number}/reviews", json=payload)

    # -- graphql (review threads; Phase 3) ------------------------------------

    def graphql(self, query: str, variables: dict[str, Any]) -> Any:
        r = self._client.post(
            "https://api.github.com/graphql", headers=self._headers(), json={"query": query, "variables": variables}
        )
        if r.status_code >= 400:
            raise GitHubError(f"graphql -> {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("errors"):
            raise GitHubError(str(data["errors"])[:300])
        return data["data"]
