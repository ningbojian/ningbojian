"""命令行入口与编排：拉数据 → 聚合 → 增量判断 → AI 简介/项目介绍 → 渲染 → 写入。"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .aggregate import (
    bio_input_hash,
    build_bio_payload,
    compute_totals,
    normalize_repos,
    render_fingerprint,
    select_featured,
    stats_fingerprint,
)
from .bio import BioError, _is_fresh, generate_bio
from .checklist import (
    UNSET,
    append_final_state,
    find_checklist_issue,
    get_issue,
    parse_checked_prs,
    update_checklist,
)
from .config import Config, ConfigError, load_config
from .github_client import API, GitHubClient, GitHubError
from .models import Snapshot, TemplateContext
from .projects import intro_filename, intro_input_hash, update_project_intros
from .render import render_readme, write_if_changed
from .repo_readmes import CompareGone, compute_queue, participants
from .repo_readmes_ai import MISSING_KEY_REASON, process_queue
from .repo_readmes_pr import (
    advance_baseline_from_merged_pr,
    get_open_pr,
    get_pr_detail,
    merge_pr,
    parse_commit_titles,
    push_results,
)
from .short_intro import generate_short_intro, short_intro_input_hash
from .snapshot import load_snapshot, save_snapshot
from .wait_merges import wait_first_line, wait_for_merges

# README 展示时间统一按北京时间（UTC+8）标注
_BEIJING = timezone(timedelta(hours=8))


def _load_fixture(fixture: Path, username: str) -> tuple[dict, list[dict]]:
    user = json.loads((fixture / "user.json").read_text(encoding="utf-8"))
    repos = json.loads((fixture / "repos.json").read_text(encoding="utf-8"))
    user.setdefault("login", username)
    return user, repos


def _prev_repo_states(prev: Snapshot | None) -> dict[str, dict]:
    if prev is None:
        return {}
    return {r["full_name"]: r for r in prev.repos if isinstance(r, dict) and r.get("full_name")}


def _project_targets(repos, featured, cfg: Config) -> list:
    """按 featured_only + include/exclude 白黑名单选出要生成介绍的仓库。

    profile 仓库自身（用户名/用户名）硬性排除：它的 README 是工具自己的输出、
    pushed_at 又随每次 bot 提交前进——自引用会让它每轮都「过期」，无限重生成
    项目介绍并开 PR（实测踩过），AI 额度被空烧。
    """
    base = featured if cfg.projects.featured_only else repos
    inc = set(cfg.projects.include)
    exc = set(cfg.projects.exclude)
    self_repo = f"{cfg.github.username}/{cfg.github.username}"
    return [
        r for r in base
        if r.name not in exc
        and (not inc or r.name in inc)
        and r.full_name != self_repo
    ]


def _projects_clean(
    targets, cfg: Config, prev: Snapshot | None, root: Path, *, ai_active: bool = False
) -> bool:
    """全部目标仓库的介绍文件都已是最新且存在 → 无待生成内容。

    AI 已可用（ai_active）但某仓库还是数据版占位（ai_generated=False）时
    视为不干净：下一次普通运行就升级重写，不让占位内容永久豁免。
    """
    states = _prev_repo_states(prev)
    out_dir = root / cfg.projects.dir
    for r in targets:
        st = states.get(r.full_name) or {}
        if st.get("intro_hash") != intro_input_hash(r, cfg.ai):
            return False
        if not (out_dir / intro_filename(r)).exists():
            return False
        if ai_active and not st.get("ai_generated"):
            return False
    return True


def _memo_readme(gh_client: GitHubClient | None):
    """同一次运行内每个仓库只拉一次 README；无 client 时返回空串。"""
    cache: dict[str, str] = {}

    def get(full_name: str) -> str:
        if full_name not in cache:
            cache[full_name] = gh_client.get_repo_readme(full_name) if gh_client else ""
        return cache[full_name]

    get.cache = cache  # 模式 B 预填 §5.6 内存/分支内容（A 同轮吸收）
    return get


def _fetchers_from_client(client: GitHubClient):
    """生产路径的 head/compare 取数：compare 归一化为队列层契约，404/409 → CompareGone。"""

    class _Fetchers:
        def fetch_head(self, full_name: str) -> str:
            data, _ = client._get(f"{API}/repos/{full_name}/commits/HEAD")
            assert isinstance(data, dict)
            return str(data.get("sha") or "")

        def fetch_compare(self, full_name: str, base: str, head: str):
            try:
                data, _ = client._get(f"{API}/repos/{full_name}/compare/{base}..{head}")
            except GitHubError as exc:
                if getattr(exc, "status", None) in (404, 409):
                    raise CompareGone(str(exc)) from exc
                raise
            assert isinstance(data, dict)
            return {
                "commits": [
                    {"sha": c.get("sha"), "message": (c.get("commit") or {}).get("message", "")}
                    for c in (data.get("commits") or [])
                    if isinstance(c, dict)
                ],
                "files": [f for f in (data.get("files") or []) if isinstance(f, dict)],
            }

    return _Fetchers()


def _fetch_tree_paths(client: GitHubClient, full_name: str, sha: str) -> list[str]:
    """二进制降级用文件树（§5.3）：只取 blob 路径。"""
    data, _ = client._get(f"{API}/repos/{full_name}/git/trees/{sha}?recursive=1")
    assert isinstance(data, dict)
    return [str(t.get("path") or "") for t in (data.get("tree") or []) if t.get("type") == "blob"]


def _save_b_snapshot(snap_path: Path, prev: Snapshot | None, cfg: Config, state: dict) -> None:
    """B 完成即落盘（§4 第 1 步）：等待期间被取消也不丢基线与 AI 缓存（SB22/SB23）。"""
    base = prev if prev is not None else Snapshot(username=cfg.github.username)
    save_snapshot(
        snap_path,
        dataclasses.replace(
            base,
            repo_readmes=state,
            generated_at=datetime.now(timezone.utc).isoformat(),
        ),
    )


def _short_intros_clean(targets, cfg: Config, prev: Snapshot | None, readme_of) -> bool:
    """全部补位目标都有最新文案（指纹含 README 内容）→ 无待生成内容。"""
    states = _prev_repo_states(prev)
    for r in targets:
        st = states.get(r.full_name) or {}
        if not st.get("short_intro"):
            return False
        if st.get("short_intro_hash") != short_intro_input_hash(r, cfg.ai, readme_of(r.full_name)):
            return False
    return True


def _append_summary(markdown: str) -> None:
    """写入 GitHub Actions 的运行摘要页（GITHUB_STEP_SUMMARY）；本地运行静默跳过。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")
    except OSError:
        pass


