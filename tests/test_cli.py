"""cli.py 离线端到端编排测试（用 fixture，不联网、不调 AI）。"""

import json
from pathlib import Path

from profile_agent.cli import run

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = Path(__file__).parent.parent / "templates" / "profile.md.j2"


def _write_config(tmp_path: Path, username: str = "alice") -> Path:
    cfg = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()  # noqa: E731
    cfg.write_text(
        f"""
github:
  username: "{username}"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    return cfg


def _run(cfg: Path, **kwargs) -> int:
    kwargs.setdefault("fixture", FIXTURES)
    kwargs.setdefault("no_ai", True)
    return run(cfg, **kwargs)


def test_dry_run_prints_readme_and_writes_nothing(tmp_path, capsys):
    cfg = _write_config(tmp_path)
    code = _run(cfg, dry_run=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "统计信息" in out and "仓库列表" in out
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "data" / "snapshot.json").exists()
    # --dry-run 承诺「只打印不写文件」——项目介绍目录同样不得落盘（M4 走查回归）
    assert not (tmp_path / "docs" / "projects").exists()


def test_full_run_never_creates_docs_projects(tmp_path):
    """项目介绍功能已移除（A-P0 回归锁②）：完整运行不得产生 docs/projects（0 token 消耗）。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    assert not (tmp_path / "docs" / "projects").exists()


def test_full_run_writes_readme_and_snapshot(tmp_path):
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    readme = tmp_path / "README.md"
    snap = tmp_path / "data" / "snapshot.json"
    assert readme.exists() and "统计信息" in readme.read_text(encoding="utf-8")
    # 有意变更（WP6→A-WP2）：旧注释锁「面板常驻」——面板已彻底移除，未配置 pin 时不再出现任何 📌
    assert "## 📌" not in readme.read_text(encoding="utf-8")  # 未配置 pin 不出置顶板块
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["username"] == "alice"
    assert data["stats_fingerprint"].startswith("sha256:")


def test_second_run_is_noop_when_unchanged(tmp_path):
    cfg = _write_config(tmp_path)
    _run(cfg)
    readme = tmp_path / "README.md"
    snap = tmp_path / "data" / "snapshot.json"
    readme_mtime = readme.stat().st_mtime_ns
    snap_mtime = snap.stat().st_mtime_ns
    assert _run(cfg) == 0
    # 无变化：文件时间戳不变（未重写）
    assert readme.stat().st_mtime_ns == readme_mtime
    assert snap.stat().st_mtime_ns == snap_mtime


def test_featured_pin_renders_pinned_section(tmp_path):
    """featured.pin 端到端（2026-10-23 置顶需求 + README 视觉改版）：置顶仓库渲染
    成 📌 置顶卡片，📦 仓库列表不重复它，板块顺序置顶在前。"""
    cfg = _write_config(tmp_path)
    with cfg.open("a", encoding="utf-8") as fh:
        fh.write('featured:\n  pin: ["alice/old-thing"]\n')
    assert _run(cfg) == 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "## 📌 置顶项目" in readme
    assert "⭐ **[old-thing](https://github.com/alice/old-thing)**｜" in readme
    assert "> 很久没动的项目" in readme  # 置顶卡片一句话摘要
    assert readme.index("## 📌 置顶项目") < readme.index("## 📦 仓库列表")
    assert "| [old-thing](" not in readme  # 列表不重复置顶仓库
    assert "| [cool-tool](" in readme  # 其余仓库仍在表格


# ---- A-WP2 一次性迁移：旧版置顶面板摘除 ----

# 旧版面板块（WP6 渲染形态：zh README 底部 <details> 折叠区 + pin-config 锚点）
_LEGACY_PANEL = (
    "<details>\n<summary><b>📌 置顶配置面板（网页直接勾选）</b></summary>\n\n"
    "<!-- pin-config:start -->\n- [x] alice/old-thing\n<!-- pin-config:end -->\n</details>\n\n"
)


def _simulate_legacy_run(tmp_path: Path, panel: str = _LEGACY_PANEL, extra: str = "") -> None:
    """把基线产物改写成「旧版最后一轮」形态：README/快照 base 都带面板、pins=旧勾选。"""
    readme = tmp_path / "README.md"
    snap = tmp_path / "data" / "snapshot.json"
    old_text = readme.read_text(encoding="utf-8").replace(
        "<!-- profile-agent:custom:start -->", panel + extra + "<!-- profile-agent:custom:start -->"
    )
    readme.write_text(old_text, encoding="utf-8")
    data = json.loads(snap.read_text(encoding="utf-8"))
    data["pins"] = ["alice/old-thing"]
    data["readme_last"] = old_text  # base = 旧版渲染输出（含面板）——真实升级形态
    snap.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_legacy_panel_stripped_once_then_noop(tmp_path, capsys):
    """A-WP2：盘上残留旧版面板 → 迁移轮整块摘除 + 中文警告；旧勾选沿用为置顶；下轮 noop。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    _simulate_legacy_run(tmp_path)
    assert _run(cfg) == 0
    out = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "pin-config" not in out  # 锚点随面板整块消失
    assert "置顶配置面板" not in out
    err = capsys.readouterr().err
    assert "警告：检测到旧版置顶面板/指针（一次性迁移），本轮已清除" in err
    assert "## 📌 置顶项目" in out  # prev.pins 过渡：旧面板勾选沿用为置顶
    # 迁移自终止：下一轮无残留、指纹一致 → noop（mtime 不变）
    mtime = (tmp_path / "README.md").stat().st_mtime_ns
    assert _run(cfg) == 0
    assert (tmp_path / "README.md").stat().st_mtime_ns == mtime


def test_legacy_en_pointer_stripped(tmp_path):
    """A-WP2：en 文件残留旧指针文案 → 迁移轮同样摘除（zh/en 标记独立检测）。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    en = tmp_path / "README.en.md"
    snap = tmp_path / "data" / "snapshot.json"
    pointer = (
        "> ⚙️ Pin configuration lives in the pin panel at the bottom of the Chinese README "
        "(tick, then Commit — it takes effect within seconds).\n"
    )
    old_en = en.read_text(encoding="utf-8").replace(
        "<!-- profile-agent:custom:start -->", pointer + "<!-- profile-agent:custom:start -->"
    )
    en.write_text(old_en, encoding="utf-8")
    # base 同步含指针（真实升级形态：旧版 en 渲染输出即带指针）
    data = json.loads(snap.read_text(encoding="utf-8"))
    data["readme_last_en"] = old_en
    snap.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert _run(cfg) == 0
    out = en.read_text(encoding="utf-8")
    assert "Pin configuration lives" not in out
    assert "pin panel" not in out


def test_user_edited_panel_lines_still_removed_by_migration(tmp_path):
    """A-WP2：用户手改过面板行也整块摘除（编辑与 ours 删除区间相撞被拦）；custom 手改保留。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    # 基线+旧面板作为 base；盘上=用户又勾了一个仓库（手改面板行）
    _simulate_legacy_run(tmp_path)
    readme = tmp_path / "README.md"
    theirs = readme.read_text(encoding="utf-8").replace(
        "- [x] alice/old-thing", "- [x] alice/old-thing\n- [x] alice/cool-tool"
    )
    readme.write_text(theirs, encoding="utf-8")
    assert _run(cfg) == 0
    out = readme.read_text(encoding="utf-8")
    assert "pin-config" not in out and "置顶配置面板" not in out
    # 沿用 base 里的旧勾选（手改的新增勾选随面板一并丢弃，不产生半摘状态）
    assert "⭐ **[old-thing](https://github.com/alice/old-thing)**｜" in out


def test_force_regenerates_even_when_unchanged(tmp_path):
    cfg = _write_config(tmp_path)
    _run(cfg)
    snap = tmp_path / "data" / "snapshot.json"
    before = snap.read_text(encoding="utf-8")
    snap.write_text(before.replace('"schema": 1', '"schema": 1'), encoding="utf-8")
    # 篡改指纹，force 应覆盖回来
    tampered = json.loads(before)
    tampered["stats_fingerprint"] = "sha256:tampered"
    snap.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    assert _run(cfg, force=True) == 0
    assert json.loads(snap.read_text(encoding="utf-8"))["stats_fingerprint"] != "sha256:tampered"


def test_missing_username_exits_nonzero(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('github:\n  username: ""\n', encoding="utf-8")
    assert _run(cfg) != 0


# ---- 修复轮与方向二新增 ----


def _with_env(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_env_username_fallback_zero_config(tmp_path, monkeypatch):
    """fork 即用：config 里 username 留空，靠 GITHUB_REPOSITORY_OWNER 兜底。"""
    cfg = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg.write_text(
        f"""
github:
  username: ""
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    _with_env(monkeypatch, GITHUB_REPOSITORY_OWNER="alice")
    assert run(cfg, fixture=FIXTURES, no_ai=True) == 0
    assert (tmp_path / "README.md").exists()


def _gen(monkeypatch, texts, calls):
    """替换 generate_bio：记录调用并按序返回 (zh, en, generated) 三元组（WP4）。"""
    import profile_agent.cli as cli_mod

    def fake(payload, cfg, **kwargs):
        calls.append(kwargs)
        return texts[len(calls) - 1]

    monkeypatch.setattr(cli_mod, "generate_bio", fake)


def test_ai_bio_generated_then_gate_skips(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    calls = []
    # 有意变更（WP4）：fake 需带 en——双语下 en 缺失会触发下轮重生成，门关不严
    _gen(monkeypatch, [("初始简介", "Initial EN", True)], calls)
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 1
    assert "初始简介" in (tmp_path / "README.md").read_text(encoding="utf-8")
    # 第二次：简介新鲜 + 数据无变 → 增量门整体跳过，不再调用
    # （有意变更 A-P0：原「项目介绍 AI 也成功」前提随功能移除，门不再有 projects 子句）
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 1


def test_stale_bio_regenerates_even_when_data_unchanged(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    calls = []
    _gen(monkeypatch, [("初始简介", "", True), ("刷新后的简介", "", True)], calls)
    run(cfg, fixture=FIXTURES)
    # 把简介时间改老（超过 max_age_days=14）
    snap_path = tmp_path / "data" / "snapshot.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["bio"]["generated_at"] = "2000-01-01T00:00:00+00:00"
    snap_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 2  # 简介过期 → 重新生成
    assert "刷新后的简介" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_config_change_invalidates_gate(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)
    # 改主题配置（显式写入 cards 段）→ 增量门必须失效并重渲染
    text = cfg.read_text(encoding="utf-8").replace(
        'readme:\n  path:',
        'readme:\n  cards:\n    theme: "github_light"\n  path:',
    )
    cfg.write_text(text, encoding="utf-8")
    assert run(cfg, fixture=FIXTURES) == 0
    assert "github_light" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_missing_readme_regenerated(tmp_path):
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)
    (tmp_path / "README.md").unlink()
    assert run(cfg, fixture=FIXTURES) == 0
    assert (tmp_path / "README.md").exists()


def test_ai_failure_with_no_previous_bio_returns_zero(tmp_path, monkeypatch):
    import profile_agent.cli as cli_mod
    from profile_agent.bio import BioError

    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="bad-key")
    monkeypatch.setattr(
        cli_mod, "generate_bio", lambda *a, **k: (_ for _ in ()).throw(BioError("boom"))
    )
    assert run(cfg, fixture=FIXTURES) == 0  # 任务不失败
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "AI 简介暂不可用" in readme  # 占位注释


def test_force_bypasses_gate(tmp_path, capsys):
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)
    capsys.readouterr()
    assert run(cfg, fixture=FIXTURES, force=True) == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" not in out  # 增量门没有拦截（明细表里的逐仓库「跳过」是另一回事）


