"""模式 B 与增量门的交互测试（测试计划 Q09、Q17-Q20，离线 fixture + 注入 fetcher）。"""

import datetime as dt
import json
from pathlib import Path

from profile_agent.cli import run

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = Path(__file__).parent.parent / "templates" / "profile.md.j2"

# fixture 归一化后的参与仓库（fork/私有被剔除，old-profile 被 config 排除）
PARTICIPANTS = ["alice/archived-one", "alice/cool-tool", "alice/old-thing"]


class _FrozenDT:
    """固定时间：两次运行渲染出的 README 逐字节可比。"""

    FROZEN = dt.datetime(2026, 10, 22, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.FROZEN.astimezone(tz)
        return cls.FROZEN


def _freeze_time(monkeypatch):
    import profile_agent.cli as cli_mod

    monkeypatch.setattr(cli_mod, "datetime", _FrozenDT)


class FakeFetchers:
    def __init__(self, heads=None, compares=None):
        self.heads = dict(heads or {})
        self.compares = dict(compares or {})
        self.head_calls: list[str] = []
        self.compare_calls: list[tuple] = []

    def fetch_head(self, full_name: str) -> str:
        self.head_calls.append(full_name)
        if full_name not in self.heads:
            raise AssertionError(f"未注册的 head：{full_name}")
        return self.heads[full_name]

    def fetch_compare(self, full_name: str, base: str, head: str):
        self.compare_calls.append((full_name, base, head))
        key = (full_name, base, head)
        if key not in self.compares:
            raise AssertionError(f"未注册的 compare：{key}")
        return self.compares[key]


def _heads_all(sha="head0001"):
    return {fn: sha for fn in PARTICIPANTS}


def _write_config(tmp_path: Path, *, rr_enabled: bool = True) -> Path:
    cfg = tmp_path / "config.yaml"
    p = lambda x: x.as_posix()  # noqa: E731
    rr = "true" if rr_enabled else "false"
    cfg.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{p(tmp_path / 'README.md')}"
  template: "{p(TEMPLATE)}"
repo_readmes:
  enabled: {rr}
snapshot:
  path: "{p(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    return cfg


def _run(cfg: Path, fetchers=None, **kwargs) -> int:
    kwargs.setdefault("fixture", FIXTURES)
    kwargs.setdefault("no_ai", True)
    if fetchers is not None:
        kwargs["readme_fetchers"] = fetchers
    return run(cfg, **kwargs)


def _snapshot(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))


def test_global_force_forces_b_first_seen_without_recording_baseline(tmp_path, capsys):
    """Q09：全局 force 同时强制 A 与 B——首见仓合成全量队列项入队（不发 compare、不记基线）。"""
    cfg = _write_config(tmp_path)
    fetchers = FakeFetchers(heads=_heads_all("head789"))
    assert _run(cfg, fetchers, force=True) == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" not in out  # force 开门
    assert "入队 3 仓" in out  # 三仓合成入队（旧空树 compare 路径在生产必 404）
    assert fetchers.compare_calls == []
    assert (tmp_path / "README.md").exists()  # A 照常
    assert _snapshot(tmp_path)["repo_readmes"] == {}  # no_ai 不落条目（与 Q21 成对：全局 force=A+B）


def test_pending_opens_gate_and_b_runs(tmp_path, capsys):
    """Q17：任一仓库 pending 积压 → 增量门开启，B 跑过且基线推进可观察。"""
    cfg = _write_config(tmp_path)
    # 第一轮：首见，三仓各记基线 head0001
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0
    snap = _snapshot(tmp_path)
    assert set(snap["repo_readmes"]) == set(PARTICIPANTS)
    # 人工构造：cool-tool 置 pending（不依赖 M2 缺 key 路径）；old-thing 基线改 stale 便于观察推进
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repo_readmes"]["alice/cool-tool"]["pending"] = True
    data["repo_readmes"]["alice/old-thing"]["sha"] = "stale00"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # 第二轮：old-thing 基线..HEAD 出现仅 README 变更 → 基线推进（B 状态可观察）
    fetchers = FakeFetchers(
        heads=_heads_all("head0001"),
        compares={
            ("alice/old-thing", "stale00", "head0001"): {
                "commits": [{"sha": "head0001", "message": "docs: bot"}],
                "files": [{"filename": "README.md", "patch": "@@ -1 +1 @@\n-a\n+b"}],
            }
        },
    )
    capsys.readouterr()
    assert _run(cfg, fetchers) == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" not in out  # pending 开门
    snap = _snapshot(tmp_path)
    assert snap["repo_readmes"]["alice/old-thing"]["sha"] == "head0001"  # 本轮新计算的 B 状态
    assert snap["repo_readmes"]["alice/cool-tool"]["sha"] == "head0001"  # 未动仓库不被强制入队
    assert fetchers.compare_calls == [("alice/old-thing", "stale00", "head0001")]


