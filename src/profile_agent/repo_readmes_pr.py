"""git-data 推送与 PR 流（设计 §5.5，测试计划 GP）。

- 全走 GitHub REST API，无本地 git；
- 每仓恒为一条 open PR：blob→tree→commit→ref（新建或 force-push）→PR 创建或刷新；
- 合并检测把基线推进到 PR head SHA 而非 merge commit（§12-R10）；
- 永不调用合并/关闭接口——合并永远由人执行（GP16）；
- 抑制只拦 cached（AI 输入哈希命中）：推送层不查 PR 状态（GP05）。
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Callable

from profile_agent.github_client import API, GitHubClient
from profile_agent.readme_block import END, START
from profile_agent.repo_readmes_ai import ProcessResult

PR_BRANCH = "readme-auto/update"
BASE_BRANCH = "main"


@dataclass
class PrResult:
    number: int
    html_url: str
    refreshed: bool


def build_pr_title(full_name: str) -> str:
    """标题带仓库短名——多仓多标签页靠它分辨（GP03）。"""
    short = full_name.split("/", 1)[-1]
    return f"docs({short}): README 自动更新（待审核）"


def build_pr_body(*, commits: list[dict], base_sha: str, head_sha: str) -> str:
    """PR body：三结局首行警示 + marker 说明 + base..head 短 SHA 列表（GP04）。

    marker 字样（profile-agent:readme）允许出现在 PR body——只禁止进 AI prompt。
    """
    base8, head8 = base_sha[:8], head_sha[:8]
    sha_lines = "\n".join(
        f"- `{c.get('sha', '')[:8]}` {str(c.get('message', '')).strip().splitlines()[0] if c.get('message') else ''}".rstrip()
        for c in commits
    )
    return (
        ">三结局：**合并本 PR = 采用这批文案**；**关闭本 PR = 拒绝这批文案**"
        "（同输入不会重发）；**先不处理** = 保持原样，合并前请重读 diff。\n"
        "\n"
        "改动仅限 README 中由两行 HTML 注释标记包裹的托管区"
        "（标记 `profile-agent:readme` 在渲染页不可见，请勿手删）。\n"
        f"覆盖提交范围：`{base8}..{head8}`\n"
        "\n"
        "涉及提交：\n"
        f"{sha_lines}\n"
        "\n"
        "如需放弃本批文案：关闭本 PR 即可——删掉区间 = 放弃，"
        "本批不会再来（除非出现新提交触发新哈希）。\n"
    )


def _owner(full_name: str) -> str:
    return full_name.split("/", 1)[0]


def get_open_pr(client: GitHubClient, full_name: str, branch: str) -> dict | None:
    """查同 head 同 base 的 open PR；无则 None（同仓恒单条，GP02）。"""
    data, _ = client._get(
        f"{API}/repos/{full_name}/pulls?state=open&head={_owner(full_name)}:{branch}&base={BASE_BRANCH}"
    )
    prs = data if isinstance(data, list) else []
    return prs[0] if prs else None


def find_latest_merged_pr(client: GitHubClient, full_name: str, branch: str) -> dict | None:
    """最近一条已合并的 bot PR；无合并记录返回 None。"""
    data, _ = client._get(
        f"{API}/repos/{full_name}/pulls?state=all&head={_owner(full_name)}:{branch}"
        f"&base={BASE_BRANCH}&sort=updated&direction=desc"
    )
    prs = data if isinstance(data, list) else []
    if prs and prs[0].get("merged"):
        return prs[0]
    return None


def advance_baseline_from_merged_pr(
    client: GitHubClient, entry: dict, full_name: str, branch: str
) -> bool:
    """合并检测：把该仓快照基线推进到 PR head SHA（不是 merge commit，§12-R10）。

    幂等：基线已等于 head SHA 时返回 False 不改写（GP13）；PR 仍 open 不动（GP14）。
    """
    pr = find_latest_merged_pr(client, full_name, branch)
    if not pr:
        return False
    head_sha = pr.get("head", {}).get("sha") or ""
    if not head_sha or entry.get("sha") == head_sha:
        return False
    entry["sha"] = head_sha
    return True


def push_readme(
    client: GitHubClient, full_name: str, content: str, head_sha: str, *, branch: str = PR_BRANCH
) -> str:
    """blob→tree→commit→ref 四连；返回新 commit SHA。

    ref 不存在则创建，存在则 force-push（每仓恒一条分支，GP02）。
    base_tree/parents 都落在目标仓默认分支 HEAD（head_sha）上。
    """
    repo = f"{API}/repos/{full_name}"
    blob, _ = client._post(f"{repo}/git/blobs", {"content": content, "encoding": "utf-8"})
    tree, _ = client._post(
        f"{repo}/git/trees",
        {
            "base_tree": head_sha,
            "tree": [{"path": "README.md", "mode": "100644", "type": "blob", "sha": blob["sha"]}],
        },
    )
    commit, _ = client._post(
        f"{repo}/git/commits",
        {
            "message": "docs: 更新 README 托管区（profile-agent 自动）",
            "tree": tree["sha"],
            "parents": [head_sha],
        },
    )
    ref, _ = client._get(f"{repo}/git/ref/heads/{branch}", allow_404=True)
    if ref is None:
        client._post(f"{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    else:
        client._patch(
            f"{repo}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": True}
        )
    return commit["sha"]


def open_or_refresh_pr(
    client: GitHubClient,
    *,
    full_name: str,
    content: str,
    head_sha: str,
    title: str,
    body: str,
    branch: str = PR_BRANCH,
) -> PrResult:
    """推送内容并开/刷同一条 PR；永不调用合并或关闭接口（GP16）。"""
    repo = f"{API}/repos/{full_name}"
    existing = get_open_pr(client, full_name, branch)
    push_readme(client, full_name, content, head_sha, branch=branch)
    if existing:
        number = existing["number"]
        client._patch(f"{repo}/pulls/{number}", {"body": body})
        return PrResult(number=number, html_url=existing.get("html_url", ""), refreshed=True)
    data, _ = client._post(
        f"{repo}/pulls", {"title": title, "body": body, "head": branch, "base": BASE_BRANCH}
    )
    assert isinstance(data, dict)
    return PrResult(number=data["number"], html_url=data.get("html_url", ""), refreshed=False)


def read_branch_block_hash(client: GitHubClient, full_name: str, branch: str) -> str:
    """读 bot 分支上 README 托管区内容哈希（GP10 漂移检测信号）。

    分支无 README 或 marker 不平衡时返回空串（调用方视为「无法比对」）。
    """
    data, _ = client._get(f"{API}/repos/{full_name}/contents/README.md?ref={branch}")
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return ""
    try:
        content = base64.b64decode(str(data.get("content") or "")).decode("utf-8", errors="replace")
    except (ValueError, OSError):
        return ""
    i, j = content.find(START), content.find(END)
    if i < 0 or j < 0 or j < i:
        return ""
    return content_block_hash(content)


def content_block_hash(content: str) -> str:
    """托管区内容哈希（与 read_branch_block_hash 同口径：marker 区块整体；无 marker 取全文）。"""
    i, j = content.find(START), content.find(END)
    block = content[i : j + len(END)] if i >= 0 and j >= i else content
    return "sha256:" + hashlib.sha256(block.encode("utf-8")).hexdigest()


def push_results(
    client: GitHubClient,
    results: list[ProcessResult],
    *,
    entries: dict[str, dict] | None = None,
    now: Callable[[], str] | None = None,
    branch: str = PR_BRANCH,
) -> list[PrResult]:
    """把 AI 结果推送成 PR；只推 generated，cached/failed/pending 全部跳过。

    抑制在 AI 输入哈希层完成（GP05/GP09/GP12）：cached 结果连一个 HTTP 请求都不发。
    force 重新生成的结果是 generated，照常推送（GP11）。
    传入 entries 时，推送成功后就地写回该仓 block_hash（托管区内容哈希，SB07）。
    """
    pushed: list[PrResult] = []
    for r in results:
        if r.status != "generated":
            continue
        res = open_or_refresh_pr(
            client,
            full_name=r.full_name,
            content=r.content or "",
            head_sha=r.head_sha,
            title=build_pr_title(r.full_name),
            body=build_pr_body(commits=r.commits, base_sha=r.base_sha, head_sha=r.head_sha),
            branch=branch,
        )
        if entries is not None:
            entry = entries.setdefault(
                r.full_name,
                {
                    "sha": r.head_sha,
                    "block_hash": "",
                    "mode": "block",
                    "failed_hash": "",
                    "last_input_hash": "",
                    "pending": False,
                },
            )
            entry["block_hash"] = content_block_hash(r.content or "")
        pushed.append(res)
    return pushed
