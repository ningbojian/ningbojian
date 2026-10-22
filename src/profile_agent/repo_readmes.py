"""模式 B 队列计算：compare(基线SHA..HEAD) 五分支（设计 §4）。

- 无新提交            → 跳过（零调用，base==head 连 compare 都不发）
- 变更只有 README 自身 → 只推进基线（防自触发循环）
- 首次见到该仓库      → 只记基线（防启用即 PR 风暴），--force 例外（diff 从空树起算）
- compare 404/409     → 基线重置到当前 HEAD + 中文警告（历史被 rebase 重写，§12-R6）
- 有代码变更          → 进入处理队列，基线不前进（§5.1「开 PR 时基线不前进」）

纯函数 + 注入 fetcher：不碰网络、不碰 snapshot 文件；entries 就地更新（调用方落盘）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import RepoReadmesConfig
from .models import Repo

# git 的空树对象 SHA（首见 + force 时 diff 的虚拟基线）
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# 截断处的显式标记（裁定 R-T1：上限约束正文，标记允许超出少量字符）
TRUNCATED_MARK = "\n…（diff 超过上限已截断，仅保留最近提交的部分）…"


class CompareGone(Exception):
    """compare 返回 404/409（基线 SHA 已不在仓库历史里，通常因 rebase 重写）。"""


@dataclass
class QueueItem:
    """一个待处理仓库的队列项（喂给 AI 的原料，测试计划 §1.5）。"""

    full_name: str
    base_sha: str
    head_sha: str
    commits: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    diff_text: str = ""


def participants(repos: list[Repo], cfg: RepoReadmesConfig, username: str) -> list[str]:
    """参与模式 B 的仓库名单：repos 过滤结果 ∩ include/exclude，硬排除 profile 自身（§12-R1）。"""
    self_repo = f"{username}/{username}"
    inc = set(cfg.include)
    exc = set(cfg.exclude)
    names = [
        r.full_name
        for r in repos
        if r.full_name
        and r.full_name != self_repo
        and r.name not in exc
        and r.full_name not in exc
        and (not inc or r.name in inc or r.full_name in inc)
    ]
    return sorted(names)


def build_diff_text(commits: list[dict], files: list[dict], max_chars: int) -> str:
    """把提交标题与 diff 拼成喂 AI 的文本；超限按「最近优先」截断并加显式标记。

    文件 patch 排在提交标题之前（预算紧张时先保住代码事实，标题随后被裁）。
    """
    parts: list[str] = []
    for f in reversed(files):  # 最近文件优先
        name = str(f.get("filename") or "")
        patch = f.get("patch")
        if patch:
            parts.append(f"--- {name}\n{patch}")
        else:
            parts.append(f"--- {name}（无文本 diff）")
    for c in reversed(commits):  # 最近提交优先
        sha = str(c.get("sha") or "")[:7]
        message = str(c.get("message") or "").strip().splitlines()
        parts.append(f"提交 {sha}：{message[0] if message else ''}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + TRUNCATED_MARK
    return text


def _blank_entry(sha: str, now_iso: str) -> dict:
    return {
        "sha": sha,
        "block_hash": "",
        "mode": "block",
        "failed_hash": "",
        "last_input_hash": "",
        "pending": False,
        "updated_at": now_iso,
    }


def compute_queue(
    repos: list[Repo],
    entries: dict[str, dict],
    cfg: RepoReadmesConfig,
    username: str,
    *,
    fetch_head,
    fetch_compare,
    force: bool = False,
    now: datetime | None = None,
    stats: dict | None = None,
) -> list[QueueItem]:
    """计算本轮处理队列；entries（snapshot.repo_readmes）就地更新，由调用方落盘。

    fetch_head(full_name) -> 当前默认分支 HEAD sha；
    fetch_compare(full_name, base, head) -> {"commits": [...], "files": [...]}，
    404/409 时抛 CompareGone。

    stats（可选，就地填充）：queued / first_seen / readme_only / no_change / reset
    五个计数——cli 用它输出「模式 B 状态」行（设计 §8①，静默必须有可读原因）。
    """
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    counts = {"queued": 0, "first_seen": 0, "readme_only": 0, "no_change": 0, "reset": 0}
    queue: list[QueueItem] = []
    for full_name in participants(repos, cfg, username):
        head = fetch_head(full_name)
        entry = entries.get(full_name)
        if entry is None:
            if not force:
                entries[full_name] = _blank_entry(head, now_iso)  # 首见只记基线
                counts["first_seen"] += 1
                continue
            base = EMPTY_TREE_SHA  # force 例外：diff 从空树起算
        else:
            base = str(entry.get("sha") or "")
            if base == head:
                counts["no_change"] += 1
                continue  # 无新提交：零成本跳过，连 compare 都不发
        try:
            data = fetch_compare(full_name, base, head)
        except CompareGone:
            if entry is not None:
                entry["sha"] = head  # 重置到当前 HEAD（§12-R6）
                entry["updated_at"] = now_iso
            counts["reset"] += 1
            print(
                f"「{full_name}」compare 失败（404/409，基线可能已因历史重写失效），"
                f"已重置基线到当前 HEAD {head[:7]}",
                file=sys.stderr,
            )
            continue
        commits = [c for c in (data.get("commits") or []) if isinstance(c, dict)]
        files = [f for f in (data.get("files") or []) if isinstance(f, dict)]
        if not commits:
            counts["no_change"] += 1
            continue  # 无新提交（compare 显示无差异）
        if files and all(str(f.get("filename") or "") == "README.md" for f in files):
            # 只有 README 自身变更 → 只推进基线（防机器人提交触发循环）
            if entry is not None:
                entry["sha"] = head
                entry["updated_at"] = now_iso
            counts["readme_only"] += 1
            continue
        counts["queued"] += 1
        queue.append(
            QueueItem(
                full_name=full_name,
                base_sha=base,
                head_sha=head,
                commits=commits,
                files=files,
                diff_text=build_diff_text(commits, files, cfg.max_diff_chars),
            )
        )
    if stats is not None:
        stats.update(counts)
    return queue
