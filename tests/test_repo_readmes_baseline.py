"""基线生命周期测试（测试计划 SB05-SB23：SB05/SB06（M1）+ SB16-SB21（M2））。

快照层权威：首见只记基线（下轮正常入队）；仅 README 自身变更只推进基线（防循环）；
AI 失败/成功/缺 key 的快照字段行为；pending 积压的开门与补跑（端到端）。
与 Q03/Q02/AP11/AP15/AP17 共用语义，本文件钉「下轮」与快照字段行为。
"""

import json
from pathlib import Path

from profile_agent.config import AIConfig, RepoReadmesConfig
from profile_agent.models import Repo
from profile_agent.repo_readmes import QueueItem, compute_queue
from profile_agent.repo_readmes_ai import compute_input_hash, process_queue

ALICE = "alice"
REPO = Repo(name="cool-tool", full_name="alice/cool-tool")
TEMPLATE = Path(__file__).parent.parent / "templates" / "profile.md.j2"
FIXTURES = Path(__file__).parent / "fixtures"

# fixture 归一化后的参与仓库（fork/私有被剔除，old-profile 被 config 排除）
PARTICIPANTS = ["alice/archived-one", "alice/cool-tool", "alice/old-thing"]


def _entry(sha, **kw):
    e = {
        "sha": sha,
        "block_hash": "",
        "mode": "block",
        "failed_hash": "",
        "last_input_hash": "",
        "pending": False,
        "updated_at": "old",
    }
    e.update(kw)
    return e


def _run(entries, heads, compares, force=False):
    return compute_queue(
        [REPO],
        entries,
        RepoReadmesConfig(enabled=True),
        ALICE,
        fetch_head=lambda fn: heads[fn],
        fetch_compare=lambda fn, b, h: compares[(fn, b, h)]
        if not isinstance(compares[(fn, b, h)], Exception)
        else (_ for _ in ()).throw(compares[(fn, b, h)]),
        force=force,
    )


def test_first_seen_baseline_then_next_round_queues_normally():
    """SB05：首见只记基线；下轮新提交从该基线起算正常入队。"""
    entries: dict = {}
    # 第一轮：只记基线 def456
    assert _run(entries, {"alice/cool-tool": "def456"}, {}) == []
    assert entries["alice/cool-tool"]["sha"] == "def456"
    # 第二轮：基线..HEAD 出现代码变更 → compare(def456..eee) 非空入队
    queue = _run(
        entries,
        {"alice/cool-tool": "eee8888"},
        {
            ("alice/cool-tool", "def456", "eee8888"): {
                "commits": [{"sha": "eee8888", "message": "feat: 真实提交"}],
                "files": [{"filename": "app.py", "patch": "+z = 3"}],
            }
        },
    )
    assert [q.full_name for q in queue] == ["alice/cool-tool"]
    assert entries["alice/cool-tool"]["sha"] == "def456"  # 入队不推进基线


def test_readme_only_change_advances_baseline_and_writes_no_suppress_fields():
    """SB06：仅 README 自身变更 → 只推进基线，不写 failed_hash/last_input_hash（防循环）。"""
    entries = {"alice/cool-tool": _entry("base123")}
    queue = _run(
        entries,
        {"alice/cool-tool": "def456"},
        {
            ("alice/cool-tool", "base123", "def456"): {
                "commits": [{"sha": "def456", "message": "docs: bot 更新"}],
                "files": [{"filename": "README.md", "patch": "@@ -1 +1 @@\n-a\n+b"}],
            }
        },
    )
    assert queue == []
    entry = entries["alice/cool-tool"]
    assert entry["sha"] == "def456"
    assert entry["failed_hash"] == ""
    assert entry["last_input_hash"] == ""
    assert entry["pending"] is False


# ---- M2：AI 阶段的快照字段权威（SB16-SB18，与 AP11/AP15 共用语义）----


def _item(**kw) -> QueueItem:
    base = dict(
        full_name="alice/cool-tool",
        base_sha="base123",
        head_sha="def456",
        commits=[{"sha": "def456", "message": "feat: 新功能"}],
        files=[{"filename": "src/app.py", "patch": "@@ -1 +1 @@\n+def add(a, b)"}],
    )
    base.update(kw)
    return QueueItem(**base)


def _ai(queue, entries, generate, *, ai_active=True, cfg_rr=None):
    return process_queue(
        queue,
        entries,
        AIConfig(),
        cfg_rr or RepoReadmesConfig(enabled=True),
        ai_active=ai_active,
        generate=generate,
    )


def test_ai_failure_keeps_baseline_and_records_failed_hash():
    """SB16：AI 抛错 → 基线不动、failed_hash 落盘（快照层权威，与 AP11 成对）。"""
    entry = _entry("base123")

    def boom(system, prompt):
        raise RuntimeError("AI 挂了")

    results = _ai([_item()], {"alice/cool-tool": entry}, boom)
    assert results[0].status == "failed"
    assert entry["sha"] == "base123"  # 基线不动
    assert entry["failed_hash"] == compute_input_hash(_item(), 1)
    assert entry["last_input_hash"] == ""


