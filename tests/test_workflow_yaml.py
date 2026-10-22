"""workflow YAML 结构回归：定时间隔下拉、RESERVED 防撞名、间隔门标记（guide「控制开销」配套）。"""

from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "update-profile.yml"


def _wf() -> dict:
    # PyYAML 按 YAML 1.1 解析：裸 `on:` 的键是布尔 True 而不是字符串 "on"
    raw = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return raw.get("on") or raw.get(True)


def test_wf_schedule_interval_input_is_choice_with_8_options():
    """Run workflow 里必须有「定时运行间隔」下拉：不修改 + 每 1..7 天，且默认不修改。"""
    inputs = _wf()["workflow_dispatch"]["inputs"]
    spec = inputs["schedule_interval"]
    assert spec["type"] == "choice"
    assert spec["options"][0].startswith("不修改")
    assert spec["default"] == spec["options"][0]
    assert spec["options"][1:] == [f"每 {n} 天" for n in range(1, 8)]


def test_wf_daily_cron_with_interval_markers():
    """cron 每天唤醒；实际是否运行由 interval_days/interval_anchor 标记门决定。"""
    assert _wf()["schedule"][0]["cron"] == "23 2 * * *"
    text = WF.read_text(encoding="utf-8")
    assert "# interval_days:" in text
    assert "# interval_anchor:" in text


def test_wf_check_step_gates_on_interval_markers():
    """定时第一步（check）读标记做间隔门：未到日子输出 schedule=false 并写明原因。"""
    text = WF.read_text(encoding="utf-8")
    assert "interval_days" in text
    assert "interval_anchor" in text
    assert "非每" in text  # 跳过时的可读原因行


def test_wf_rewrite_step_only_on_dispatch_and_skips_default():
    """改写步骤仅手动触发执行；默认选项「不修改」时原样退出不改文件。"""
    text = WF.read_text(encoding="utf-8")
    assert 'if: github.event_name == \'workflow_dispatch\'' in text
    assert "不修改" in text


def test_wf_dialog_hides_projects_inputs():
    """Run workflow 对话框不再暴露任何 projects 相关输入（功能已隐式关闭）。

    对话框输入须恰好是这五个安全项，不含 update_projects / projects_repos /
    逐仓「仅项目介绍」勾选框；REPO_CHECKBOXES 标记被移除后同步步骤会自我跳过，
    不会再把勾选框注入回来。config.yaml 仍保留 projects 段（enabled: false），
    代码路径休眠但可随时重新启用。
    """
    inputs = _wf()["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "force",
        "repo_readmes",
        "wait_for_merges",
        "schedule_interval",
        "update_readme",
    }
    text = WF.read_text(encoding="utf-8")
    assert "REPO_CHECKBOXES_START" not in text  # 勾选框区块标记（移除后同步步骤自我跳过）
