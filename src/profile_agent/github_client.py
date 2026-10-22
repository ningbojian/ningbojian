"""GitHub REST API 客户端（requests，支持分页与重试）。"""

from __future__ import annotations

import base64
import re
import time
from typing import Callable

import requests

API = "https://api.github.com"
_HEADERS_JSON = {"Accept": "application/vnd.github+json", "User-Agent": "profile-agent"}
_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubError(Exception):
    """GitHub API 错误（消息为中文）。"""


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        session: requests.Session | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
    ) -> None:
        self._session = session or requests.Session()
        self._headers = dict(_HEADERS_JSON)
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._sleep = sleep
        self._max_retries = max_retries

    def _request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        *,
        allow_404: bool = False,
        ok_status: tuple[int, ...] = (200,),
    ) -> tuple[dict | list | None, dict]:
        """通用请求（GET/POST/PATCH…），复用同一套重试与中文错误语义。"""
        for attempt in range(self._max_retries + 1):
            resp = self._session.request(
                method, url, headers=self._headers, json=payload, timeout=30
            )
            if resp.status_code in ok_status:
                return resp.json(), resp.headers
            if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = resp.headers.get("X-RateLimit-Reset", "未知")
                raise GitHubError(
                    f"GitHub API 限流（速率已达上限），重置时间戳：{reset}，请稍后再试"
                )
            if resp.status_code == 404:
                if allow_404:
                    return None, resp.headers
                raise GitHubError("GitHub API 返回 404：用户不存在或仓库不可见")
            if resp.status_code >= 500 and attempt < self._max_retries:
                self._sleep(0.5 * (attempt + 1))
                continue
            raise GitHubError(f"GitHub API 请求失败：HTTP {resp.status_code} {resp.text[:200]}")
        raise GitHubError("GitHub API 请求失败：重试次数已用尽")

    def _get(self, url: str, *, allow_404: bool = False) -> tuple[dict | list | None, dict]:
        for attempt in range(self._max_retries + 1):
            resp = self._session.get(url, headers=self._headers, timeout=30)
            if resp.status_code == 200:
                return resp.json(), resp.headers
            if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = resp.headers.get("X-RateLimit-Reset", "未知")
                raise GitHubError(
                    f"GitHub API 限流（速率已达上限），重置时间戳：{reset}，请稍后再试"
                )
            if resp.status_code == 404:
                if allow_404:
                    return None, resp.headers
                raise GitHubError("GitHub API 返回 404：用户不存在或仓库不可见")
            if resp.status_code >= 500 and attempt < self._max_retries:
                self._sleep(0.5 * (attempt + 1))
                continue
            raise GitHubError(f"GitHub API 请求失败：HTTP {resp.status_code} {resp.text[:200]}")
        raise GitHubError("GitHub API 请求失败：重试次数已用尽")

    def _post(
        self,
        url: str,
        payload: dict,
        *,
        allow_404: bool = False,
        ok_status: tuple[int, ...] = (201,),
    ) -> tuple[dict | list | None, dict]:
        return self._request("POST", url, payload, allow_404=allow_404, ok_status=ok_status)

    def _patch(
        self,
        url: str,
        payload: dict,
        *,
        allow_404: bool = False,
        ok_status: tuple[int, ...] = (200,),
    ) -> tuple[dict | list | None, dict]:
        return self._request("PATCH", url, payload, allow_404=allow_404, ok_status=ok_status)

    def get_user(self, username: str) -> dict:
        data, _ = self._get(f"{API}/users/{username}")
        assert isinstance(data, dict)
        return data

    def list_repos(self, username: str) -> list[dict]:
        """列出用户全部公开仓库（owner 归属，按更新时间倒序，自动翻页）。"""
        url: str | None = f"{API}/users/{username}/repos?type=owner&sort=updated&per_page=100"
        repos: list[dict] = []
        while url:
            data, headers = self._get(url)
            assert isinstance(data, list)
            repos.extend(data)
            match = _NEXT_RE.search(headers.get("Link", ""))
            url = match.group(1) if match else None
        return repos

    def get_repo_readme(self, full_name: str) -> str:
        """读取仓库 README 文本；无 README 或读取失败时返回空串（不报错）。"""
        try:
            data, _ = self._get(f"{API}/repos/{full_name}/readme", allow_404=True)
        except GitHubError:
            return ""
        if not isinstance(data, dict):
            return ""
        content = str(data.get("content") or "")
        if data.get("encoding") != "base64" or not content:
            return ""
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except (ValueError, OSError):
            return ""
