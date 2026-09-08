import pytest
from pytest_httpx import HTTPXMock

from barney.tools.github import GitHub, GitHubError, PatTokenProvider


class Tok:
    def token(self):
        return "abc"


def test_headers_and_create_pull(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/o/r/pulls",
        json={"html_url": "u", "number": 5},
        match_json={"title": "t", "body": "b", "head": "h", "base": "main", "draft": True},
    )
    gh = GitHub("o/r", Tok())
    pr = gh.create_pull("t", "b", "h", "main", draft=True)
    assert pr["number"] == 5
    req = httpx_mock.get_requests()[0]
    assert req.headers["Authorization"] == "Bearer abc"
    assert req.headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_error_surface(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="GET", url="https://api.github.com/repos/o/r/issues/1", status_code=404, text="nope")
    with pytest.raises(GitHubError, match="404"):
        GitHub("o/r", Tok()).issue(1)


def test_pat_provider(monkeypatch):
    monkeypatch.delenv("BARNEY_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        PatTokenProvider().token()
    monkeypatch.setenv("BARNEY_GITHUB_TOKEN", "x")
    assert PatTokenProvider().token() == "x"
