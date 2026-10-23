"""README 内置置顶勾选面板（WP6）：锚点解析、候选行构建与面板渲染。

面板是置顶配置的唯一 UI（config 里 featured.pin 仅首跑种子）：
- 区域限定解析：先按 pin-config 锚点切出子串再逐行匹配——custom 区形似
  `- [x] owner/repo` 的行绝不误收
- 行正则不设行尾锚定：行尾备注不吞掉勾选意图；坏行跳过 + 中文警告
  （面板=托管区，重建会规范化；自由文字写 custom 区）
- 候选=全部 normalize 后的公开仓库：有效置顶（按序）在前、其余精选序在后——
  取消勾选的行仍以未勾状态留在面板（可随时勾回）
"""

from __future__ import annotations

import re

PIN_START = "<!-- pin-config:start -->"
PIN_END = "<!-- pin-config:end -->"

# 勾选行：`- [x] owner/repo`（后可跟任意备注——不设 $ 行尾锚定，保勾选意图）
_LINE_RE = re.compile(r"^- \[([ xX])\] +([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)")


def parse_pin_panel(text: str, warn=None) -> list[str] | None:
    """从 README 提取置顶名单（勾选行、按文档序）。

    返回 None（回落 config 种子）：锚点缺失/不平衡/非单次成对出现。
    返回 list（可为空）：锚点平衡，勾选行即置顶名单。
    坏行（形似勾选行但不合法）跳过并经 warn 回调打中文警告。
    """
    if not text:
        return None
    if text.count(PIN_START) != 1 or text.count(PIN_END) != 1:
        return None
    body = text.split(PIN_START, 1)[1].split(PIN_END, 1)[0]
    pins: list[str] = []
    for line in body.splitlines():
        if not line.startswith("- ["):
            continue  # 面板头部/说明文字合法存在，静默略过
        m = _LINE_RE.match(line)
        if not m:
            if warn is not None:
                warn(
                    f"置顶面板有无法识别的行，已跳过（面板为托管区，重建会规范化；"
                    f"自由文字请写 custom 区）：{line[:60]}"
                )
            continue
        ticked, name = m.group(1), m.group(2)
        if ticked in ("x", "X"):
            pins.append(name)
    return pins


def panel_candidates(repos, effective_pins: list[str], featured) -> list[tuple[str, bool]]:
    """面板候选行（full_name, 是否勾选）：有效置顶按序在前，其余按精选序在后，
    最后补全集剩余（候选=全集，取消勾选的行仍留在面板可勾回）。"""
    by_name = {r.full_name for r in repos}
    rows: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for name in effective_pins:
        if name in by_name and name not in seen:
            rows.append((name, True))
            seen.add(name)
    for r in list(featured) + list(repos):
        if r.full_name in by_name and r.full_name not in seen:
            rows.append((r.full_name, False))
            seen.add(r.full_name)
    return rows


def render_pin_panel(rows: list[tuple[str, bool]], count_cap: int = 0) -> str:
    """面板 HTML（zh 文件底部 <details> 折叠区）。rows=(full_name, 是否勾选)。"""
    lines = [
        "<details>",
        "<summary><b>📌 置顶配置面板（网页直接勾选）</b></summary>",
        "",
        PIN_START,
    ]
    for name, ticked in rows:
        lines.append(f"- [{'x' if ticked else ' '}] {name}")
    lines += [
        PIN_END,
        "",
        "每项一句后果：勾选 = 进入上方 📌 置顶板块，取消勾选 = 移出板块（行仍留在本面板，可随时勾回）。",
        "在本页点右上角编辑图标勾选后 **Commit 保存**，几秒内自动生效，无需回本地运行。",
        "只改变本页展示顺序，不修改任何仓库内容、不合并任何 PR。",
    ]
    if count_cap > 0:
        lines.append(
            f"置顶数量超过首页上限（{count_cap}）时超出部分不展示，多余勾选仍然保留。"
        )
    lines += [
        "本面板为托管区（工具自动重建，请勿手改结构）；自由文字请写页面底部 custom 区。",
        "</details>",
    ]
    return "\n".join(lines)
