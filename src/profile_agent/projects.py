"""方向二：按仓库生成深度项目介绍 / 简历素材（docs/projects/）。

- 每个仓库一个 markdown 文件，文件头是事实数据（链接/star/语言/更新时间），
  正文优先由 AI 生成（项目简介 + 亮点 + 简历素材段），无 key 或失败时降级为纯数据版。
- 仓库级增量：intro_hash 不变且文件存在 → 不重新生成，不调 API。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import AIConfig, ProjectsConfig
from .models import Repo

_SYSTEM = (
    "你是一位技术写作与简历辅导助手，用简体中文撰写单个开源项目的介绍。"
    "只输出正文，不要 markdown 一级标题、代码块或解释。"
)


def intro_filename(repo: Repo) -> str:
    safe = re.sub(r"[^\w.\-]+", "-", repo.name).strip("-") or "repo"
    return f"{safe}.md"


def intro_input_hash(repo: Repo, cfg: AIConfig) -> str:
    payload = {
        "full_name": repo.full_name,
        "description": repo.description,
        "language": repo.language,
        "stars": repo.stars,
        "forks": repo.forks,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
        "prompt_version": cfg.prompt_version,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_intro_prompt(repo: Repo) -> str:
    facts = json.dumps(
        {
            "name": repo.name,
            "description": repo.description,
            "language": repo.language,
            "stars": repo.stars,
            "forks": repo.forks,
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"请为下面这个 GitHub 项目写中文介绍，包含三部分：\n"
        f"1. “项目介绍”：2-3 句话说明它解决什么问题、怎么解决；\n"
        f"2. “亮点”：3-5 条要点，每条以“- ”开头、不超过 30 字，只写可验证的事实；\n"
        f"3. “简历素材”：一段 40-80 字、可直接放进简历项目经历的描述，突出技术栈与成果，不要夸大。\n"
        f"已知事实（不得编造超出这些事实的内容，缺失的信息不要虚构）：\n{facts}\n"
    )


def _header(repo: Repo) -> str:
    updated = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "未知"
    lines = [
        f"<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->",
        f"# {repo.name}",
        "",
        f"- 仓库：[{repo.full_name}]({repo.html_url or 'https://github.com/' + repo.full_name})",
        f"- 语言：{repo.language or '未知'}　⭐ {repo.stars}　🍴 {repo.forks}",
        f"- 最近推送：{updated}",
        "",
    ]
    return "\n".join(lines)


def _data_stub(repo: Repo) -> str:
    parts = [
        "## 项目介绍",
        "",
        repo.description or "（GitHub 上暂无描述，可在仓库主页补充）",
        "",
        "## 亮点",
        "",
        f"- {repo.language or '多语言'} 项目，获得 {repo.stars} 个 star、{repo.forks} 个 fork",
        "",
        "## 简历素材",
        "",
        f"参与/维护 {repo.full_name}（{repo.language or '多语言'}），项目累计 {repo.stars} star。",
        "",
        "> （数据版占位：配置 ANTHROPIC_API_KEY 后重新生成可获得 AI 撰写的完整版本）",
        "",
    ]
    return "\n".join(parts)


def generate_project_intro(
    repo: Repo, cfg: AIConfig, *, client=None, http_post=None
) -> str:
    """调用配置的模型生成项目介绍正文（无文件头）。"""
    from .bio import chat_text

    text = chat_text(
        cfg, _SYSTEM, build_intro_prompt(repo), client=client, http_post=http_post
    ).strip()
    if not text:
        raise RuntimeError("模型返回了空的项目介绍")
    return text


def update_project_intros(
    repos: list[Repo],
    proj_cfg: ProjectsConfig,
    ai_cfg: AIConfig,
    prev_states: dict[str, dict],
    *,
    client=None,
    allow_ai: bool = True,
) -> dict[str, dict]:
    """按仓库增量生成/更新介绍文件。返回每仓库的新状态。

    - hash 匹配且文件存在 → 跳过（不调 API、不写文件），沿用旧状态
    - 否则重新生成：AI 可用且成功 → AI 正文；否则 → 数据版占位
    """
    out_dir = Path(proj_cfg.dir)
    now_iso = datetime.now(timezone.utc).isoformat()
    states: dict[str, dict] = {}

    for repo in repos:
        h = intro_input_hash(repo, ai_cfg)
        out_path = out_dir / intro_filename(repo)
        prev = prev_states.get(repo.full_name) or {}

        if prev.get("intro_hash") == h and out_path.exists():
            states[repo.full_name] = dict(prev)
            continue

        body = None
        ai_generated = False
        if allow_ai:
            try:
                body = generate_project_intro(repo, ai_cfg, client=client)
                ai_generated = True
            except Exception:
                body = None
        if body is None:
            body = _data_stub(repo)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_header(repo) + "\n" + body.strip() + "\n", encoding="utf-8")
        states[repo.full_name] = {
            "intro_hash": h,
            "intro_generated_at": now_iso,
            "ai_generated": ai_generated,
        }

    return states