def test_gate_stays_closed_without_pending(tmp_path, capsys):
    """Q18：无 pending、指纹不变 → 门维持原逻辑关闭，B 连 fetcher 都不碰。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0
    snap_path = tmp_path / "data" / "snapshot.json"
    snap_mtime = snap_path.stat().st_mtime_ns
    fetchers = FakeFetchers()  # 任何调用都会 AssertionError
    capsys.readouterr()
    assert _run(cfg, fetchers) == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" in out
    assert fetchers.head_calls == [] and fetchers.compare_calls == []
    assert snap_path.stat().st_mtime_ns == snap_mtime  # snapshot 未被改写


def test_gate_open_but_empty_queue_runs_at_zero_cost(tmp_path, monkeypatch, capsys):
    """Q19：pending 开门但队列空（无新提交）→ 零成本跑完，Summary/日志有可读原因。"""
    _freeze_time(monkeypatch)
    cfg = _write_config(tmp_path)
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repo_readmes"]["alice/cool-tool"]["pending"] = True
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    readme_path = tmp_path / "README.md"
    readme_mtime = readme_path.stat().st_mtime_ns
    fetchers = FakeFetchers(heads=_heads_all())  # base==head → 零 compare
    capsys.readouterr()
    assert _run(cfg, fetchers) == 0
    out = capsys.readouterr().out
    assert "模式 B 状态" in out and "无新提交" in out  # 静默有可读原因（§4 护栏）
    assert fetchers.compare_calls == []  # 零成本
    assert readme_path.stat().st_mtime_ns == readme_mtime  # README 无重写


def test_unrelated_change_opens_gate_but_untouched_repo_zero_cost(tmp_path, capsys):
    """Q20：无关仓库开门（指纹变化）时，未动仓库零成本跳过。"""
    cfg = _write_config(tmp_path)
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0
    # 篡改指纹模拟无关仓库数据变化开门
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stats_fingerprint"] = "sha256:tampered"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fetchers = FakeFetchers(heads=_heads_all())  # 各仓 base==head → 零 compare
    capsys.readouterr()
    assert _run(cfg, fetchers) == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" not in out  # 门已打开
    assert fetchers.head_calls == PARTICIPANTS  # B 跑过
    assert fetchers.compare_calls == []  # 但未动仓库零成本


# ---- 生产事故回归（逐仓隔离 + 状态行诚实，不得用「无事可做」掩盖失败）----


def test_fetch_head_404_isolated_and_status_honest(tmp_path, capsys):
    """生产 404 事故回归：门开 + 某仓 fetch_head 404（PAT 不可见）→ 只跳过该仓、
    其余照常、整轮退出码 0；状态行写「读取失败」而非「无事可做」。"""
    from profile_agent.github_client import GitHubError

    cfg = _write_config(tmp_path)
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0  # 首轮：三仓各记基线

    # pending 开门（模拟门开 + 一仓恰好不可见）
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repo_readmes"]["alice/old-thing"]["pending"] = True
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    class HeadErrFetchers(FakeFetchers):
        def fetch_head(self, full_name):
            self.head_calls.append(full_name)
            if full_name == "alice/cool-tool":
                raise GitHubError("GitHub API 返回 404：用户不存在或仓库不可见")
            return self.heads[full_name]

    fetchers = HeadErrFetchers(heads=_heads_all())  # 其余 base==head → 零 compare
    capsys.readouterr()
    assert _run(cfg, fetchers) == 0  # 整轮不受影响，退出码 0
    out = capsys.readouterr().out
    assert "模式 B 状态" in out and "读取失败" in out  # 失败可见
    assert "无事可做" not in out  # 不再被「无事可做」掩盖
    # 坏仓被跳过、基线不被强推；其余仓照常处理
    assert _snapshot(tmp_path)["repo_readmes"]["alice/cool-tool"]["sha"] == "head0001"
    assert fetchers.head_calls == PARTICIPANTS  # 坏仓抛错后仍继续查其余仓


def test_whole_b_crash_shows_failure_not_noop(tmp_path, monkeypatch, capsys):
    """整体（非逐仓）失败：_save_b_snapshot 落盘抛错 → 状态行写「整体失败」而非
    「无事可做」，且模式 A 不受影响、退出码 0。"""
    import profile_agent.cli as cli_mod

    cfg = _write_config(tmp_path)
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0  # 首轮记基线
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repo_readmes"]["alice/cool-tool"]["pending"] = True
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **k):
        raise RuntimeError("snapshot 落盘炸了")

    monkeypatch.setattr(cli_mod, "_save_b_snapshot", _boom)
    capsys.readouterr()
    assert _run(cfg, FakeFetchers(heads=_heads_all())) == 0  # A 不受影响，退出码 0
    out = capsys.readouterr().out
    assert "模式 B 状态" in out and "整体失败" in out  # 失败被点名
    assert "无事可做" not in out
