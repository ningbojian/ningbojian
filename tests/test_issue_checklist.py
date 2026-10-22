"""清单 issue/通知通道测试（测试计划 IW01-IW08、IW26，全离线）。

设计 §4-2、§5.5 文案草案、§5.7、§12-R8：唯一单份清单 issue（可原地改写、
全部结清自动关闭、永不发评论）、三结局文案、@你 + assignee 主动通知。
"""

import pytest
from fake_github import FakeHttp, FakeResponse

from profile_agent.checklist import (
    CHECKLIST_TITLE,
    append_final_state,
    build_checklist_body,
    update_checklist,
)
from profile_agent.github_client import API, GitHubClient, GitHubError

SELF = "alice/alice"
PR7 = {
    "full_name": "ningbojian/shiyuan",
    "html_url": "https://github.com/ningbojian/shiyuan/pull/7",
    "branch": "readme-auto/update",
}
PR43 = {
    "full_name": "ningbojian/profile-readme-agent",
    "html_url": "https://github.com/ningbojian/profile-readme-agent/pull/43",
    "branch": "readme-auto/update",
}


def _client(http: FakeHttp) -> GitHubClient:
    return GitHubClient("g-tok", session=http)


def _search_empty(http: FakeHttp):
    http.add("GET", f"{API}/repos/alice/alice/issues?state=open&per_page=100",
             FakeResponse(json_data=[]))


def _search_existing(http: FakeHttp, number=5, body="旧清单正文"):
    http.add("GET", f"{API}/repos/alice/alice/issues?state=open&per_page=100",
             FakeResponse(json_data=[{
                "number": number,
                "title": f"{CHECKLIST_TITLE}（待合并 PR）",
                "body": body,
                "html_url": f"https://x/issues/{number}",
            }]))


