"""基线生命周期测试（测试计划 SB05-SB23：SB05/SB06（M1）+ SB16-SB21（M2））。

快照层权威：首见只记基线（下轮正常入队）；仅 README 自身变更只推进基线（防循环）；
AI 失败/成功/缺 key 的快照字段行为；pending 积压的开门与补跑（端到端）。
与 Q03/Q02/AP11/AP15/AP17 共用语义，本文件钉「下轮」与快照字段行为。
"""

import json
from pathlib import Path

from profile_agent.config import AIConfig, RepoReadmesConfig
from profile_agent.models import Repo
from profile_agent.repo_readmes import QueueItem, build_diff_text, compute_queue
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


def _ih(item) -> str:
    """与 process_queue 同口径：基于 commits/files 现场重建的 diff 计算期望哈希（SB14 裁定）。"""
    return compute_input_hash(
        item,
        1,
        diff_text=build_diff_text(item.commits, item.files, RepoReadmesConfig().max_diff_chars),
    )


def _ai(queue, entries, generate, *, ai_active=True, cfg_rr=None, **kw):
    return process_queue(
        queue,
        entries,
        AIConfig(),
        cfg_rr or RepoReadmesConfig(enabled=True),
        ai_active=ai_active,
        generate=generate,
        **kw,
    )


def test_ai_failure_keeps_baseline_and_records_failed_hash():
    """SB16：AI 抛错 → 基线不动、failed_hash 落盘（快照层权威，与 AP11 成对）。"""
    entry = _entry("base123")

    def boom(system, prompt):
        raise RuntimeError("AI 挂了")

    results = _ai([_item()], {"alice/cool-tool": entry}, boom)
    assert results[0].status == "failed"
    assert entry["sha"] == "base123"  # 基线不动
    assert entry["failed_hash"] == _ih(_item())
    assert entry["last_input_hash"] == ""


def test_ai_success_clears_failed_hash_and_writes_last_input_hash():
    """SB17：AI 成功后清空 failed_hash 并写入新 last_input_hash；开 PR 前基线仍不前进。"""
    entry = _entry("base123", failed_hash="sha256:旧失败")

    def ok(system, prompt):
        return "一句话定位。\n- 亮点一"

    results = _ai([_item()], {"alice/cool-tool": entry}, ok)
    assert results[0].status == "generated"
    assert entry["failed_hash"] == ""
    assert entry["last_input_hash"] == _ih(_item())
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


# ---- M3：PR 生命周期的基线权威（SB07-SB15，与 GP 去重后本文件钉快照侧）----


def _pr_client(http):
    from profile_agent.github_client import GitHubClient

    return GitHubClient("p-pat", session=http)


def _merged_pr_http(http, *, head="HHH2222", merge="MMM3333", merged=True):
    """注册 merge 检测路由（sticky：多轮重复检测同一响应）。"""
    from fake_github import FakeHttp, FakeResponse  # noqa: F401 — 仅类型提示

    http.add(
        "GET",
        f"https://api.github.com/repos/alice/cool-tool/pulls?state=all&head=alice:readme-auto/update&base=main&sort=updated&direction=desc",
        FakeResponse(json_data=[{
            "number": 7,
            "merged": merged,
            "merge_commit_sha": merge if merged else None,
            "head": {"sha": head},
        }]),
        sticky=True,
    )


def test_squash_replay_hits_cache_keeps_baseline_and_skips_push():
    """SB14：squash 合并后 compare 恒非空 → 剔除 README hunk 后同批内容命中缓存；
    零 AI、零推送（含零 PR 查询）、last_input_hash/block_hash 不变、基线保持 HHH、不依赖 PR open。"""
    from fake_github import FakeHttp

    from profile_agent.repo_readmes_pr import advance_baseline_from_merged_pr, push_results

    c1 = {"sha": "HHH2222", "message": "feat: 新增 add 函数"}
    code_files = [{"filename": "src/core.py", "patch": "@@ -1 +1 @@\n+def add(a, b)"}]
    # 第一轮：人工代码变更 → 生成，记 last_input_hash 与 block_hash
    entries = {"alice/cool-tool": _entry("aaa1111")}
    rec: list = []
    q1 = _run(entries, {"alice/cool-tool": "HHH2222"},
              {("alice/cool-tool", "aaa1111", "HHH2222"):
               {"commits": [c1], "files": code_files}})
    assert [q.full_name for q in q1] == ["alice/cool-tool"]
    r1 = _ai(q1, entries, lambda s, p: rec.append(1) or "一句话。\n- 亮点")
    assert r1[0].status == "generated" and len(rec) == 1
    ih1 = entries["alice/cool-tool"]["last_input_hash"]
    bh1 = entries["alice/cool-tool"]["block_hash"]
    # 第二轮：PR 被 squash 合并 → 基线推进到 HHH；compare(HHH..SSS) 恒非空（重放同批内容）
    detect_http = FakeHttp()
    _merged_pr_http(detect_http, head="HHH2222", merge="MMM3333")
    assert advance_baseline_from_merged_pr(_pr_client(detect_http), entries["alice/cool-tool"],
                                           "alice/cool-tool", "readme-auto/update") is True
    assert entries["alice/cool-tool"]["sha"] == "HHH2222"
    bot_hunk = ("@@ -1,2 +1,7 @@\n # 标题\n+<!-- profile-agent:readme:start -->\n"
                "+一句话定位。\n+- 亮点\n+<!-- profile-agent:readme:end -->")
    q2 = _run(entries, {"alice/cool-tool": "SSS4444"},
              {("alice/cool-tool", "HHH2222", "SSS4444"):
               {"commits": [c1],  # 同批提交重放
                "files": [{"filename": "README.md", "patch": bot_hunk}, *code_files]}})
    assert len(q2) == 1  # compare 恒非空（squash 下 head 不在主干历史）
    r2 = _ai(q2, entries, lambda s, p: rec.append(1) or "x", strip_readme=True)
    assert r2[0].status == "cached"
    assert len(rec) == 1  # 零 AI
    # 推送层：空路由 FakeHttp——任何 HTTP 请求都会 AssertionError，证明零推送零 PR 查询
    pushed = push_results(_pr_client(FakeHttp()), r2)
    assert pushed == []
    e = entries["alice/cool-tool"]
    assert e["sha"] == "HHH2222"  # ④ 基线保持 HHH
    assert e["last_input_hash"] == ih1  # ③ 缓存字段不变
    assert e["block_hash"] == bh1
    assert e["failed_hash"] == ""


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
