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
    assert "仓库统计" in out and "精选项目" in out
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "data" / "snapshot.json").exists()


def test_full_run_writes_readme_and_snapshot(tmp_path):
    cfg = _write_config(tmp_path)
    assert _run(cfg) == 0
    readme = tmp_path / "README.md"
    snap = tmp_path / "data" / "snapshot.json"
    assert readme.exists() and "仓库统计" in readme.read_text(encoding="utf-8")
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


def _block_project_ai(monkeypatch):
    """挡掉项目介绍的真实 AI 调用：让 update_project_intros 快速降级为数据版。

    这些测试关注的是 bio/门控逻辑；不挡的话 anthropic SDK 会真的去连网络。
    """
    import profile_agent.projects as projects_mod

    def fake(repo, cfg, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(projects_mod, "generate_project_intro", fake)


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
    """替换 generate_bio：记录调用并按序返回 (text, generated)。"""
    import profile_agent.cli as cli_mod

    def fake(payload, cfg, **kwargs):
        calls.append(kwargs)
        return texts[len(calls) - 1], True

    monkeypatch.setattr(cli_mod, "generate_bio", fake)


def test_ai_bio_generated_then_gate_skips(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    _block_project_ai(monkeypatch)
    calls = []
    _gen(monkeypatch, [("初始简介", True)], calls)
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 1
    assert "初始简介" in (tmp_path / "README.md").read_text(encoding="utf-8")
    # 第二次：简介新鲜 + 数据无变 → 增量门整体跳过，不再调用
    assert run(cfg, fixture=FIXTURES) == 0
    assert len(calls) == 1


def test_stale_bio_regenerates_even_when_data_unchanged(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    _with_env(monkeypatch, ANTHROPIC_API_KEY="test-key")
    _block_project_ai(monkeypatch)
    calls = []
    _gen(monkeypatch, [("初始简介", True), ("刷新后的简介", True)], calls)
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
    _block_project_ai(monkeypatch)
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
    assert "跳过" not in out


def test_skip_projects_keeps_intros_untouched(tmp_path):
    """只更新 overview：数据变化时 README 更新，但介绍文件保持原样。"""
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)  # 无 AI key：生成数据版介绍
    intro = tmp_path / "docs" / "projects" / "cool-tool.md"
    assert intro.exists()
    before = intro.read_text(encoding="utf-8")
    intro.unlink()  # 删掉一个介绍文件
    assert run(cfg, fixture=FIXTURES, skip_projects=True, force=True) == 0
    assert not intro.exists()  # --skip-projects 不重建
    assert (tmp_path / "README.md").exists()


def test_skip_readme_keeps_readme_untouched(tmp_path):
    """只更新项目介绍：README 不动，介绍文件正常生成。"""
    cfg = _write_config(tmp_path)
    run(cfg, fixture=FIXTURES)
    readme = tmp_path / "README.md"
    mtime = readme.stat().st_mtime_ns
    (tmp_path / "docs" / "projects" / "cool-tool.md").unlink()
    assert run(cfg, fixture=FIXTURES, skip_readme=True, force=True) == 0
    assert readme.stat().st_mtime_ns == mtime  # README 未被重写
    assert (tmp_path / "docs" / "projects" / "cool-tool.md").exists()


def test_projects_include_whitelist(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    as_posix = lambda p: p.as_posix()
    cfg_path.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
projects:
  include: ["cool-tool"]
readme:
  path: "{as_posix(tmp_path / 'README.md')}"
  template: "{as_posix(TEMPLATE)}"
snapshot:
  path: "{as_posix(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    assert run(cfg_path, fixture=FIXTURES, no_ai=True) == 0
    files = {p.name for p in (tmp_path / "docs" / "projects").iterdir()}
    assert files == {"cool-tool.md"}  # include 白名单外的仓库不生成