def test_ai_success_clears_failed_hash_and_writes_last_input_hash():
    """SB17：AI 成功后清空 failed_hash 并写入新 last_input_hash；开 PR 前基线仍不前进。"""
    entry = _entry("base123", failed_hash="sha256:旧失败")

    def ok(system, prompt):
        return "一句话定位。\n- 亮点一"

    results = _ai([_item()], {"alice/cool-tool": entry}, ok)
    assert results[0].status == "generated"
    assert entry["failed_hash"] == ""
    assert entry["last_input_hash"] == compute_input_hash(_item(), 1)
    assert entry["sha"] == "base123"  # 开 PR 时基线不前进（§5.1）


def test_missing_key_marks_pending_without_failed_hash():
    """SB18：AI key 缺失 → 整体跳过、置 pending、不记 failed_hash、基线不动（快照字段权威，与 AP15 成对）。"""
    entry = _entry("base123")
    called = []
    results = _ai([_item()], {"alice/cool-tool": entry}, lambda s, p: called.append(1), ai_active=False)
    assert called == []  # 零 AI 调用
    assert results[0].status == "pending"
    assert entry["pending"] is True
    assert entry["failed_hash"] == ""  # 缺 key 是积压不是失败（R3）
    assert entry["sha"] == "base123"  # 基线不动


# ---- M2 端到端：pending 开门与补跑（SB19-SB21，cli 接线后生效）----


class FakeFetchers:
    def __init__(self, heads=None, compares=None):
        self.heads = dict(heads or {})
        self.compares = dict(compares or {})
        self.head_calls: list[str] = []
        self.compare_calls: list[tuple] = []

    def fetch_head(self, full_name: str) -> str:
        self.head_calls.append(full_name)
        return self.heads[full_name]

    def fetch_compare(self, full_name: str, base: str, head: str):
        self.compare_calls.append((full_name, base, head))
        return self.compares[(full_name, base, head)]


def _write_config(tmp_path: Path, *, rr_include: list[str] | None = None) -> Path:
    cfg = tmp_path / "config.yaml"
    p = lambda x: x.as_posix()  # noqa: E731
    include_line = ""
    if rr_include is not None:
        items = ", ".join(f'"{x}"' for x in rr_include)
        include_line = f"  include: [{items}]\n"
    cfg.write_text(
        f"""
github:
  username: "alice"
repos:
  exclude: ["alice/old-profile"]
readme:
  path: "{p(tmp_path / 'README.md')}"
  template: "{p(TEMPLATE)}"
ai:
  fill_empty_descriptions: false  # fixture 模式无 client，避免补位路径真抓 README
projects:
  enabled: false  # 本文件只测 B 与门，项目介绍默认开启会带 key 轮次走真 AI 网络
repo_readmes:
  enabled: true
{include_line}snapshot:
  path: "{p(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    return cfg


def _run_cli(cfg: Path, fetchers, readme_generate=None, **kwargs) -> int:
    from profile_agent.cli import run

    kwargs.setdefault("fixture", FIXTURES)
    kwargs["readme_fetchers"] = fetchers
    kwargs["readme_generate"] = readme_generate
    return run(cfg, **kwargs)


def _snapshot(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))


def _noop_a(monkeypatch):
    """模式 A 的 AI 出口换成假实现（B 的假 AI 走 readme_generate 注入，互不干扰）。"""
    import profile_agent.cli as cli_mod

    monkeypatch.setattr(cli_mod, "generate_bio", lambda *a, **k: ("你好，我是 Alice。", True))
    monkeypatch.setattr(cli_mod, "generate_short_intro", lambda *a, **k: "")


CODE_CHANGE = {
    "commits": [{"sha": "head0002", "message": "feat: 真实提交"}],
    "files": [{"filename": "src/app.py", "patch": "@@ -1 +1 @@\n+def add(a, b)"}],
}


def test_missing_key_roundtrip_pending_opens_gate_and_backfill_runs(tmp_path, monkeypatch, capsys):
    """SB19：缺 key 那轮 B 自己置 pending（非手工）→ 下轮带 key 时门打开、compare 被请求、AI 补跑。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _noop_a(monkeypatch)
    cfg = _write_config(tmp_path)
    heads = {fn: "head0001" for fn in PARTICIPANTS}
    # 第一轮：首见记基线
    assert _run_cli(cfg, FakeFetchers(heads=heads)) == 0
    # 第二轮：有代码变更但缺 key → 整体跳过、置 pending、基线不动。
    # fixture 统计不变，篡改指纹模拟「别的数据变化开门」（真实场景是 pushed_at 变化）
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stats_fingerprint"] = "sha256:tampered"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fetchers1 = FakeFetchers(
        heads={**heads, "alice/cool-tool": "head0002"},
        compares={("alice/cool-tool", "head0001", "head0002"): CODE_CHANGE},
    )
    assert _run_cli(cfg, fetchers1) == 0
    snap = _snapshot(tmp_path)
    entry = snap["repo_readmes"]["alice/cool-tool"]
    assert entry["pending"] is True
    assert entry["failed_hash"] == ""  # 缺 key 是积压不是失败
    assert entry["sha"] == "head0001"  # 基线不动
    # 第三轮：配好 key → pending 开门（指纹未变）、compare 被请求、AI 补跑成功。
    # 只推 cool-tool 的 head——其余仓 base==head 零 compare（未注册的 compare 会 KeyError）
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    rec = []
    fetchers2 = FakeFetchers(
        heads={**heads, "alice/cool-tool": "head0002"},
        compares={("alice/cool-tool", "head0001", "head0002"): CODE_CHANGE},
    )
    capsys.readouterr()
    assert _run_cli(cfg, fetchers2, readme_generate=lambda s, p: rec.append((s, p)) or "一句话。\n- 亮点") == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" not in out  # pending 开门
    assert ("alice/cool-tool", "head0001", "head0002") in fetchers2.compare_calls
    assert len(rec) == 1  # 补跑恰好调用一次 AI
    entry = _snapshot(tmp_path)["repo_readmes"]["alice/cool-tool"]
    assert entry["pending"] is False  # 补跑成功清积压
    assert entry["last_input_hash"].startswith("sha256:")  # 已写入新批输入哈希


