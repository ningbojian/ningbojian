"""github_client.py 测试：用假 session，无网络。"""

import base64

import pytest

from profile_agent.github_client import GitHubClient, GitHubError


class FakeResponse:
    def __init__(self, status=200, json_data=None, headers=None, text=""):
        self.status_code = status
        self._json = json_data
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    """按调用顺序返回预设响应，并记录请求。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append({"url": url, "headers": headers or {}})
        return self._responses.pop(0)


def test_get_user_returns_json():
    session = FakeSession([FakeResponse(json_data={"login": "alice"})])
    client = GitHubClient(token="tok", session=session)
    assert client.get_user("alice") == {"login": "alice"}
    assert session.requests[0]["url"] == "https://api.github.com/users/alice"
    assert session.requests[0]["headers"]["Authorization"] == "Bearer tok"


def test_list_repos_paginates_via_link_header():
    page1 = FakeResponse(
        json_data=[{"name": "a"}],
        headers={"Link": '<https://api.github.com/users/alice/repos?page=2>; rel="next"'},
    )
    page2 = FakeResponse(json_data=[{"name": "b"}])
    session = FakeSession([page1, page2])
    client = GitHubClient(token=None, session=session)
    repos = client.list_repos("alice")
    assert [r["name"] for r in repos] == ["a", "b"]
    assert "page=2" in session.requests[1]["url"]
    # 无 token 时不带 Authorization 头
    assert "Authorization" not in session.requests[0]["headers"]


def test_rate_limit_raises_chinese_error():
    session = FakeSession(
        [FakeResponse(status=403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1792000000"}, text="rate limited")]
    )
    client = GitHubClient(token=None, session=session)
    with pytest.raises(GitHubError, match="限流"):
        client.get_user("alice")


def test_server_error_retries_then_succeeds():
    session = FakeSession(
        [FakeResponse(status=500), FakeResponse(status=500), FakeResponse(json_data={"login": "alice"})]
    )
    client = GitHubClient(token=None, session=session)
    assert client.get_user("alice")["login"] == "alice"
    assert len(session.requests) == 3


def test_not_found_raises_chinese_error():
    session = FakeSession([FakeResponse(status=404, text="nope")])
    client = GitHubClient(token=None, session=session)
    with pytest.raises(GitHubError, match="不存在"):
        client.get_user("ghost-user-xyz")


def test_get_repo_readme_decodes_base64_content():
    text = "# cool-tool\n一个很酷的工具，支持 A/B。"
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    session = FakeSession([FakeResponse(json_data={"content": b64, "encoding": "base64"})])
    client = GitHubClient(token=None, session=session)
    assert client.get_repo_readme("alice/cool-tool") == text
    assert session.requests[0]["url"] == "https://api.github.com/repos/alice/cool-tool/readme"


def test_get_repo_readme_missing_returns_empty_string():
    session = FakeSession([FakeResponse(status=404, text="not found")])
    client = GitHubClient(token=None, session=session)
    assert client.get_repo_readme("alice/no-readme") == ""