def test_iw01_create_checklist_issue_structure():
    """IW01：首次产出后创建清单 issue——assignee、时间戳标题、逐条链接+预览、三结局、@你。"""
    http = FakeHttp()
    _search_empty(http)
    http.add("POST", f"{API}/repos/alice/alice/issues",
             FakeResponse(status=201, json_data={"number": 5, "html_url": "https://x/issues/5"}))
    issue = update_checklist(_client(http), SELF, [PR7], username="alice", updated_at="2026-10-22 18:30")
    assert issue["number"] == 5
    assert issue["html_url"] == "https://x/issues/5"
    assert "/pull/7" in issue["body"]  # 回带刚写入的正文（收尾 append 的底稿，OR13）
    posts = [r for r in http.writes() if r["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["json"]["assignees"] == ["alice"]  # ① 主动通知通道
    body = posts[0]["json"]["body"]
    assert "## 🔔 README 更新待合并清单（更新于 2026-10-22 18:30，北京时间）" in body  # ②
    assert "https://github.com/ningbojian/shiyuan/pull/7" in body  # ③ 逐条链接
    assert "https://github.com/ningbojian/shiyuan/blob/readme-auto/update/README.md" in body  # 预览链接
    assert "合并" in body and "关闭" in body and "先放着" in body  # 三结局
    assert "@alice" in body  # ④ @你
    assert "刷新" in body and "重读 diff" in body  # ⑤ 先放着条含刷新语义


def test_iw02_iw04_refresh_in_place_only_patch_keeps_links_and_adds_timestamp():
    """IW02/IW04：有遗留 open PR 仍刷新清单——仅 PATCH 原地改 body、不发评论、链接保留、时间戳刷新。"""
    http = FakeHttp()
    _search_existing(http, body="旧正文 https://x/pull/7\n")
    http.add("PATCH", f"{API}/repos/alice/alice/issues/5", FakeResponse(json_data={"number": 5}))
    issue = update_checklist(_client(http), SELF, [PR7], username="alice", updated_at="2026-10-22 19:00")
    assert issue["number"] == 5
    writes = http.writes()
    assert all(r["method"] == "PATCH" for r in writes)  # ④ 无 POST 无评论
    assert not any("comments" in r["url"] for r in writes)
    body = writes[0]["json"]["body"]
    assert "https://github.com/ningbojian/shiyuan/pull/7" in body  # ② 链接仍在
    assert "2026-10-22 19:00" in body  # 时间戳已刷新
    assert "合并" in body and "关闭" in body and "先放着" in body  # 三结局完整


def test_iw03_all_settled_auto_closes_issue():
    """IW03：全部 PR 结清（open_prs 为空）→ PATCH state=closed、无评论、关闭在刷新逻辑内。"""
    http = FakeHttp()
    _search_existing(http)
    http.add("PATCH", f"{API}/repos/alice/alice/issues/5", FakeResponse(json_data={"number": 5}))
    assert update_checklist(_client(http), SELF, [], username="alice", updated_at="t") is None
    writes = http.writes()
    assert [r["method"] for r in writes] == ["PATCH"]
    assert writes[0]["json"]["state"] == "closed"
    assert not any("comments" in r["url"] for r in writes)


def test_iw05_no_open_prs_and_no_existing_issue_creates_nothing():
    """IW05：无任何 open PR 且无既有清单 → 不开 issue、零写请求。"""
    http = FakeHttp()
    _search_empty(http)
    assert update_checklist(_client(http), SELF, [], username="alice", updated_at="t") is None
    assert http.writes() == []


def test_iw08_reuse_single_issue_with_multiple_prs():
    """IW08：已存在清单 → 复用单份不新建；body 同时含多条 PR，assignee/@ 保持。"""
    http = FakeHttp()
    _search_existing(http)
    http.add("PATCH", f"{API}/repos/alice/alice/issues/5", FakeResponse(json_data={"number": 5}))
    update_checklist(_client(http), SELF, [PR7, PR43], username="alice", updated_at="t")
    assert not http.has("POST", "/issues")
    body = [r for r in http.writes() if r["method"] == "PATCH"][0]["json"]["body"]
    assert "/pull/7" in body and "/pull/43" in body
    assignees = [r for r in http.writes() if r["method"] == "PATCH"][0]["json"]["assignees"]
    assert assignees == ["alice"]


def test_iw06_final_state_appends_overview_line_and_project_pr():
    """IW06：收尾追加 Overview 终态行与项目介绍 PR 链接——仍原地 PATCH、无评论。"""
    http = FakeHttp()
    _search_existing(http, body="清单正文\n")
    http.add("PATCH", f"{API}/repos/alice/alice/issues/5", FakeResponse(json_data={"number": 5}))
    append_final_state(_client(http), SELF,
                       {"number": 5, "body": "清单正文\n"},
                       project_pr_url="https://github.com/ningbojian/ningbojian/pull/3")
    writes = http.writes()
    assert [r["method"] for r in writes] == ["PATCH"]
    body = writes[0]["json"]["body"]
    assert "本轮 Overview 已进入 main" in body
    assert "https://github.com/ningbojian/ningbojian/pull/3" in body


def test_iw07_final_state_without_project_pr_has_no_dangling_link():
    """IW07：无项目介绍 PR 时仅追加终态行，不产生悬空死链。"""
    http = FakeHttp()
    http.add("PATCH", f"{API}/repos/alice/alice/issues/5", FakeResponse(json_data={"number": 5}))
    append_final_state(_client(http), SELF, {"number": 5, "body": "清单正文\n"})
    body = [r for r in http.writes() if r["method"] == "PATCH"][0]["json"]["body"]
    assert "本轮 Overview 已进入 main" in body
    assert "项目介绍" not in body


def test_iw07_no_issue_noop():
    """IW07 附：无清单 issue（已结清/从未创建）时收尾直接跳过、零写请求。"""
    http = FakeHttp()
    append_final_state(_client(http), SELF, None)
    assert http.writes() == []


def test_iw26_create_failure_raises_for_caller_isolation():
    """IW26：issue 创建 403 → 模块向上抛 GitHubError（cli 负责隔离不失败）。"""
    http = FakeHttp()
    _search_empty(http)
    http.add("POST", f"{API}/repos/alice/alice/issues", FakeResponse(status=403, text="forbidden"))
    with pytest.raises(GitHubError):
        update_checklist(_client(http), SELF, [PR7], username="alice", updated_at="t")


def test_body_builder_respects_custom_branch_in_preview():
    """预览链接跟随自定义 pr_branch（GP15 同款语义）。"""
    body = build_checklist_body(
        [dict(PR7, branch="docs/readme-bot")], username="alice", updated_at="t"
    )
    assert "/blob/docs/readme-bot/README.md" in body