def test_skip_readme_keeps_readme_untouched(tmp_path):
    """skip_readme（独立功能）：README 文件不动，快照等其余流程照常。"""
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)
    readme = tmp_path / "README.md"
    mtime = readme.stat().st_mtime_ns
    assert run(cfg, fixture=FIXTURES, skip_readme=True, force=True) == 0
    assert readme.stat().st_mtime_ns == mtime  # README 未被重写
    # 有意变更（A-P0）：原「介绍文件正常生成」断言随项目介绍功能移除删除
    assert not (tmp_path / "docs" / "projects").exists()


# ---- 描述补位 + 逐仓库精细化 ----


def test_short_intro_skips_profile_repo(tmp_path, monkeypatch):
    """补位文案同样跳过 profile 仓库自身（否则它的 README 每变一次就重生成一次）。"""
    import profile_agent.cli as cli_mod

    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    calls = []

    def fake(repo, cfg_ai, **kwargs):
        calls.append(repo.full_name)
        return "一个命令行密码生成器。", ""

    monkeypatch.setattr(cli_mod, "generate_short_intro", fake)
    fx = _empty_desc_fixture(tmp_path)
    # 在 fixture 里追加 profile 仓库自身（description 同样为空）
    repos = json.loads((fx / "repos.json").read_text(encoding="utf-8"))
    repos.append(
        {
            "name": "alice",
            "full_name": "alice/alice",
            "description": None,
            "language": "Python",
            "stargazers_count": 0,
            "forks_count": 0,
            "private": False,
            "fork": False,
            "archived": False,
            "pushed_at": "2026-10-01T00:00:00Z",
            "html_url": "https://github.com/alice/alice",
            "topics": [],
        }
    )
    (fx / "repos.json").write_text(json.dumps(repos), encoding="utf-8")

    assert run(cfg_path, fixture=fx) == 0
    assert calls == ["alice/mystery"], calls  # alice/alice 不得出现


