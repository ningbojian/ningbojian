"""Jinja2 模板渲染与按需写入。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import TemplateContext

# 统一徽章样式：style=flat（自带 3px 圆角——shields 源码无 "rounded" 样式，
# 传未知 style 会抛错裂图；flat-square 方角已废弃）、无动画。
_BADGE_STYLE = "style=flat"
_STAT_COLOR = "8aa6c4"  # 统计/说明徽章主色（灰蓝，低饱和）
_SOFT_COLOR = "c9d8e8"  # 实时/日期徽章底色（浅蓝灰）

# 语言 → shields 徽章低饱和主色（2026-10-23 视觉规范：配色清新不刺眼；
# 旧的大红大亮原色如 Python 3776AB、JavaScript f7df1e 已废弃；未知语言用中性灰）
_LANG_COLORS: dict[str, str] = {
    "Python": "5b7f9e",
    "JavaScript": "b09a3f",
    "TypeScript": "5e81a8",
    "Go": "5b98a8",
    "Rust": "a3876a",
    "Java": "96764a",
    "C": "848f9e",
    "C++": "566f8c",
    "C#": "7568a0",
    "PHP": "646d8f",
    "Ruby": "8c5560",
    "Swift": "a9654e",
    "Kotlin": "8368bc",
    "Dart": "4d8ab5",
    "Vue": "5f9e7a",
    "HTML": "a56249",
    "CSS": "726384",
    "Shell": "6b9450",
    "Lua": "666a96",
    "Jupyter Notebook": "94764a",
    "Makefile": "657a4f",
}


def _static_badge_url(label: str, value: object, color: str) -> str:
    """shields 静态徽章 URL：字面横线写成 --，其余按 URL 编码转义，统一样式。

    value 为空时省略消息段（`badge/{label}-{color}`），避免双横线残缺 URL。
    """
    text = quote(str(label).replace("-", "--"), safe="")
    msg = quote(str(value).replace("-", "--"), safe="")
    mid = f"-{msg}" if msg else ""
    return f"https://img.shields.io/badge/{text}{mid}-{color}?{_BADGE_STYLE}"


def stat_badge(label: str, value: object) -> str:
    """统计徽章（📊 统计信息行）：markdown 图片语法，链接干净。"""
    return f"![{label}]({_static_badge_url(label, value, _STAT_COLOR)})"


def lang_badge(language: str) -> str:
    """语言静态彩色徽章；空语言返回空串（避免出空段的残缺 URL）。"""
    if not language:
        return ""
    color = _LANG_COLORS.get(language, "8a8f98")
    return f"![{language}]({_static_badge_url(language, '', color)})"


def lang_star_badge(language: str, stars: int) -> str:
    """🏷️ 技术标签徽章：语言 + star 计数（如 Python-120★），低饱和语言色。"""
    color = _LANG_COLORS.get(language, "8a8f98")
    return f"![{language}]({_static_badge_url(language, f'{stars}★', color)})"


def stars_badge(full_name: str) -> str:
    """star 实时徽章（img.shields.io 按需拉取，README 指纹不受数量变化影响）。"""
    return (
        f"![stars](https://img.shields.io/github/stars/{full_name}"
        f"?{_BADGE_STYLE}&label=stars&labelColor={_STAT_COLOR}&color={_SOFT_COLOR})"
    )


def forks_badge(full_name: str) -> str:
    """fork 实时徽章。"""
    return (
        f"![forks](https://img.shields.io/github/forks/{full_name}"
        f"?{_BADGE_STYLE}&label=forks&labelColor={_STAT_COLOR}&color={_SOFT_COLOR})"
    )


def push_badge(pushed_at: datetime | None) -> str:
    """最后推送日期静态徽章；无记录返回空串。"""
    if pushed_at is None:
        return ""
    # 横线转义交给 _static_badge_url 统一处理（2026-10-01 → 2026--10--01）
    date = pushed_at.strftime("%Y-%m-%d")
    return f"![last_push]({_static_badge_url('last_push', date, _SOFT_COLOR)})"


def render_readme(ctx: TemplateContext, template_path: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(()),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)
    return template.render(
        username=ctx.username,
        display_name=ctx.display_name,
        blog=ctx.blog,
        totals=ctx.totals,
        featured=ctx.featured,
        pinned=ctx.pinned,
        bio_text=ctx.bio_text,
        cards_theme=ctx.cards_theme,
        cards_show=ctx.cards_show,
        include_update_time=ctx.include_update_time,
        updated_at=ctx.updated_at,
        short_intros=ctx.short_intros,
        visitors_badge=ctx.visitors_badge,
        key_env=ctx.key_env,
        lang_badge=lang_badge,
        stars_badge=stars_badge,
        forks_badge=forks_badge,
        push_badge=push_badge,
        stat_badge=stat_badge,
        lang_star_badge=lang_star_badge,
    )


def write_if_changed(path: Path, content: str) -> bool:
    """内容有变化才写入；返回是否写入。"""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True
