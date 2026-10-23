"""核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Repo:
    name: str
    full_name: str
    description: str = ""
    language: str = ""
    stars: int = 0
    forks: int = 0
    private: bool = False
    fork: bool = False
    archived: bool = False
    pushed_at: datetime | None = None
    html_url: str = ""
    homepage: str = ""
    # 仓库默认分支（模式 B 的 PR 目标，§5.5）；/users/{u}/repos 载荷缺失时回落 main
    default_branch: str = "main"
    topics: list[str] = field(default_factory=list)

    @property
    def age_days(self) -> float | None:
        """距上次 push 的天数；无 push 记录返回 None。"""
        if self.pushed_at is None:
            return None
        delta = datetime.now(self.pushed_at.tzinfo) - self.pushed_at
        return delta.total_seconds() / 86400


@dataclass
class Totals:
    public_repos: int = 0
    followers: int = 0
    total_stars: int = 0
    top_languages: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class TemplateContext:
    username: str
    display_name: str
    blog: str
    totals: Totals
    featured: list[Repo]
    pinned: list[Repo] = field(default_factory=list)  # 置顶仓库（featured.pin 命中且未被 count 截断）
    bio_text: str = ""
    cards_theme: str = "github_dark"
    cards_show: list[str] = field(default_factory=lambda: ["stats", "top_langs", "streak"])
    include_update_time: bool = True
    updated_at: str = ""
    short_intros: dict[str, str] = field(default_factory=dict)  # full_name → AI 补位文案
    visitors_badge: bool = False  # 主页嵌入第三方「主页访问量」计数徽章
    key_env: str = "ANTHROPIC_API_KEY"  # 用户实际配置的 AI key secret 名（简介缺失提示用）


@dataclass
class BioInfo:
    text: str = ""
    input_hash: str = ""
    generated_at: str = ""
    model: str = ""
    prompt_version: int = 0


@dataclass
class Snapshot:
    schema: int = 3
    username: str = ""
    stats_fingerprint: str = ""
    stats_config_hash: str = ""
    totals: dict = field(default_factory=dict)
    repos: list[dict] = field(default_factory=list)
    bio: BioInfo = field(default_factory=BioInfo)
    # 模式 B（repo_readmes）逐仓状态：full_name → {sha, block_hash, mode,
    # failed_hash, last_input_hash, pending, updated_at}（设计 §5.1，schema 3）
    repo_readmes: dict[str, dict] = field(default_factory=dict)
    generated_at: str = ""