def _empty_desc_fixture(tmp_path: Path) -> Path:
    """造一个 description 为空的精选仓库 fixture。"""
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "user.json").write_text(
        json.dumps({"login": "alice", "name": "Alice", "public_repos": 1, "followers": 0}),
        encoding="utf-8",
    )
    (fx / "repos.json").write_text(
        json.dumps(
            [
                {
                    "name": "mystery",
                    "full_name": "alice/mystery",
                    "description": None,
                    "language": "Python",
                    "stargazers_count": 3,
                    "forks_count": 0,
                    "private": False,
                    "fork": False,
                    "archived": False,
                    "pushed_at": "2026-10-01T00:00:00Z",
                    "html_url": "https://github.com/alice/mystery",
                    "topics": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    return fx


def test_short_intro_generated_for_empty_description_then_reused(tmp_path, monkeypatch):
    """description 为空的精选仓库：AI 生成补位文案，第二次运行复用不重调。"""
    import profile_agent.cli as cli_mod

    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    calls = []

    def fake(repo, cfg_ai, **kwargs):
        calls.append(repo.full_name)
        # 有意变更（WP4）：fake 需带 en——双语下 en 缺失会触发下轮重生成，复用断言碎
        return "一个命令行密码生成器。", "A CLI password generator."

    monkeypatch.setattr(cli_mod, "generate_short_intro", fake)
    fx = _empty_desc_fixture(tmp_path)

    assert run(cfg_path, fixture=fx) == 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "一个命令行密码生成器" in readme
    assert "（暂无描述）" not in readme
    assert calls == ["alice/mystery"]
    # 第二次：指纹命中 → 整体增量门跳过（含补位文案），不再调用
    assert run(cfg_path, fixture=fx) == 0
    assert calls == ["alice/mystery"]


def test_short_intro_disabled_by_config(tmp_path, monkeypatch):
    import profile_agent.cli as cli_mod

    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
ai:
  fill_empty_descriptions: false
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "generate_short_intro",
        lambda *a, **k: (calls.append(1) or "不该被调用", ""),
    )
    fx = _empty_desc_fixture(tmp_path)
    assert run(cfg_path, fixture=fx) == 0
    assert calls == []
    # 无补位 → 表格 — 占位（「暂无描述」废话已废弃）
    assert "| — |" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_run_writes_step_summary_table(tmp_path, monkeypatch):
    """Actions 的 GITHUB_STEP_SUMMARY 存在时，写出逐仓库动作明细表。

    有意变更（A-P0）：项目介绍列随功能移除，明细表只剩「主页描述补位」单列；
    表只在有补位目标（存在空描述仓库 + AI 可用）时出现，故用空描述 fixture + AI 挡板。
    """
    import profile_agent.cli as cli_mod

    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    summary = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    monkeypatch.setattr(cli_mod, "generate_short_intro", lambda *a, **k: ("密码生成器。", ""))
    fx = _empty_desc_fixture(tmp_path)
    assert run(cfg_path, fixture=fx) == 0
    text = summary.read_text(encoding="utf-8")
    assert "主页描述补位" in text
    assert "mystery" in text
    assert "已生成补位文案" in text


def test_snapshot_repos_carry_pushed_at(tmp_path):
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    data = json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))
    by_name = {r["full_name"]: r for r in data["repos"]}
    # 供勾选框标签显示「最近推送日期」用
    assert by_name["alice/cool-tool"]["pushed_at"].startswith("2026-10-01")


# ============================ WP3 双语 README（2026-10-23） ============================


def test_full_run_writes_both_readme_files(tmp_path):
    """bilingual 默认开：一次运行同时写 README.md（中文）与 README.en.md（英文），
    两文件顶部互链切换。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    zh = (tmp_path / "README.md").read_text(encoding="utf-8")
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "统计信息" in zh and "Statistics" in en
    switch = "🇨🇳 [中文](./README.md) · 🇺🇸 [English](./README.en.md)"
    assert switch in zh and switch in en


def test_bilingual_false_writes_only_readme_md(tmp_path):
    """bilingual: false 一键回退单文件：只产 README.md，不产 en（迁移护栏）。"""
    as_posix = lambda p: p.as_posix()  # noqa: E731
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
  bilingual: false
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    assert _run(cfg) == 0
    assert (tmp_path / "README.md").exists()
    assert not (tmp_path / "README.en.md").exists()


def test_deleted_en_readme_regenerated_by_gate(tmp_path):
    """en 文件被手删 → 增量门视为「readme 缺失」开门，重渲染时重建 README.en.md。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    (tmp_path / "README.en.md").unlink()
    assert _run(cfg) == 0  # 门不得早退
    assert (tmp_path / "README.en.md").exists()


def test_dry_run_prints_both_languages(tmp_path, capsys):
    """--dry-run 双语分段打印（zh 段 + en 段），不落盘。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg, dry_run=True) == 0
    out = capsys.readouterr().out
    assert "统计信息" in out and "Statistics" in out
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "README.en.md").exists()


def test_second_run_is_noop_with_bilingual(tmp_path):
    """双语幂等：连跑两遍，第二遍 zh/en 文件时间戳均不变（零写入）。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    zh, en = tmp_path / "README.md", tmp_path / "README.en.md"
    zh_mt, en_mt = zh.stat().st_mtime_ns, en.stat().st_mtime_ns
    assert _run(cfg) == 0
    assert zh.stat().st_mtime_ns == zh_mt
    assert en.stat().st_mtime_ns == en_mt


def test_bio_fresh_requires_en_when_bilingual(tmp_path, monkeypatch):
    """双语下新鲜判据补查 text_en：zh 新鲜但 en 缺失 → 必须重新生成（防单语卡死）。"""
    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    calls = []
    _gen(monkeypatch, [("第一版", "First EN", True), ("第二版", "Second EN", True)], calls)
    assert run(cfg, fixture=FIXTURES) == 0
    snap_path = tmp_path / "data" / "snapshot.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert data["bio"]["text"] == "第一版"
    assert data["bio"]["text_en"] == "First EN"
    # 清掉 en：指纹/时间仍新鲜，但双语下不完整 → 门必须开、重新生成
    data["bio"]["text_en"] = ""
    snap_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 2
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert data["bio"]["text"] == "第二版"
    assert data["bio"]["text_en"] == "Second EN"


def test_short_intro_clean_requires_en_when_bilingual(tmp_path, monkeypatch):
    """双语下补位复用判据补查 short_intro_en：en 缺失时不得复用 zh-only 旧文案。"""
    import profile_agent.cli as cli_mod

    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "Bio EN", True))
    calls = []

    def fake(repo, cfg_ai, **kwargs):
        calls.append(repo.full_name)
        return "一个命令行密码生成器。", "A CLI password generator."

    monkeypatch.setattr(cli_mod, "generate_short_intro", fake)
    fx = _empty_desc_fixture(tmp_path)

    assert run(cfg_path, fixture=fx) == 0
    assert "A CLI password generator." in (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert calls == ["alice/mystery"]
    # 清掉 short_intro_en：hash 仍匹配 → 复用判据必须因缺 en 而拒绝，重新生成
    snap_path = tmp_path / "data" / "snapshot.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    for repo in data["repos"]:
        repo.pop("short_intro_en", None)
    snap_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert run(cfg_path, fixture=fx) == 0
    assert calls == ["alice/mystery", "alice/mystery"]


# ============================ A-WP-B：英文版仓库描述自动英译 ============================


def _desc_translation_env(monkeypatch, translate_fake=None):
    """AI 环境 + bio 挡板 + 可注入的 translate_descriptions fake；返回调用批次记录。"""
    import profile_agent.cli as cli_mod

    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    calls = []

    def default_fake(items, cfg_ai, **kwargs):
        calls.append(list(items))
        return {fn: "A cool tool." for fn, _ in items}, ""

    monkeypatch.setattr(cli_mod, "translate_descriptions", translate_fake or default_fake)
    return calls


def _copy_fixture(tmp_path):
    """拷贝基线 fixture 到临时目录（可改 repos.json 后当 fixture 用）。"""
    fx = tmp_path / "fixture"
    fx.mkdir(exist_ok=True)
    for name in ("user.json", "repos.json"):
        (fx / name).write_text(
            (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return fx


def test_en_repo_descriptions_translated_and_cached(tmp_path, monkeypatch):
    """A-WP-B：含中文描述的仓库 en 出英译、zh 逐字原文；缓存落盘 desc_en + desc_en_src。"""
    cfg = _write_config(tmp_path)
    calls = _desc_translation_env(monkeypatch)
    assert run(cfg, fixture=FIXTURES) == 0
    zh = (tmp_path / "README.md").read_text(encoding="utf-8")
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "| [cool-tool](https://github.com/alice/cool-tool) | A cool tool. |" in en
    assert "一个很酷的工具" in zh  # zh 逐字原文（display_descs 恒空）
    assert "一个很酷的工具" not in en  # 英译命中后中文不再进 en
    assert calls and ("alice/cool-tool", "一个很酷的工具") in calls[0]
    data = json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))
    entry = next(r for r in data["repos"] if r["full_name"] == "alice/cool-tool")
    assert entry["desc_en"] == "A cool tool."
    assert entry["desc_en_src"] == "一个很酷的工具"


def test_translation_cached_on_force_rerun_zero_ai(tmp_path, monkeypatch):
    """A-WP-B：描述没变时 force 重渲染 0 次翻译调用（缓存仍喂 en 渲染）。"""
    cfg = _write_config(tmp_path)
    calls = _desc_translation_env(monkeypatch)
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 1
    assert run(cfg, fixture=FIXTURES, force=True) == 0
    assert len(calls) == 1  # 缓存新鲜（desc_en_src == description）→ 不重调
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "A cool tool." in en


def test_translation_ai_failure_falls_back_to_original(tmp_path, monkeypatch):
    """A-WP-B：翻译失败 → en 回落中文原文、退出码 0、不写缓存（下轮开门重试）。"""
    def fail(items, cfg_ai, **kwargs):
        return {}, "仓库描述英译失败（沿用原文）：api down"

    cfg = _write_config(tmp_path)
    _desc_translation_env(monkeypatch, fail)
    assert run(cfg, fixture=FIXTURES) == 0
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "一个很酷的工具" in en  # 回落原文
    data = json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))
    entry = next(r for r in data["repos"] if r["full_name"] == "alice/cool-tool")
    assert "desc_en" not in entry  # 失败不写缓存


