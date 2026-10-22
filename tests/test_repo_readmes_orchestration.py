"""编排测试（测试计划 OR01-OR20 中 M1 部分：OR07）。

OR07：B 无变更时输出与纯 A 逐字节一致（M1 即可先写——启用 + 空队列不需要 AI 与推送）。
其余 OR 用例在 M3 接入 清单/等待/A 新鲜度 后补齐。
"""

import datetime as dt
from pathlib import Path

from profile_agent.cli import run

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = Path(__file__).parent.parent / "templates" / "profile.md.j2"

PARTICIPANTS = ["alice/archived-one", "alice/cool-tool", "alice/old-thing"]


class _FrozenDT:
    FROZEN = dt.datetime(2026, 10, 22, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.FROZEN.astimezone(tz)
        return cls.FROZEN


class FakeFetchers:
    def __init__(self, heads):
        self.heads = dict(heads)
        self.head_calls: list[str] = []
        self.compare_calls: list[tuple] = []

    def fetch_head(self, full_name: str) -> str:
        self.head_calls.append(full_name)
        if full_name not in self.heads:
            raise AssertionError(f"未注册的 head：{full_name}")
        return self.heads[full_name]

    def fetch_compare(self, full_name: str, base: str, head: str):
        self.compare_calls.append((full_name, base, head))
        raise AssertionError(f"零成本轮不应 compare：{(full_name, base, head)}")


def _write_config(tmp_path: Path, rr_enabled: bool) -> Path:
    cfg = tmp_path / "config.yaml"
    p = lambda x: x.as_posix()  # noqa: E731
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
  enabled: {"true" if rr_enabled else "false"}
snapshot:
  path: "{p(tmp_path / 'data' / 'snapshot.json')}"
""",
        encoding="utf-8",
    )
    return cfg


def test_b_no_change_output_bytes_identical_to_pure_a(tmp_path, monkeypatch):
    """OR07：启用 B 但队列空 → README 与纯 A 运行逐字节一致；零 AI、fetcher 只查 head。"""
    import profile_agent.cli as cli_mod

    monkeypatch.setattr(cli_mod, "datetime", _FrozenDT)

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    assert run(_write_config(dir_a, False), fixture=FIXTURES, no_ai=True) == 0
    pure_a = (dir_a / "README.md").read_bytes()

    dir_b = tmp_path / "b"
    dir_b.mkdir()
    fetchers = FakeFetchers({fn: "head0001" for fn in PARTICIPANTS})
    cfg_b = _write_config(dir_b, True)
    assert run(cfg_b, fixture=FIXTURES, no_ai=True, readme_fetchers=fetchers) == 0
    with_b = (dir_b / "README.md").read_bytes()

    assert with_b == pure_a  # 字节一致（冻结时间消除页脚时间差）
    assert fetchers.head_calls == PARTICIPANTS  # B 只发了 head 查询
    assert fetchers.compare_calls == []  # 首见记基线，零 compare、零 AI、零推送
