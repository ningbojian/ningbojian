"""基线生命周期测试（测试计划 SB05-SB23 中 M1 部分：SB05/SB06）。

快照层权威：首见只记基线（下轮正常入队）；仅 README 自身变更只推进基线（防循环）。
与 Q03/Q02 共用语义，本文件钉「下轮」与快照字段行为。
"""

from profile_agent.config import RepoReadmesConfig
from profile_agent.models import Repo
from profile_agent.repo_readmes import compute_queue

ALICE = "alice"
REPO = Repo(name="cool-tool", full_name="alice/cool-tool")


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
