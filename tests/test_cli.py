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
