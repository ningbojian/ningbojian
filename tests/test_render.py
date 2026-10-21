"""render.py 模板渲染与写入测试。"""

from datetime import datetime, timezone
from pathlib import Path

from profile_agent.models import Repo, TemplateContext, Totals
from profile_agent.render import render_readme, write_if_changed

TEMPLATE = Path(__file__).parent.parent / "templates" / "profile.md.j2"


def _ctx() -> TemplateContext:
    return TemplateContext(
        username="alice",
        display_name="Alice Zhang",
        blog="https://alice.dev",
        totals=Totals(
            public_repos=42,
            followers=128,
            total_stars=230,
            top_languages=[("Python", 120), ("JavaScript", 80)],
        ),
        featured=[
            Repo(
                name="cool-tool",
                full_name="alice/cool-tool",
                description="一个很酷的工具",
                language="Python",
                stars=120,
                forks=12,
                pushed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                html_url="https://github.com/alice/cool-tool",
            ),
            Repo(
                name="web-app",
                full_name="alice/web-app",
                description="网页应用",
                language="JavaScript",
                stars=80,
                forks=4,
                pushed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                html_url="https://github.com/alice/web-app",
            ),
        ],
        bio_text="你好，我是 Alice，一名热爱开源的工程师。",
        cards_theme="github_dark",
        cards_show=["stats", "top_langs", "streak"],
        include_update_time=True,
        updated_at="2026-10-21 10:23",
    )


def test_render_contains_chinese_sections():
    out = render_readme(_ctx(), TEMPLATE)
    assert "你好，我是" in out
    assert "仓库统计" in out
    assert "精选项目" in out
    assert "你好，我是 Alice" in out  # AI 简介
    assert out.lstrip().startswith("<!--")  # 自动生成标记


def test_render_contains_stats_table_and_featured():
    out = render_readme(_ctx(), TEMPLATE)
    assert "| 公开仓库 | 42 |" in out
    assert "| 总 Star | 230 |" in out
    assert "[cool-tool](https://github.com/alice/cool-tool)" in out
    assert "一个很酷的工具" in out
    assert "网页应用" in out
    assert "⭐ 120" in out


def test_render_contains_card_urls():
    out = render_readme(_ctx(), TEMPLATE)
    assert "github-readme-stats.vercel.app/api?username=alice" in out
    assert "top-langs" in out
    assert "streak-stats.demolab.com/?user=alice" in out
    assert "theme=github_dark" in out
    assert "&amp;theme=github_dark" in out  # HTML 实体化的 &


def test_render_without_bio_leaves_comment():
    ctx = _ctx()
    ctx.bio_text = ""
    out = render_readme(ctx, TEMPLATE)
    assert "AI 简介" in out  # 注释形式
    assert "你好，我是 Alice，一名热爱开源的工程师。" not in out


def test_render_without_update_time():
    ctx = _ctx()
    ctx.include_update_time = False
    out = render_readme(ctx, TEMPLATE)
    assert "最后更新" not in out


def test_render_deterministic():
    assert render_readme(_ctx(), TEMPLATE) == render_readme(_ctx(), TEMPLATE)


def test_write_if_changed(tmp_path):
    path = tmp_path / "README.md"
    assert write_if_changed(path, "内容 A\n") is True
    assert path.read_text(encoding="utf-8") == "内容 A\n"
    assert write_if_changed(path, "内容 A\n") is False  # 无变化不写
    assert write_if_changed(path, "内容 B\n") is True
    assert path.read_text(encoding="utf-8") == "内容 B\n"