_B_STAT_LABELS = (
    ("queued", "入队"),
    ("first_seen", "首见记基线"),
    ("readme_only", "仅README推进基线"),
    ("no_change", "无新提交"),
    ("reset", "基线重置"),
    ("error", "读取失败"),
)


def _b_status_line(stats: dict, reason: str = "") -> str:
    """「模式 B 状态」一行（设计 §8①：静默必须能被看懂是设计如此还是出问题了）。"""
    parts = [f"{label} {stats.get(key, 0)} 仓" for key, label in _B_STAT_LABELS if stats.get(key)]
    if parts:
        body = "、".join(parts) + (f"（{reason}）" if reason else "")
    else:
        body = reason or "无事可做"
    return "模式 B 状态：" + body


def _b_repo_progress(r) -> str:
    """单仓进度描述（OR20 逐仓进度行；与 ProcessResult.status 一一对应）。"""
    return {
        "generated": "已推分支（PR 待审核）",
        "cached": "缓存命中，跳过 AI",
        "suppressed": "与上次失败输入相同，已抑制",
        "failed": "AI 失败（已记录，同输入下轮跳过）",
        "skipped": "README marker 不平衡，已跳过",
    }.get(r.status, "缺 key 积压")


def run(
    cfg_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    no_ai: bool = False,
    skip_readme: bool = False,
    skip_projects: bool = False,
    fixture: Path | None = None,
    only_repos: list[str] | None = None,
    readme_fetchers=None,
    readme_generate=None,
    b_client=None,
    issue_client=None,
    b_force: bool = False,
    merge_wait_minutes: float = 0,
    now_fn=None,
    sleep_fn=None,
) -> int:
    fallback = os.environ.get("GITHUB_REPOSITORY_OWNER")
    try:
        cfg: Config = load_config(cfg_path, fallback_username=fallback)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    # 手动点名仓库（--repos / 勾选板 /run）：精确到仓库一级，即使不在精选名单也生成；
    # 点名即「重跑」语义——忽略仓库级 hash 复用，强制重新生成
    named_repos = bool(only_repos and only_repos != ["all"])
    if named_repos:
        cfg.projects.include = list(only_repos)
        cfg.projects.featured_only = False

    root = cfg_path.parent
    readme_path = root / cfg.readme.path
    template_path = root / cfg.readme.template
    readme_active = cfg.readme.enabled and not skip_readme
    projects_active = cfg.projects.enabled and not skip_projects

    # 1. 取数
    gh_client: GitHubClient | None = None
    try:
        if fixture is not None:
            user, raw_repos = _load_fixture(fixture, cfg.github.username)
        else:
            token = os.environ.get(cfg.github.token_env) or None
            gh_client = GitHubClient(token)
            user = gh_client.get_user(cfg.github.username)
            raw_repos = gh_client.list_repos(cfg.github.username)
    except (GitHubError, OSError) as exc:
        print(f"获取数据失败：{exc}", file=sys.stderr)
        return 3

    # 2. 聚合
    repos = normalize_repos(raw_repos, cfg.repos)
    totals = compute_totals(user, repos)
    featured = select_featured(repos, cfg.featured)
    fingerprint = stats_fingerprint(totals, repos, featured)
    template_bytes = template_path.read_bytes() if template_path.exists() else b""
    cfg_hash = render_fingerprint(cfg, template_bytes, user)

    # 3. 增量门：数据、配置/模板/资料、README 存在、简介新鲜、项目介绍齐备 全部无变化才跳过
    snap_path = root / cfg.snapshot.path
    prev = load_snapshot(snap_path)
    proj_targets = _project_targets(repos, featured, cfg) if projects_active else []
    ai_active = bool(
        not no_ai and cfg.ai.enabled and os.environ.get(cfg.ai.key_env_name)
    )
    readme_of = _memo_readme(gh_client)
    # 描述补位目标：精选里 description 为空的仓库（开关关掉或无 AI key 则为空）；
    # profile 仓库自身同样排除——它的「README 内容」就是工具输出，自引用会每轮都变
    short_targets = (
        [
            r
            for r in featured
            if not r.description
            and r.full_name != f"{cfg.github.username}/{cfg.github.username}"
        ]
        if (readme_active and ai_active and cfg.ai.fill_empty_descriptions)
        else []
    )
    payload = build_bio_payload(user, featured, cfg.ai)
    cur_hash = bio_input_hash(payload, cfg.ai)
    if ai_active and prev is not None:
        bio_fresh = (
            bool(prev.bio.text)
            and prev.bio.input_hash == cur_hash
            and _is_fresh(prev.bio.generated_at, cfg.ai.max_age_days)
        )
    else:
        bio_fresh = True

    # 门的开门条件新增一条（设计 §7）：任一仓库留有积压标记（pending）→ 开门，
    # 否则「提交发生在缺 key 期间、指纹随后被记录」的积压会永远饿死
    b_pending = prev is not None and any(
        bool(e.get("pending")) for e in prev.repo_readmes.values()
    )

    # ---- 模式 B 前置（2026-10-23 设计验证修订）：PAT/清单通道/开局勾选收割先于增量门 ----
    # 勾选（- [x]）是用户的人工授权动作：无条件收割，门早退不得让它永不生效；
    # 门再由 merge_requested/b_force 决定是否放行整轮 B
    owner_repo = f"{cfg.github.username}/{cfg.github.username}"
    issue: dict | None = None
    issue_eff = None
    # 开局预取的清单 issue（2026-10-23 钩子①）：UNSET=未预取/预取失败（清单步现场搜索），
    # dict=确认命中（清单步免搜索），None=确认无清单（直接创建）
    issue_cached: object = UNSET
    checklist_closed = False
    merge_requested = False  # 门条件之一：清单里存在 - [x]（无论合并成败，用户在要求动作）
    attempted: set[tuple[str, int]] = set()  # 同轮每条勾选至多一次 PUT（防重复与误报）

    # PAT 解析（Option A）：注入参数优先；生产路径从 WORKFLOW_PAT 构造（fixture 离线不读环境）
    b_client_eff = b_client
    if b_client_eff is None and fixture is None:
        _pat = os.environ.get("WORKFLOW_PAT") or None
        if _pat:
            b_client_eff = GitHubClient(_pat)
    if b_force and not cfg.repo_readmes.enabled:
        _conflict = (
            "已勾选 repo_readmes 但 config.yaml 中 repo_readmes.enabled=false，本次未运行模式 B"
        )
        print(_conflict)
        _append_summary(f"- ⚠️ {_conflict}")

    # 清单通道提前解析（2026-10-23 钩子①）：开局预取清单、读勾选需要它
    # （IW27 权限分离保持：清单读写走 GITHUB_TOKEN/issue_client，合并走 PAT）
    if cfg.repo_readmes.enabled and b_client_eff is not None and not dry_run:
        if issue_client is not None:
            issue_eff = issue_client
        else:
            _tok = os.environ.get(cfg.github.token_env) or None
            if _tok:
                issue_eff = GitHubClient(_tok)

    def _merge_from_issue(src, where: str) -> list[tuple[str, int]]:
        """按清单勾选（- [x]）逐条代为合并（2026-10-23 §5.5 修订：勾选=人工授权）。

        返回成功合并的 (full_name, number) 列表（钩子①' 用它推进基线）；单条失败只
        记录不中断（修复后重新勾选、下轮重试）；同轮已试过的条目直接跳过（attempted：
        防重复 PUT 与「成功后再报失败」）；src 非 dict（None=无清单、UNSET=预取失败
        未命中）直接跳过——UNSET 是 truthy 哨兵，不能只判 falsy。
        """
        if not isinstance(src, dict) or b_client_eff is None:
            return []
        merged_refs: list[tuple[str, int]] = []
        for _cf, _cn in parse_checked_prs(str(src.get("body") or "")):
            if (_cf, _cn) in attempted:
                continue
            attempted.add((_cf, _cn))
            _ok, _why = merge_pr(b_client_eff, _cf, _cn)
            if _ok:
                merged_refs.append((_cf, _cn))
                _line = f"「{_cf}」PR #{_cn} 已按清单勾选合并（{where}）"
                print(_line)
                _append_summary(f"- ✅ {_line}")
            else:
                _line = (
                    f"「{_cf}」PR #{_cn} 勾选合并失败（{where}；修复后重新勾选，下轮重试）：{_why}"
                )
                print(_line, file=sys.stderr)
                _append_summary(f"- ⚠️ {_line}")
        return merged_refs

    # 钩子①（2026-10-23 勾选合并）：预取清单 → 按勾选代为合并。无条件先于增量门——
    # 门若先早退，cron 轮里的勾选将永不生效（设计验证实测缺口）
    if b_client_eff is not None and not dry_run and issue_eff is not None:
        try:
            issue_cached = find_checklist_issue(issue_eff, owner_repo)
        except Exception as exc:  # noqa: BLE001 —— 预取失败退化为清单步现场搜索
            print(f"清单预取失败（勾选合并跳过，清单步会重查）：{exc}", file=sys.stderr)
        if isinstance(issue_cached, dict):
            merge_requested = bool(parse_checked_prs(str(issue_cached.get("body") or "")))
        _merge_from_issue(issue_cached, "开局")

    # 增量门（2026-10-23 设计验证修订）：b_force（对话框承诺「全量重跑开 PR」，Q21）与
    # 清单勾选（merge_requested，用户在要求动作）都必须开门；enabled=false 时勾选只警告
    # 不运行（Q22）→ b_gate 含 enabled 判定，冲突警告已在上方输出
    b_gate = b_force and cfg.repo_readmes.enabled
    if (
        not force
        and not named_repos  # 点名即重跑：不走整体增量门
        and not b_gate
        and not merge_requested
        and prev is not None
        and prev.stats_fingerprint == fingerprint
        and prev.stats_config_hash == cfg_hash
        and (not readme_active or readme_path.exists())
        and bio_fresh
        and (not projects_active or _projects_clean(proj_targets, cfg, prev, root, ai_active=ai_active))
        and (not short_targets or _short_intros_clean(short_targets, cfg, prev, readme_of))
        and not b_pending
    ):
        print("无变化，跳过更新")
        return 0

    # 3.5 模式 B（M3）：合并检测 → 队列 → AI → 推送/PR → 即时落盘 → 清单 → 等待 → §5.6 新鲜度
    # --no-ai 时整个 AI 阶段跳过且不置 pending（显式关 AI 是开发/测试语义，不是缺 key 积压）
    repo_readmes_state: dict[str, dict] = dict(prev.repo_readmes) if prev else {}
    b_stats: dict = {}
    b_reason = ""
    b_crash = ""  # 整体（非逐仓）失败原因：状态行不得用「无事可做」掩盖（生产 404 事故回归）
    b_results = []
    b_merged: set[str] = set()
    open_prs: list[dict] = []
    b_readme_sources: dict[str, str] = {}  # §5.6：full_name → 内存/API 真源/分支/旧文
    fetchers = readme_fetchers
    if fetchers is None and b_client_eff is not None and cfg.repo_readmes.enabled:
        fetchers = _fetchers_from_client(b_client_eff)
    # B 活跃条件：启用 且（测试注入 fetchers 或 生产 PAT 可用）——queue-only 模式合法（IW10）
    b_active = cfg.repo_readmes.enabled and (fetchers is not None or b_client_eff is not None)
    # 各仓默认分支（§5.5 PR 目标；master 仓库不再硬编码 main 导致 422）
    default_bases = {r.full_name: r.default_branch for r in repos}

    if b_active:
        b_progress: list[str] = []  # 逐仓进度行（OR20：串行 AI 静默期的可见性，写 Summary）
        b_errors: list[str] = []  # 逐仓失败行（OR06：异常不跨仓传播，写 Summary）
        try:
            # 合并检测：已合并 bot PR 的基线推进到 PR head SHA（§12-R10）；b_merged 供 §5.3 剔除
            if b_client_eff is not None and not dry_run:
                for _fn, _entry in list(repo_readmes_state.items()):
                    if not _entry.get("sha"):
                        continue
                    try:
                        if advance_baseline_from_merged_pr(
                            b_client_eff,
                            _entry,
                            _fn,
                            cfg.repo_readmes.pr_branch,
                            base=default_bases.get(_fn, "main"),
                        ):
                            b_merged.add(_fn)
                    except Exception as exc:  # noqa: BLE001 —— 逐仓隔离：一仓合并检测失败不拖死其他仓
                        print(
                            f"「{_fn}」合并检测失败（本轮跳过该仓，不影响其他仓库）：{exc}",
                            file=sys.stderr,
                        )
                        b_errors.append(f"- `{_fn}` 合并检测失败：{exc}")

            b_queue = compute_queue(
                repos,
                repo_readmes_state,
                cfg.repo_readmes,
                cfg.github.username,
                fetch_head=fetchers.fetch_head,
                fetch_compare=fetchers.fetch_compare,
                force=force or b_force,
                stats=b_stats,
            )
            # 逐仓走完「AI → 推送」再进下一仓（OR20：第一仓终态行先于第二仓进度行）；
            # 逐仓 try 隔离（OR06：一仓推送失败不拖死其他仓）
            if b_queue and not no_ai:
                for item in b_queue:
                    try:
                        print(f"「{item.full_name}」AI 生成中（缓存/失败抑制则直接跳过）…")
                        one = process_queue(
                            [item],
                            repo_readmes_state,
                            cfg.ai,
                            cfg.repo_readmes,
                            ai_active=ai_active,
                            generate=readme_generate,
                            fetch_readme=(
                                b_client_eff.get_repo_readme if b_client_eff is not None else None
                            ),
                            fetch_tree=(
                                (lambda fn, sha: _fetch_tree_paths(b_client_eff, fn, sha))
                                if b_client_eff is not None
                                else None
                            ),
                            strip_readme=b_merged,
                            force=force or b_force,
                        )
                        b_results.extend(one)
                        if b_client_eff is not None and not dry_run:
                            # 只推 generated；成功后 entries 回写 block_hash（SB07）
                            for res in push_results(
                                b_client_eff,
                                one,
                                entries=repo_readmes_state,
                                branch=cfg.repo_readmes.pr_branch,
                                bases=default_bases,
                            ):
                                print(f"「{item.full_name}」已推分支：{res.html_url}")
                        for r in one:
                            b_progress.append(f"- `{r.full_name}`：{_b_repo_progress(r)}")
                    except Exception as exc:  # noqa: BLE001 —— 逐仓隔离，不跨仓传播（OR06）
                        print(
                            f"「{item.full_name}」模式 B 失败（不影响其他仓库与模式 A）：{exc}",
                            file=sys.stderr,
                        )
                        b_errors.append(f"- `{item.full_name}`：{exc}")
            # B 完成即落盘（§4 第 1 步，SB22/23）：等待期间被取消也不丢基线与 AI 缓存
            if not dry_run:
                _save_b_snapshot(snap_path, prev, cfg, repo_readmes_state)
        except Exception as exc:  # noqa: BLE001 —— B 任何异常都不得阻断 A（§4 护栏）
            print(f"模式 B 失败（不影响模式 A）：{exc}", file=sys.stderr)
            b_errors.append(f"- 整体：{exc}")
            b_crash = str(exc)
        if b_progress or b_errors:
            _append_summary(
                "### 模式 B 逐仓进度\n" + "\n".join(b_progress + b_errors)
            )

    # 钩子①'（2026-10-23 设计验证修订）：扫描前再收割一次——AI/推送阶段（可达数分钟）期间
    # 新勾选若不先收割会被清单重建抹掉；合并成功即同轮推进该仓基线（attempted 挡重复 PUT）
    if b_client_eff is not None and not dry_run and issue_eff is not None:
        try:
            if isinstance(issue_cached, dict):
                cur_issue = get_issue(issue_eff, owner_repo, int(issue_cached["number"]))
            elif issue_cached is None:
                cur_issue = None  # 开局确认无既有清单：本轮新建的不可能有用户勾选
            else:
                cur_issue = find_checklist_issue(issue_eff, owner_repo)  # 预取失败退化重查
            for _cf, _cn in _merge_from_issue(cur_issue, "推送后"):
                _merged_entry = repo_readmes_state.get(_cf)
                if _merged_entry and _merged_entry.get("sha"):
                    try:
                        if advance_baseline_from_merged_pr(
                            b_client_eff,
                            _merged_entry,
                            _cf,
                            cfg.repo_readmes.pr_branch,
                            base=default_bases.get(_cf, "main"),
                        ):
                            b_merged.add(_cf)
                    except Exception as exc:  # noqa: BLE001 —— 逐仓隔离：推进失败不拖死扫描
                        print(
                            f"「{_cf}」合并后基线推进失败（不影响清单重建）：{exc}",
                            file=sys.stderr,
                        )
        except Exception as exc:  # noqa: BLE001 —— 收割失败不拖死扫描与清单
            print(f"扫描前清单收割失败（忽略，清单重建照旧）：{exc}", file=sys.stderr)

    # open-PR 扫描（清单/等待的输入）；§5.6 新鲜度预填延后到等待之后——
    # 等待中被结清的 PR 不得再用分支内容（OR04 回退旧文防线）
    if b_client_eff is not None and cfg.repo_readmes.enabled and not dry_run:
        for _fn, _entry in sorted(repo_readmes_state.items()):
            if not _entry.get("sha"):
                continue
            pr = get_open_pr(
                b_client_eff, _fn, cfg.repo_readmes.pr_branch,
                base=default_bases.get(_fn, "main"),
            )
            if pr:
                pr_info = {
                    "full_name": _fn,
                    "html_url": pr.get("html_url", ""),
                    "number": pr.get("number"),
                    "branch": cfg.repo_readmes.pr_branch,
                }
                # W3 清单明细（2026-10-23）：list 接口不带统计——逐 PR 单 GET；
                # 失败降级为无细节条目（清单省略该行，不拖死扫描）
                try:
                    det = get_pr_detail(b_client_eff, _fn, int(pr["number"]))
                except Exception as exc:  # noqa: BLE001 —— 明细失败不影响清单主行
                    print(
                        f"「{_fn}」PR 明细获取失败（清单该条省略细节）：{exc}",
                        file=sys.stderr,
                    )
                    det = None
                if isinstance(det, dict):
                    for _k in ("additions", "deletions", "changed_files", "commits"):
                        if isinstance(det.get(_k), int):
                            pr_info[_k] = det[_k]
                    if isinstance(det.get("mergeable_state"), str):
                        pr_info["mergeable_state"] = det["mergeable_state"]
                    pr_info["commit_titles"] = parse_commit_titles(
                        str(det.get("body") or "")
                    )
                open_prs.append(pr_info)

    # 「模式 B 状态」行（§8①）：七种静默场景各有可读原因，日志 + Summary 同源；每轮必有（OR11②）
    if b_crash:
        b_reason = f"整体失败（不影响模式 A）：{b_crash}"  # 失败不得被「无事可做」掩盖
    elif b_force and not cfg.repo_readmes.enabled:
        b_reason = "未运行（勾选与 config 开关冲突，见上方警告）"
    elif not cfg.repo_readmes.enabled:
        b_reason = "未启用（config.yaml repo_readmes.enabled=false）"
    elif b_client_eff is None and readme_fetchers is None:
        b_reason = "未运行：缺 WORKFLOW_PAT，无法 compare/推送（配好后自动启用）"
    elif any(r.status == "pending" for r in b_results):
        b_reason = MISSING_KEY_REASON
    elif any(r.status == "suppressed" for r in b_results):
        b_reason = "本批输入与上次失败相同已跳过（不会自动重试；新提交或 --force 才重试）"
    status_line = _b_status_line(b_stats, b_reason)
    print(status_line)
    _append_summary(f"- {status_line}")

    # 3.6 清单/通知 + 等待（§4-2/§4-3）：有 open PR 才动 issue；等待仅勾选且非空时执行
    # （issue_eff 已在开局解析；issue_cached 为钩子①的预取——省一次搜索，条件同款）
    if cfg.repo_readmes.enabled and b_client_eff is not None and not dry_run:
        wait_hint = ""
        if merge_wait_minutes > 0 and open_prs:
            _until = (
                datetime.now(_BEIJING) + timedelta(minutes=merge_wait_minutes)
            ).strftime("%H:%M")
            wait_hint = wait_first_line(len(open_prs), _until)
        if issue_eff is not None:
            try:
                issue = update_checklist(
                    issue_eff,
                    owner_repo,
                    open_prs,
                    username=cfg.github.username,
                    updated_at=datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M"),
                    branch=cfg.repo_readmes.pr_branch,
                    tail=wait_hint,
                    existing=issue_cached,
                )
            except Exception as exc:  # noqa: BLE001 —— 清单失败任务不失败（IW26）
                print(f"清单 issue 更新失败（不影响本轮任务）：{exc}", file=sys.stderr)
        if open_prs:
            # Summary 清单快照（IW25）：无论 issue 通道是否可用都留一份可点的清单
            _append_summary(
                "### README 待合并清单\n"
                + "\n".join(f"- {p['full_name']}：{p['html_url']}" for p in open_prs)
                + (f"\n清单 issue：{issue['html_url']}" if issue else "\n（清单 issue 未创建）")
            )

    waited = False
    current: set[tuple[str, int]] = set()
    if merge_wait_minutes > 0 and open_prs and b_client_eff is not None and not dry_run:
        pending_refs = [
            (str(p["full_name"]), int(p["number"]))
            for p in open_prs
            if p.get("number")
        ]
        if pending_refs:
            waited = True
            current = set(pending_refs)
            until_bj = (
                datetime.now(_BEIJING) + timedelta(minutes=merge_wait_minutes)
            ).strftime("%H:%M")
            first = wait_first_line(len(pending_refs), until_bj)
            print(f"等待合并：{first}")
            _append_summary(f"### 等待合并\n{first}")

            def _on_change(pending: list[tuple[str, int]]) -> None:
                nonlocal current, checklist_closed, issue
                current = set(pending)
                if not pending:
                    checklist_closed = True
                remaining = [
                    p for p in open_prs if (p["full_name"], p["number"]) in current
                ]
                if issue is not None and issue_eff is not None:
                    try:
                        # 回带最新 body：收尾 append_final_state 在其上追加，
                        # 抹掉已结清条目（终审 I1）
                        issue = update_checklist(
                            issue_eff,
                            owner_repo,
                            remaining,
                            username=cfg.github.username,
                            updated_at=datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M"),
                            branch=cfg.repo_readmes.pr_branch,
                            existing=issue,
                        )
                    except Exception as exc:  # noqa: BLE001 —— 刷新失败忽略，不拖死等待
                        print(f"清单刷新失败（忽略）：{exc}", file=sys.stderr)
                print(f"::notice::等待合并：还剩 {len(pending)} 条待处理")

            def _tick_merge() -> None:
                # 钩子②（2026-10-23）：等待期间新勾选 → 立即代为合并，本轮轮询即见结果；
                # 每 tick 按号直读清单（勾选是用户在等待期间改的；按号 GET 不消耗
                # 搜索路由的测试配额/限流预算），异常自隔离不拖死等待
                if issue is None or issue_eff is None:
                    return
                try:
                    cur = get_issue(issue_eff, owner_repo, int(issue["number"]))
                    _merge_from_issue(cur, "等待中")
                except Exception as exc:  # noqa: BLE001
                    print(f"等待中勾选合并失败（忽略，下个 tick 重试）：{exc}", file=sys.stderr)

            try:
                wait_result = wait_for_merges(
                    b_client_eff,
                    pending_refs,
                    minutes=merge_wait_minutes,
                    now_fn=now_fn or time.monotonic,
                    sleep_fn=sleep_fn or time.sleep,
                    on_change=_on_change,
                    on_tick=_tick_merge,
                )
            except KeyboardInterrupt:
                raise  # 取消语义：B 产物已落盘，不回滚（IW24 前半）
            except Exception as exc:  # noqa: BLE001 —— 轮询失败不拖死整轮，按超时继续
                print(f"等待合并轮询失败（继续执行模式 A）：{exc}", file=sys.stderr)
                wait_result = "timeout"
            if wait_result == "timeout":
                timeout_tail = "⏰ 等待窗口已耗尽，未合并的 PR 会继续留在清单里，任务继续。"
                print(timeout_tail)
                remaining = [
                    p for p in open_prs if (p["full_name"], p["number"]) in current
                ]
                if issue is not None and issue_eff is not None and remaining:
                    try:
                        # 回带 ⏰ 终态 body：收尾追加不得抹掉它（终审 I1）
                        issue = update_checklist(
                            issue_eff,
                            owner_repo,
                            remaining,
                            username=cfg.github.username,
                            updated_at=datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M"),
                            branch=cfg.repo_readmes.pr_branch,
                            tail=timeout_tail,
                            existing=issue,
                        )
                    except Exception as exc:  # noqa: BLE001 —— 终态行失败忽略
                        print(f"清单更新失败（忽略）：{exc}", file=sys.stderr)

    # 3.7 §5.6 同轮新鲜度（等待后评估，只喂主页描述补位会读的短介绍仓）：
    # 合并（含等待中合并）→ API 真源 > 等待中被关（拒绝）→ 旧文 > 本轮生成 → 内存 >
    # 静默且 PR 仍 open → 分支 > 其余 → 旧文（不预填，A 拉默认分支）
    if b_client_eff is not None and cfg.repo_readmes.enabled and not dry_run:
        generated = {
            r.full_name: r.content for r in b_results if r.status == "generated"
        }
        short_names = {r.full_name for r in short_targets}
        settled_ok: set[str] = set(b_merged)  # 合并检测已确认合并的仓
        settled_closed: set[str] = set()
        if waited:
            for p in open_prs:
                _fn = p["full_name"]
                if _fn not in short_names or (_fn, p["number"]) in current:
                    continue
                # 等待中结清 → 复查 GET /pulls/{n}：合并=新版真源，关闭=旧文（OR04 防线，
                # 绝不因「本轮生成过」把被拒内容留在主页——规则 3 覆盖规则 2）
                try:
                    data, _ = b_client_eff._get(f"{API}/repos/{_fn}/pulls/{p['number']}")
                    _merged = bool(isinstance(data, dict) and data.get("merged"))
                except Exception:  # noqa: BLE001 —— 状态复查失败按未合并（旧文）处理
                    _merged = False
                (settled_ok if _merged else settled_closed).add(_fn)
        for _fn in sorted(short_names):
            if _fn in settled_ok:
                b_readme_sources[_fn] = "API 真源"
                readme_of.cache[_fn] = b_client_eff.get_repo_readme(_fn)
            elif _fn in settled_closed:
                b_readme_sources[_fn] = "旧文"
                readme_of.cache[_fn] = b_client_eff.get_repo_readme(_fn)
            elif _fn in generated:
                b_readme_sources[_fn] = "内存"
                readme_of.cache[_fn] = generated[_fn]
            elif any(p["full_name"] == _fn for p in open_prs):
                b_readme_sources[_fn] = "分支"
                readme_of.cache[_fn] = b_client_eff.get_repo_readme(
                    _fn, ref=cfg.repo_readmes.pr_branch
                )
        # 对账行（§8④，OR10 每轮必含）：本轮 A（描述补位）读到的 README 各来自哪里
        counts = {"内存": 0, "API 真源": 0, "分支": 0, "旧文": 0}
        for r in short_targets:
            counts[b_readme_sources.get(r.full_name, "旧文")] += 1
        sources_line = (
            "本轮 A 的 README 输入来源："
            + "、".join(f"{label} {counts[label]}" for label in counts)
        )
        print(sources_line)
        _append_summary(f"- {sources_line}")

    # 4. 描述补位：缺 description 的精选仓库，用其 README 生成一句主页文案
    short_intros: dict[str, str] = {}
    short_states: dict[str, dict] = {}
    if short_targets:
        prev_states_all = _prev_repo_states(prev)
        for r in short_targets:
            readme_text = readme_of(r.full_name)
            h = short_intro_input_hash(r, cfg.ai, readme_text)
            st = prev_states_all.get(r.full_name) or {}
            if st.get("short_intro") and st.get("short_intro_hash") == h:
                short_intros[r.full_name] = st["short_intro"]
                continue
            try:
                text = generate_short_intro(r, cfg.ai, readme=readme_text)
            except Exception as exc:
                text = st.get("short_intro") or ""
                print(f"「{r.name}」描述补位失败，沿用旧文案：{exc}", file=sys.stderr)
            short_states[r.full_name] = {"short_intro": text, "short_intro_hash": h}
            if text:
                short_intros[r.full_name] = text

    # 4. AI 简介（只在更新 overview 时生成；失败保留旧简介，任务不失败）
    bio_text = prev.bio.text if prev else ""
    bio_generated = False
    if ai_active and readme_active:
        try:
            bio_text, bio_generated = generate_bio(
                payload,
                cfg.ai,
                input_hash=cur_hash,
                prev_hash=prev.bio.input_hash if prev else "",
                prev_text=prev.bio.text if prev else "",
                prev_generated_at=prev.bio.generated_at if prev else "",
            )
        except BioError as exc:
            print(f"简介生成失败，沿用旧简介：{exc}", file=sys.stderr)

    # 5. 项目介绍（方向二：仓库级增量；include/exclude 多选控制）
    project_states: dict[str, dict] = {}
    if projects_active and proj_targets:
        project_states = update_project_intros(
            proj_targets,
            dataclasses.replace(cfg.projects, dir=str(root / cfg.projects.dir)),
            cfg.ai,
            _prev_repo_states(prev),
            allow_ai=ai_active,
            # 真实抓取时把各仓库 README 拉下来喂给模型（介绍内容的信息密度来源）
            fetch_readme=gh_client.get_repo_readme if gh_client else None,
            # --force 或点名重跑：忽略仓库级 hash 复用
            force=force or named_repos,
            dry_run=dry_run,
        )

    now_bj = datetime.now(_BEIJING)
    changed = False
    if readme_active:
        ctx = TemplateContext(
            username=cfg.github.username,
            display_name=user.get("name") or cfg.github.username,
            blog=user.get("blog") or "",
            totals=totals,
            featured=featured,
            bio_text=bio_text,
            cards_theme=cfg.readme.cards.theme,
            cards_show=cfg.readme.cards.show,
            include_update_time=cfg.readme.include_update_time,
            updated_at=now_bj.strftime("%Y-%m-%d %H:%M") + "（北京时间）",
            short_intros=short_intros,
            visitors_badge=cfg.readme.visitors_badge,
            key_env=cfg.ai.key_env_name,
        )
        content = render_readme(ctx, template_path)

        if dry_run:
            print(content)
            return 0

        changed = write_if_changed(readme_path, content)
    elif dry_run:
        print("readme 已禁用（readme.enabled=false 或 --skip-readme），跳过 overview 生成")
        return 0

    # 6. 快照：bio 的 hash/时间只在本次真正生成时前进，复用/回退时保留旧值
    now_iso = datetime.now(timezone.utc).isoformat()
    if bio_generated:
        bio_info = dataclasses.replace(
            prev.bio if prev else Snapshot().bio,
            text=bio_text,
            input_hash=cur_hash,
            generated_at=now_iso,
            model=cfg.ai.model,
            prompt_version=cfg.ai.prompt_version,
        )
    else:
        bio_info = dataclasses.replace(
            prev.bio if prev else Snapshot().bio,
            text=bio_text,
        )

    merged_states = _prev_repo_states(prev)
    merged_states.update(project_states)
    merged_states.update(short_states)
    new_snap = Snapshot(
        schema=3,
        username=cfg.github.username,
        stats_fingerprint=fingerprint,
        stats_config_hash=cfg_hash,
        totals={
            "public_repos": totals.public_repos,
            "followers": totals.followers,
            "total_stars": totals.total_stars,
        },
        repos=[
            {
                "full_name": r.full_name,
                "stars": r.stars,
                "language": r.language,
                # 供 workflow 勾选框标签显示「最近推送日期」
                "pushed_at": r.pushed_at.isoformat() if r.pushed_at else "",
                **{
                    k: v
                    for k, v in (merged_states.get(r.full_name) or {}).items()
                    if k.startswith("intro_") or k.startswith("short_intro") or k == "ai_generated"
                },
            }
            for r in repos
        ],
        bio=bio_info,
        repo_readmes=repo_readmes_state,
        generated_at=now_iso,
    )
    save_snapshot(snap_path, new_snap)

    # 6.5 收尾（§4-5）：本轮确实更新了 Overview 且清单仍开着时，原地追加终态行。
    # （终审 I4：未更新 Overview 不写「已进入 main」——提交由随后的工作流步骤完成，
    # 不替它打包票；项目介绍 PR 在后续步骤创建，CLI 拿不到链接，不写入 issue）
    if issue is not None and issue_eff is not None and not checklist_closed and changed:
        try:
            append_final_state(issue_eff, owner_repo, issue)
        except Exception as exc:  # noqa: BLE001 —— 收尾行失败忽略，不改任务结果
            print(f"清单收尾更新失败（忽略）：{exc}", file=sys.stderr)

    # 7. 运行明细：逐仓库列出本次做了什么（写入 Actions 摘要页 + 日志）
    if proj_targets or short_targets:
        prev_states_all = _prev_repo_states(prev)
        proj_dir = root / cfg.projects.dir
        actions: dict[str, list[str]] = {}

        def _cell(name: str, col: int, value: str) -> None:
            actions.setdefault(name, ["—", "—"])[col] = value

        for r in proj_targets:
            st = prev_states_all.get(r.full_name) or {}
            new_st = project_states.get(r.full_name) or {}
            if not new_st.get("regenerated") and st.get("intro_hash") == intro_input_hash(
                r, cfg.ai
            ) and (proj_dir / intro_filename(r)).exists():
                action = "跳过（无变化）"
            elif new_st.get("ai_generated"):
                action = "已重新生成（AI，走 PR 审核）"
            else:
                action = "已生成数据版（AI 未启用或失败）"
            _cell(r.name, 0, action)
        for r in short_targets:
            if r.full_name not in short_states:
                _cell(r.name, 1, "已是最新（复用）")
            elif short_states[r.full_name].get("short_intro"):
                _cell(r.name, 1, "已生成补位文案")
            else:
                _cell(r.name, 1, "生成失败（保留暂无描述）")
        lines = [
            "## 本次运行明细（逐仓库）",
            "",
            "| 仓库 | 项目介绍 | 主页描述补位 |",
            "| --- | --- | --- |",
        ]
        for name, (a, b) in actions.items():
            lines.append(f"| `{name}` | {a} | {b} |")
        lines += [
            "",
            f"全部公开仓库（可在 projects_repos 里点名）：{'、'.join(sorted(r.name for r in repos))}",
        ]
        _append_summary("\n".join(lines))
        print("\n".join(lines))

    print("已更新" if changed else "内容无差异")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="自动维护 GitHub Profile README")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="打印到 stdout，不写文件")
    parser.add_argument("--force", action="store_true", help="忽略增量检测，强制重新生成")
    parser.add_argument("--no-ai", action="store_true", help="跳过 AI 调用（仍生成数据版内容）")
    parser.add_argument("--skip-readme", action="store_true", help="本次不更新 overview README")
    parser.add_argument("--skip-projects", action="store_true", help="本次不生成项目介绍")
    parser.add_argument(
        "--repos",
        default=None,
        help="只更新这些仓库的介绍（逗号分隔仓库名，可点名任意公开仓库）；all = 按 config 规则的全部",
    )
    parser.add_argument("--fixture", default=None, help="从本地 fixture 目录读取数据（离线测试）")
    parser.add_argument(
        "--repo-readmes", action="store_true", help="本次强制重跑模式 B（各仓库 README 托管区更新）"
    )
    parser.add_argument(
        "--wait-for-merges",
        action="store_true",
        help="等待待合并的 README PR 结清后再更新主页（默认窗口 30 分钟）",
    )
    parser.add_argument(
        "--merge-wait-minutes",
        type=float,
        default=None,
        help="等待合并窗口分钟数（0 = 不等待；给出时覆盖 --wait-for-merges 的默认 30）",
    )
    args = parser.parse_args(argv)
    only_repos = None
    if args.repos:
        only_repos = [s.strip() for s in args.repos.split(",") if s.strip()] or None
    merge_wait = 30.0 if args.wait_for_merges else 0.0
    if args.merge_wait_minutes is not None:
        merge_wait = args.merge_wait_minutes
    return run(
        Path(args.config),
        dry_run=args.dry_run,
        force=args.force,
        no_ai=args.no_ai,
        skip_readme=args.skip_readme,
        skip_projects=args.skip_projects,
        fixture=Path(args.fixture) if args.fixture else None,
        only_repos=only_repos,
        b_force=args.repo_readmes,
        merge_wait_minutes=merge_wait,
    )


if __name__ == "__main__":
    raise SystemExit(main())
