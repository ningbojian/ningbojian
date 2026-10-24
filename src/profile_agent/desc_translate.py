"""仓库描述批量英译（A-WP-B1）：英文版 README 里含中文的 description 换成 AI 英译。

- contains_cjk 只认 Han（基本区 + 扩展A）：纯假名/纯 ASCII 不译（零回归裁定）
- 全量目标一次 chat_text 调用（单批单请求），JSON map 宽松解析（仿 bio._parse_dual）
- 失败/解析失败 → ({}, 中文警告含「沿用原文"])：调用方回落原文且不写缓存，下轮开门自动重试
"""

from __future__ import annotations

import json
import re

from .bio import chat_text
from .config import AIConfig

# Han 基本区（一-鿿）+ 扩展A（㐀-䶿）；不含假名/谚文（不译非中文语言，零回归）
_HAN_RE = re.compile("[一-鿿㐀-䶿]")

_SYSTEM = (
    "你是一位技术翻译助手，负责把 GitHub 仓库的中文简介翻译成自然地道的英文。"
    "只输出 JSON，不要代码块围栏或任何解释。"
)


def contains_cjk(text: str) -> bool:
    """描述是否含汉字（基本区或扩展A）；纯 ASCII/假名等返回 False。"""
    return bool(text) and bool(_HAN_RE.search(text))


def _parse_desc_map(raw: str) -> dict[str, str] | None:
    """从模型输出提取 {full_name: 英文译文}；非法 → None（调用方降级原文）。

    宽松解析：容忍 ```json 围栏与前后杂文，取首个 { 到末个 } 之间的片段
    （同 bio._parse_dual 的宽容口径）；值须为非空字符串，否则剔除。
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            return None  # 值类型不对 = 整体不合法（防误把非 map 当结果）
        v = v.strip()
        if v:
            out[str(k).strip()] = v  # 空值剔除（模型偶发给空串 → 视为漏译回落原文）
    return out


def build_desc_translate_prompt(items: list[tuple[str, str]]) -> str:
    """批量翻译提示词：items=[(full_name, 中文描述)]；只输出 JSON map。"""
    payload = [{"full_name": fn, "description": desc} for fn, desc in items]
    return (
        "把下面每个仓库的中文简介翻译成自然地道的英文，用作 GitHub 个人主页的仓库描述。\n"
        "要求：忠实原意、不扩写、每条压成单行（不许换行）、不要引号包裹整句；"
        "保留必要的专有名词与命令原文。\n"
        "只输出一个 JSON 对象，形如：\n"
        '{"full_name": "English description"}\n'
        "每个仓库都要有条目，键必须与输入的 full_name 完全一致；"
        "不要输出 JSON 之外的任何文字或代码块围栏。\n\n"
        f"仓库列表：\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def translate_descriptions(
    items: list[tuple[str, str]],
    cfg: AIConfig,
    *,
    client=None,
    http_post=None,
) -> tuple[dict[str, str], str]:
    """批量英译（单批一次调用）。返回 (译文 map, 警告)。

    - 空 items → ({}, "")，不发起调用
    - AI 异常/解析失败 → ({}, 中文警告含「沿用原文"])：不写缓存，下轮自动重试
    - 模型漏译的仓库不进返回（调用方回落原文），警告点名缺失者
    - 译文压成单行（\\n → 空格）——README 描述必须单行
    """
    if not items:
        return {}, ""
    names = [fn for fn, _ in items]
    try:
        raw = chat_text(
            cfg, _SYSTEM, build_desc_translate_prompt(items), client=client, http_post=http_post
        )
        parsed = _parse_desc_map(raw)
    except Exception as exc:  # AI 层任何失败都不影响任务（回落原文）
        msg = str(exc)[:120]
        return {}, (
            f"仓库描述英译失败（沿用原文）：{msg}；涉及 {len(items)} 个仓库"
            f"（{', '.join(names[:5])}{' 等' if len(names) > 5 else ''}）"
        )
    if parsed is None:
        return {}, f"仓库描述英译输出无法解析（沿用原文）；涉及 {len(items)} 个仓库"
    out: dict[str, str] = {}
    for fn in names:
        translated = parsed.get(fn)
        if translated:
            out[fn] = re.sub(r"\s*\n\s*", " ", translated).strip()
    missing = [fn for fn in names if fn not in out]
    warn = ""
    if missing:
        warn = (
            f"警告：{len(missing)} 个仓库的描述英译缺失（沿用原文）："
            f"{', '.join(missing[:5])}{' 等' if len(missing) > 5 else ''}"
        )
    return out, warn