def test_no_translation_when_bilingual_false(tmp_path, monkeypatch):
    """A-WP-B：单语模式（bilingual: false）不发起翻译、不产 en 文件。"""
    as_posix = lambda p: p.as_posix()  # noqa: E731
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
  bilingual: false
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    calls = _desc_translation_env(monkeypatch)
    assert run(cfg, fixture=FIXTURES) == 0
    assert calls == []  # 单语模式零翻译
    assert not (tmp_path / "README.en.md").exists()


def test_ascii_description_not_translated(tmp_path, monkeypatch):
    """A-WP-B：不含中文的描述（纯 ASCII）不进翻译请求（零回归裁定）。"""
    cfg = _write_config(tmp_path)
    fx = _copy_fixture(tmp_path)
    repos = json.loads((fx / "repos.json").read_text(encoding="utf-8"))
    for r in repos:
        if r["full_name"] == "alice/cool-tool":
            r["description"] = "A cool CLI tool"
    (fx / "repos.json").write_text(json.dumps(repos, ensure_ascii=False), encoding="utf-8")
    calls = _desc_translation_env(monkeypatch)
    assert run(cfg, fixture=fx) == 0
    requested = [fn for batch in calls for fn, _ in batch]
    assert "alice/cool-tool" not in requested  # 纯 ASCII 不译
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "A cool CLI tool" in en  # 照搬原文


