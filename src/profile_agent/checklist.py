"""清单 issue/通知通道（设计 §4-2、§5.5 文案草案、§5.7、§12-R8）。

- 本仓（username/username）唯一单份「🔔 待合并清单」issue：@你 + assignee 制造
  主动通知（自 PAT 开的 PR 不通知作者本人，mention/assign 不受自操作抑制）；
- 状态变化只原地改 body、永不发评论（避免通知轰炸，IW04）；
- 全部结清自动关闭（关闭通知 = 可以收工，IW03）；无 open PR 且无既有清单不开新 issue（IW05）；
- 异常向上抛，由 cli 隔离（创建失败任务不失败，IW26）。
"""

from __future__ import annotations

from .github_client import API, GitHubClient
from .repo_readmes_pr import PR_BRANCH

CHECKLIST_TITLE = "🔔 README 更新待合并清单"


def _find_checklist_issue(client: GitHubClient, owner_repo: str) -> dict | None:
    """找本仓唯一的清单 issue（open 态、标题前缀匹配）；无则 None。"""
    data, _ = client._get(f"{API}/repos/{owner_repo}/issues?state=open&per_page=100")
    for it in data if isinstance(data, list) else []:
        if str(it.get("title") or "").startswith(CHECKLIST_TITLE):
            return it
    return None


def build_checklist_body(
    open_prs: list[dict],
    *,
    username: str,
    updated_at: str,
    branch: str = PR_BRANCH,
    tail: str = "",
) -> str:
    """清单 body：时间戳标题 + @你 + 逐条 PR（含预览链接）+ 三结局文案（§5.5 草案）。

    open_prs 元素：{"full_name", "html_url", "branch"?}。
    """
    lines = [
        f"## {CHECKLIST_TITLE}（更新于 {updated_at}，北京时间）",
        f"@{username}",
    ]
    for pr in open_prs:
        full = str(pr.get("full_name") or "")
        short = full.split("/", 1)[-1]
        b = str(pr.get("branch") or branch)
        preview = f"https://github.com/{full}/blob/{b}/README.md"
        lines.append(f"- [ ] {short}：{pr.get('html_url', '')}（[新版 README 预览]({preview})）")
    lines += [
        "",
        "三种处理方式的效果：",
        "- **合并** → 新 README 落进仓库，主页本轮已经吸收，无需再做任何事；",
        "- **关闭** → 拒绝这批文案：主页将不再包含它（本轮或下一轮生效），同批内容不会自动重开，"
        "下次新提交会把新批次连同旧内容一起带回来；",
        "- **先放着** → 完全没问题：PR 留着以后合，主页照样是新鲜的"
        "（期间有新批次时 PR 会被刷新，合并前请重读 diff）。",
    ]
    if tail:
        lines += ["", tail]
    return "\n".join(lines) + "\n"


def update_checklist(
    client: GitHubClient,
    owner_repo: str,
    open_prs: list[dict],
    *,
    username: str,
    updated_at: str,
    branch: str = PR_BRANCH,
    tail: str = "",
) -> dict | None:
    """创建/刷新唯一清单 issue；全部结清时自动关闭；无 open PR 且无既有 issue → 不开。

    tail 附加在 body 末尾（等待首行、⏰ 终态行等，§4-3/§4-5）。
    返回 {"number", "html_url"} 或 None。异常向上抛（cli 隔离，IW26）。
    """
    repo = f"{API}/repos/{owner_repo}"
    existing = _find_checklist_issue(client, owner_repo)
    if not open_prs:
        if existing:
            client._patch(f"{repo}/issues/{existing['number']}", {"state": "closed"})
        return None
    body = build_checklist_body(
        open_prs, username=username, updated_at=updated_at, branch=branch, tail=tail
    )
    if existing:
        client._patch(
            f"{repo}/issues/{existing['number']}",
            {"body": body, "assignees": [username]},
        )
        return {"number": existing["number"], "html_url": existing.get("html_url", "")}
    data, _ = client._post(
        f"{repo}/issues",
        {
            "title": f"{CHECKLIST_TITLE}（待合并 PR）",
            "body": body,
            "assignees": [username],
        },
    )
    assert isinstance(data, dict)
    return {"number": data["number"], "html_url": data.get("html_url", "")}


def append_final_state(
    client: GitHubClient,
    owner_repo: str,
    issue: dict | None,
    *,
    project_pr_url: str | None = None,
) -> None:
    """收尾：清单仍开着时原地追加终态行（Overview 进 main + 项目介绍 PR 链接，§4-5）。

    issue 为 None（已结清/从未创建）时直接跳过（IW07 附）。
    """
    if not issue:
        return
    lines = [""]
    if project_pr_url:
        lines.append(f"本轮项目介绍 PR：{project_pr_url}")
    lines.append("本轮 Overview 已进入 main")
    body = str(issue.get("body") or "") + "\n" + "\n".join(lines) + "\n"
    client._patch(f"{API}/repos/{owner_repo}/issues/{issue['number']}", {"body": body})
