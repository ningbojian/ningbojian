"""WP6 README 内置置顶勾选面板：区域限定解析、候选构建、面板渲染与 cli 集成。"""

import json
import shutil

from profile_agent.pin_panel import (
    PIN_END,
    PIN_START,
    panel_candidates,
    parse_pin_panel,
    render_pin_panel,
)
from profile_agent.cli import run

from test_cli import FIXTURES, _write_config  # noqa: F401


# ============================ 解析（区域限定 + 宽松行） ============================


def test_parse_pin_panel_region_limited_ignores_custom_lookalike():
    """custom 区形似 `- [x] owner/repo` 的行绝不误收（先切区域再逐行匹配）。"""
    text = (
        "# README\n"
        "<!-- profile-agent:custom:start -->\n"
        "- [x] evil/not-a-pin\n"
        "<!-- profile-agent:custom:end -->\n"
        f"{PIN_START}\n"
        "- [x] alice/cool-tool\n"
        "- [ ] alice/old-thing\n"
        f"{PIN_END}\n"
    )
    assert parse_pin_panel(text) == ["alice/cool-tool"]


def test_parse_pin_panel_tick_order_and_trailing_note_kept():
    """勾选行按文档序返回；行尾备注不吞掉勾选意图（正则不设 $ 锚定）。"""
    text = (
        f"{PIN_START}\n"
        "- [x] alice/old-thing 我的代表作\n"
        "- [ ] alice/web-app\n"
        "- [X] alice/cool-tool\n"
        f"{PIN_END}\n"
    )
    assert parse_pin_panel(text) == ["alice/old-thing", "alice/cool-tool"]


def test_parse_pin_panel_missing_or_unbalanced_returns_none():
    """锚点缺失/不平衡 → None（回落 config 种子，由 panel_missing 负责重建）。"""
    assert parse_pin_panel("") is None
    assert parse_pin_panel("# 没有面板的 README\n") is None
    assert parse_pin_panel(f"{PIN_START}\n- [x] a/b\n") is None
    assert parse_pin_panel(
        f"{PIN_START}\n- [x] a/b\n{PIN_END}\n{PIN_START}\n- [ ] c/d\n{PIN_END}\n"
    ) is None


def test_parse_pin_panel_bad_line_skipped_with_warning():
    """坏行跳过 + 中文警告（面板=托管区，重建会规范化）。"""
    warns = []
    text = f"{PIN_START}\n- [xx] 坏行没有斜杠\n- [x] alice/cool-tool\n{PIN_END}\n"
    assert parse_pin_panel(text, warn=warns.append) == ["alice/cool-tool"]
    assert warns and "无法识别" in warns[0]


# ============================ 候选与渲染回环 ============================


class _R:
    def __init__(self, full_name):
        self.full_name = full_name


def test_panel_candidates_full_set_pins_first_unticked_remain():
    """候选=全集：置顶在前、其余精选序；取消勾选的行仍以未勾状态留在面板。"""
    repos = [_R("alice/cool-tool"), _R("alice/old-thing"), _R("alice/new-repo")]
    featured = [_R("alice/cool-tool"), _R("alice/old-thing")]
    rows = panel_candidates(repos, ["alice/old-thing"], featured)
    assert rows == [
        ("alice/old-thing", True),
        ("alice/cool-tool", False),
        ("alice/new-repo", False),
    ]


def test_render_panel_roundtrip_parse_stable():
    """渲染 → 解析回环恒等：勾选态与行序零漂移（两轮收敛的回归点）。"""
    rows = [("alice/old-thing", True), ("alice/cool-tool", False)]
    html = render_pin_panel(rows)
    assert PIN_START in html and PIN_END in html
    assert "- [x] alice/old-thing" in html and "- [ ] alice/cool-tool" in html
    assert parse_pin_panel(html) == ["alice/old-thing"]
    assert "Commit 保存" in html  # 生效时机一句话（交互文案承诺）
    assert "不修改任何仓库内容" in html  # 不会发生什么（边界文案承诺）
    assert "托管区" in html


# ============================ cli 集成 ============================


def _prepare(tmp_path):
    cfg = _write_config(tmp_path)
    fx = tmp_path / "fx"
    shutil.copytree(FIXTURES, fx)
    assert run(cfg, fixture=fx, no_ai=True) == 0
    return cfg, fx


def test_pin_tick_opens_gate_without_data_change(tmp_path):
    """勾选一行（数据零变化）→ 门开、置顶板块出现该仓库、快照记录生效名单。"""
    cfg, fx = _prepare(tmp_path)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "- [ ] alice/cool-tool" in text  # 首渲染全未勾
    readme.write_text(
        text.replace("- [ ] alice/cool-tool", "- [x] alice/cool-tool"), encoding="utf-8"
    )
    assert run(cfg, fixture=fx, no_ai=True) == 0
    out = readme.read_text(encoding="utf-8")
    assert "## 📌 置顶项目" in out
    assert "- [x] alice/cool-tool" in out  # 勾选态保持
    data = json.loads((tmp_path / "data" / "snapshot.json").read_text(encoding="utf-8"))
    assert data["pins"] == ["alice/cool-tool"]
    # 第三轮：无变化 → noop（面板行确定性排序是回归点）
    mt = readme.stat().st_mtime_ns
    assert run(cfg, fixture=fx, no_ai=True) == 0
    assert readme.stat().st_mtime_ns == mt


def test_anchor_deleted_restores_panel_via_panel_missing_with_warning(tmp_path, capsys):
    """锚点被删 → panel_missing 开门重建 + 中文警告（回落种子后重新渲染面板）。"""
    cfg, fx = _prepare(tmp_path)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = text.index(PIN_START), text.index(PIN_END) + len(PIN_END)
    readme.write_text(text[:start] + text[end:], encoding="utf-8")  # 整段删掉面板
    capsys.readouterr()
    assert run(cfg, fixture=fx, no_ai=True) == 0
    err = capsys.readouterr().err
    assert "置顶面板" in err  # 重建警告
    assert PIN_START in readme.read_text(encoding="utf-8")  # 面板已回来


def test_config_pin_seed_only_first_render(tmp_path):
    """config pin 仅首跑种子：面板存在后改 config 不再改置顶（面板是唯一 UI）。"""
    cfg = _write_config(tmp_path)
    with cfg.open("a", encoding="utf-8") as fh:
        fh.write('featured:\n  pin: ["alice/old-thing"]\n')
    fx = tmp_path / "fx"
    shutil.copytree(FIXTURES, fx)
    assert run(cfg, fixture=fx, no_ai=True) == 0
    assert "## 📌 置顶项目" in (tmp_path / "README.md").read_text(encoding="utf-8")
    # 改 config pin：面板已存在 → 解析结果优先，置顶不变
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace("alice/old-thing", "alice/cool-tool"),
        encoding="utf-8",
    )
    assert run(cfg, fixture=fx, no_ai=True) == 0
    out = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "⭐ **[old-thing](" in out  # 仍是面板决定的 old-thing
    assert "- [x] alice/old-thing" in out  # 面板勾选态与 config 无关
    assert "- [ ] alice/cool-tool" in out
