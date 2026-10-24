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
    """Run workflow 对话框不再暴露任何 projects 相关输入（功能已彻底移除）。

    对话框输入须恰好是这五个安全项，不含 update_projects / projects_repos /
    逐仓「仅项目介绍」勾选框。有意变更（A-P0）：项目介绍功能已删除——
    config.yaml 的 projects 段、workflow 勾选框映射与点名链路一并下线。
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


def test_wf_force_and_repo_readmes_descriptions_match_semantics():
    """对话框文案与实际旗标语义一致（2026-10-23 重写：新人一眼可辨、去内部黑话）。

    force = 跳过「有变化才更新」：主页 overview 立即重写 + 全部公开仓库 README
    全量重跑开 PR；repo_readmes = 只强制各仓库 README，明确不影响主页 overview。
    两行并排时「谁含主页谁不含」字面直接可辨——不再依赖 A+B/模式 B 这类
    内部代号（用户反馈：新人看不懂、描述太长）。
    """
    inputs = _wf()["workflow_dispatch"]["inputs"]
    force_desc = inputs["force"]["description"]
    rr_desc = inputs["repo_readmes"]["description"]
    # force：必须点名主页 + 全量重跑（覆盖 A 门与 B 队列两层语义）
    assert "主页" in force_desc
    assert "全量重跑" in force_desc
    # repo_readmes：全量重跑且明确排除主页（与 force 的字面对照锚点）
    assert "全量重跑" in rr_desc
    assert "不影响主页 overview" in rr_desc
    # 去黑话：两行都不得再出现内部代号（防止文案回退成黑话）
    for desc in (force_desc, rr_desc):
        assert "A+B" not in desc
        assert "模式 B" not in desc


def test_wf_dialog_descriptions_single_line_short_and_plain():
    """对话框五条 description 均单行、短、零黑话（2026-10-23 用户反馈：太长、对新人不自解释）。

    description 即 Run workflow 里输入旁的可见文本：换行会拖成多行，超长会淹没
    其余选项；wait_for_merges 保住「不勾也行」零风险语义，update_readme 与
    default:true 一致（写明默认勾选），schedule_interval 只答「改什么、何时生效」。
    """
    inputs = _wf()["workflow_dispatch"]["inputs"]
    for spec in inputs.values():
        desc = spec["description"]
        assert "\n" not in desc  # 单行：> 折叠或显式换行都会让对话框变两行
        assert len(desc) <= 60  # 一行读完的上限
        for jargon in ("A+B", "模式 B", "增量门"):
            assert jargon not in desc
    wait_desc = inputs["wait_for_merges"]["description"]
    assert "不勾也行" in wait_desc  # 不是必选项：消除「不勾会不会漏掉」的焦虑
    assert "30 分钟" in wait_desc  # 等待窗口时长可见
    update_desc = inputs["update_readme"]["description"]
    assert "默认" in update_desc  # default:true 对应「默认勾选」
    # 跨行矛盾化解（2026-10-23 设计验证）：不勾主页时，force 行的「立即重写」也失效——
    # 引号内必须逐字引用 force 行界面上真实出现的词（不引用 UI 不显示的 input id）
    assert "『立即重写』" in update_desc
    interval_desc = inputs["schedule_interval"]["description"]
    assert "本轮结束后" in interval_desc  # 何时生效说清楚


# ---- WP8 保存即触发（push → main + README 路径过滤）----


def test_wf_push_trigger_targets_main_readme_paths():
    """WP8：README/README.en.md 保存到 main 即触发（用户选定「保存即触发」）。

    paths 只圈两个 README 文件——其余 push 不触发；
    防循环三重保险之一（bot 提交 [skip ci] + paths 过滤 + branches:[main]）。
    """
    push = _wf()["push"]  # PyYAML 解析为 dict（branches/paths 两个键，非 list 形态）
    assert push["branches"] == ["main"]
    assert push["paths"] == ["README.md", "README.en.md"]


def test_wf_steps_bypass_interval_gate_for_non_schedule():
    """WP8：push 下工作步骤穿透定时门（核验结论：两门内聚于 check 步，无需改 if）。

    工作步骤条件恒为 `!= 'schedule' || schedule=='true'`（push 下左操作数真短路）；
    仅 check 步（schedule 专属）与间隔改写步（dispatch 专属）是事件专属条件。
    不存在任何把 push 挡在门外的其他 if 形态。
    """
    raw = yaml.safe_load(WF.read_text(encoding="utf-8"))  # _wf() 只返回 on 段，jobs 在根文档
    steps = raw["jobs"]["update"]["steps"]
    allowed = {
        "github.event_name == 'schedule'",
        "github.event_name == 'workflow_dispatch'",
        "github.event_name != 'schedule' || steps.check.outputs.schedule == 'true'",
    }
    conds = [s["if"] for s in steps if s.get("if")]
    assert conds, "工作步骤不得全部无条件（定时门必须存在于 check/工作步）"
    assert [c for c in conds if c not in allowed] == []


def test_wf_git_add_includes_readme_en():
    """WP8：提交步 git add 带上 README.en.md（路径步输出 readme_en，与 cli 派生同口径）。"""
    text = WF.read_text(encoding="utf-8")
    assert 'print(f"readme_en=' in text  # 读取配置路径步输出 en 路径
    assert "steps.paths.outputs.readme_en" in text  # 提交步消费该输出
    # add 行同时含 readme 与 readme_en 两个输出（双文件一起进 main）
    add_line = next(
        line for line in text.splitlines() if "git add" in line and "outputs.readme" in line
    )
    assert "outputs.readme }}" in add_line and "outputs.readme_en }}" in add_line


def test_wf_bot_commit_keeps_skip_ci():
    """WP8：bot 提交保留 [skip ci]（防 push 触发自循环的第一道保险）。

    有意变更（A-P0）：项目介绍 PR 提交随审核流移除，工作流只剩直提 main 一个提交。
    """
    text = WF.read_text(encoding="utf-8")
    assert 'git commit -m "chore: 自动更新 Profile README [skip ci]"' in text


def test_wf_has_no_projects_or_named_repo_traces():
    """反向锁（A-P0）：yml 全文不得再出现项目介绍/点名仓库链路的任何痕迹。"""
    text = WF.read_text(encoding="utf-8")
    for token in ("docs/projects", "--repos", "repo_inputs", "项目介绍", "steps.resolve"):
        assert token not in text, f"workflow 残留项目介绍痕迹：{token}"