def test_backfill_clears_pending_then_gate_back_to_fingerprint(tmp_path, monkeypatch, capsys):
    """SB20：补跑成功后 pending 清除 → 再下轮（无新提交）门回到指纹判断，整体跳过且零 AI。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _noop_a(monkeypatch)
    cfg = _write_config(tmp_path)
    heads = {fn: "head0001" for fn in PARTICIPANTS}
    assert _run_cli(cfg, FakeFetchers(heads=heads)) == 0
    # 缺 key 轮：篡改指纹开门（fixture 统计不变），队列有货但缺 key → 置 pending
    path = tmp_path / "data" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stats_fingerprint"] = "sha256:tampered"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    f1 = FakeFetchers(
        heads={**heads, "alice/cool-tool": "head0002"},
        compares={("alice/cool-tool", "head0001", "head0002"): CODE_CHANGE},
    )
    assert _run_cli(cfg, f1) == 0
    assert _snapshot(tmp_path)["repo_readmes"]["alice/cool-tool"]["pending"] is True
    # 补跑轮：pending 清除（只推 cool-tool 的 head，其余仓零 compare）
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    rec: list = []
    f2 = FakeFetchers(
        heads={**heads, "alice/cool-tool": "head0002"},
        compares={("alice/cool-tool", "head0001", "head0002"): CODE_CHANGE},
    )
    assert _run_cli(cfg, f2, readme_generate=lambda s, p: rec.append(1) or "一句话。\n- 亮点") == 0
    assert _snapshot(tmp_path)["repo_readmes"]["alice/cool-tool"]["pending"] is False
    # 第四轮：无新提交、无 pending → 门回指纹判断，整体跳过，零 AI
    rec2: list = []
    f3 = FakeFetchers(heads={fn: "head0002" for fn in PARTICIPANTS})  # base==head，任何 compare 都会 KeyError
    capsys.readouterr()
    assert _run_cli(cfg, f3, readme_generate=lambda s, p: rec2.append(1) or "x") == 0
    out = capsys.readouterr().out
    assert "无变化，跳过更新" in out
    assert rec2 == []  # 零 AI 调用
    assert f3.compare_calls == []


def test_pending_is_per_repo_independent(tmp_path, monkeypatch, capsys):
    """SB21：pending 逐仓库独立——include 圈定的仓补跑成功清 pending，圈外积压保持。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _noop_a(monkeypatch)
    cfg = _write_config(tmp_path, rr_include=["cool-tool"])
    path = tmp_path / "data" / "snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 直接构造：两仓都积压，但 include 只放行 cool-tool
    path.write_text(
        json.dumps(
            {
                "schema": 3,
                "username": "alice",
                "repo_readmes": {
                    "alice/cool-tool": _entry("head0001", pending=True),
                    "alice/old-thing": _entry("head0001", pending=True),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fetchers = FakeFetchers(
        heads={fn: "head0002" for fn in PARTICIPANTS},
        compares={("alice/cool-tool", "head0001", "head0002"): CODE_CHANGE},
    )
    assert _run_cli(cfg, fetchers, readme_generate=lambda s, p: "一句话。\n- 亮点") == 0
    # include 圈外的 old-thing 根本不进 participants，积压保持
    assert ("alice/old-thing", "head0001", "head0002") not in fetchers.compare_calls
    snap = _snapshot(tmp_path)
    assert snap["repo_readmes"]["alice/cool-tool"]["pending"] is False
    assert snap["repo_readmes"]["alice/old-thing"]["pending"] is True
