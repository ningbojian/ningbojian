"""配置加载与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_SORT_BY = ("score", "stars", "updated")
VALID_CARDS = ("stats", "top_langs", "streak")


class ConfigError(Exception):
    """配置错误（消息为中文）。"""


@dataclass
class ScheduleConfig:
    enabled: bool = True


@dataclass
class GitHubConfig:
    username: str = ""
    token_env: str = "GITHUB_TOKEN"


@dataclass
class ReposConfig:
    exclude_forks: bool = True
    exclude_archived: bool = False
    exclude: list[str] = field(default_factory=list)


@dataclass
class FeaturedConfig:
    count: int = 6
    min_stars: int = 0
    recency_days: int = 365
    sort_by: str = "score"
    score_stars_weight: float = 1.0
    score_recency_weight: float = 0.5


@dataclass
class CardsConfig:
    theme: str = "github_dark"
    show: list[str] = field(default_factory=lambda: ["stats", "top_langs", "streak"])


@dataclass
class ReadmeConfig:
    enabled: bool = True  # false = 本次不更新 overview README
    path: str = "README.md"
    template: str = "templates/profile.md.j2"
    cards: CardsConfig = field(default_factory=CardsConfig)
    include_update_time: bool = True


@dataclass
class AIConfig:
    enabled: bool = True
    model: str = "claude-opus-5-5"
    max_repos: int = 15
    max_age_days: int = 14
    bio_min_chars: int = 100
    bio_max_chars: int = 150
    language: str = "zh-CN"
    prompt_version: int = 1


@dataclass
class ProjectsConfig:
    """方向二：按仓库生成深度项目介绍 / 简历素材（docs/projects/）。"""

    enabled: bool = True
    dir: str = "docs/projects"
    featured_only: bool = True
    review_via_pr: bool = True  # 生成/更新走 PR 人工审核；false = 直接提交
    include: list[str] = field(default_factory=list)  # 非空 = 只给这些仓库名生成
    exclude: list[str] = field(default_factory=list)  # 永远跳过这些仓库名


@dataclass
class SnapshotConfig:
    path: str = "data/snapshot.json"


@dataclass
class Config:
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    repos: ReposConfig = field(default_factory=ReposConfig)
    featured: FeaturedConfig = field(default_factory=FeaturedConfig)
    readme: ReadmeConfig = field(default_factory=ReadmeConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    projects: ProjectsConfig = field(default_factory=ProjectsConfig)
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)


def _section(data: dict, key: str) -> dict:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"配置项 {key} 必须是一个映射（键值对）")
    return value


def load_config(path: Path, *, fallback_username: str | None = None) -> Config:
    """读取 config.yaml 并校验，失败抛出 ConfigError（中文消息）。

    github.username 为空时可用 fallback_username（如 Actions 的
    GITHUB_REPOSITORY_OWNER）兜底，实现 fork 即用、零配置。
    """
    if not path.exists():
        raise ConfigError(f"找不到配置文件：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件 YAML 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是映射（键值对）")

    cfg = Config()
    sched = _section(data, "schedule")
    cfg.schedule = ScheduleConfig(enabled=bool(sched.get("enabled", True)))

    gh = _section(data, "github")
    username = str(gh.get("username") or "").strip()
    if not username and fallback_username:
        username = fallback_username.strip()
    if not username:
        raise ConfigError(
            "请先在 config.yaml 中填写 github.username（你的 GitHub 用户名）"
        )
    cfg.github = GitHubConfig(
        username=username,
        token_env=str(gh.get("token_env") or "GITHUB_TOKEN"),
    )

    repos = _section(data, "repos")
    exclude = repos.get("exclude") or []
    if not isinstance(exclude, list):
        raise ConfigError("repos.exclude 必须是列表")
    cfg.repos = ReposConfig(
        exclude_forks=bool(repos.get("exclude_forks", True)),
        exclude_archived=bool(repos.get("exclude_archived", False)),
        exclude=[str(x) for x in exclude],
    )

    feat = _section(data, "featured")
    sort_by = str(feat.get("sort_by") or "score")
    if sort_by not in VALID_SORT_BY:
        raise ConfigError(f"featured.sort_by 只能是 {VALID_SORT_BY} 之一，收到：{sort_by}")
    cfg.featured = FeaturedConfig(
        count=int(feat.get("count", 6)),
        min_stars=int(feat.get("min_stars", 0)),
        recency_days=int(feat.get("recency_days", 365)),
        sort_by=sort_by,
        score_stars_weight=float(feat.get("score_stars_weight", 1.0)),
        score_recency_weight=float(feat.get("score_recency_weight", 0.5)),
    )

    readme = _section(data, "readme")
    cards_raw = readme.get("cards") or {}
    if not isinstance(cards_raw, dict):
        raise ConfigError("readme.cards 必须是映射（键值对）")
    show = cards_raw.get("show") or ["stats", "top_langs", "streak"]
    if not isinstance(show, list):
        raise ConfigError("readme.cards.show 必须是列表")
    for name in show:
        if name not in VALID_CARDS:
            raise ConfigError(f"readme.cards.show 含未知卡片：{name}（可选：{VALID_CARDS}）")
    cfg.readme = ReadmeConfig(
        enabled=bool(readme.get("enabled", True)),
        path=str(readme.get("path") or "README.md"),
        template=str(readme.get("template") or "templates/profile.md.j2"),
        cards=CardsConfig(
            theme=str(cards_raw.get("theme") or "github_dark"),
            show=[str(x) for x in show],
        ),
        include_update_time=bool(readme.get("include_update_time", True)),
    )

    ai = _section(data, "ai")
    cfg.ai = AIConfig(
        enabled=bool(ai.get("enabled", True)),
        model=str(ai.get("model") or "claude-opus-5-5"),
        max_repos=int(ai.get("max_repos", 15)),
        max_age_days=int(ai.get("max_age_days", 14)),
        bio_min_chars=int(ai.get("bio_min_chars", 100)),
        bio_max_chars=int(ai.get("bio_max_chars", 150)),
        language=str(ai.get("language") or "zh-CN"),
        prompt_version=int(ai.get("prompt_version", 1)),
    )

    proj = _section(data, "projects")
    include = proj.get("include") or []
    exclude = proj.get("exclude") or []
    if not isinstance(include, list) or not isinstance(exclude, list):
        raise ConfigError("projects.include / projects.exclude 必须是列表")
    cfg.projects = ProjectsConfig(
        enabled=bool(proj.get("enabled", True)),
        dir=str(proj.get("dir") or "docs/projects"),
        featured_only=bool(proj.get("featured_only", True)),
        review_via_pr=bool(proj.get("review_via_pr", True)),
        include=[str(x) for x in include],
        exclude=[str(x) for x in exclude],
    )

    snap = _section(data, "snapshot")
    cfg.snapshot = SnapshotConfig(path=str(snap.get("path") or "data/snapshot.json"))

    return cfg