def test_description_change_triggers_retranslate(tmp_path, monkeypatch):
    """A-WP-B：描述原文变化（desc_en_src 失效）→ 本轮开门重译并覆盖缓存。"""
    import profile_agent.cli as cli_mod

    cfg = _write_config(tmp_path)
    fx = _copy_fixture(tmp_path)
    calls = []

    def fake(items, cfg_ai, **kwargs):
        calls.append(list(items))
        return {fn: f"T:{desc}" for fn, desc in items}, ""

    monkeypatch.setattr(cli_mod, "translate_descriptions", fake)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("简介", "", True))
    assert run(cfg, fixture=fx) == 0
    assert len(calls) == 1
    assert "T:一个很酷的工具" in (tmp_path / "README.en.md").read_text(encoding="utf-8")
    # 改 fixture 里 cool-tool 的描述 → 指纹开门 + 缓存失效 → 重译
    repos = json.loads((fx / "repos.json").read_text(encoding="utf-8"))
    for r in repos:
        if r["full_name"] == "alice/cool-tool":
            r["description"] = "一个很酷的新工具"
    (fx / "repos.json").write_text(json.dumps(repos, ensure_ascii=False), encoding="utf-8")
    assert run(cfg, fixture=fx) == 0
    assert len(calls) == 2
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "T:一个很酷的新工具" in en
    assert "T:一个很酷的工具" not in en  # 旧译文被覆盖
    data = json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))
    entry = next(r for r in data["repos"] if r["full_name"] == "alice/cool-tool")
    assert entry["desc_en_src"] == "一个很酷的新工具"


def test_no_translation_without_ai_key(tmp_path, monkeypatch):
    """A-WP-B：缺 AI key（降级运行）→ 不翻译，en 回落中文原文（预期降级）。"""
    cfg = _write_config(tmp_path)
    calls = _desc_translation_env(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run(cfg, fixture=FIXTURES, no_ai=True) == 0
    assert calls == []
    en = (tmp_path / "README.en.md").read_text(encoding="utf-8")
    assert "一个很酷的工具" in en
