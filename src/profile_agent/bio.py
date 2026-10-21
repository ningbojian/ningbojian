"""AI 简介：提示词构建与 Claude 调用（含复用与回退）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import AIConfig

_SYSTEM = (
    "你是一位技术写作助手，为 GitHub 个人主页撰写中文简介。"
    "只输出简介正文，不要 markdown 标题、代码块或任何解释。"
)


class BioError(Exception):
    """简介生成失败（消息为中文）。"""


def build_prompt(payload: dict, cfg: AIConfig) -> str:
    repos_text = json.dumps(payload.get("repos", []), ensure_ascii=False, indent=2)
    return (
        f"请为下面这位开发者写一段 GitHub 个人主页简介，使用简体中文。\n"
        f"简介长度在 {cfg.bio_min_chars} 到 {cfg.bio_max_chars} 字之间，"
        f"语气自然、专业，突出技术方向与代表项目，不要夸大。\n\n"
        f"个人资料：\n{json.dumps({k: payload.get(k) for k in ('name', 'blog', 'bio', 'totals')}, ensure_ascii=False, indent=2)}\n\n"
        f"代表项目：\n{repos_text}\n"
    )


def _is_fresh(prev_generated_at: str, max_age_days: int) -> bool:
    if not prev_generated_at:
        return False
    try:
        generated = datetime.fromisoformat(prev_generated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - generated
    return age.total_seconds() < max_age_days * 86400


def generate_bio(
    payload: dict,
    cfg: AIConfig,
    *,
    input_hash: str,
    prev_hash: str,
    prev_text: str,
    prev_generated_at: str,
    client=None,
) -> str:
    """生成简介：输入未变且未过期则复用，失败则回退旧简介。"""
    if prev_text and input_hash == prev_hash and _is_fresh(prev_generated_at, cfg.max_age_days):
        return prev_text

    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    try:
        message = client.messages.create(
            model=cfg.model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": build_prompt(payload, cfg)}],
        )
    except Exception as exc:
        if prev_text:
            return prev_text
        raise BioError(f"调用 Claude 生成简介失败：{exc}") from exc

    text = (message.content or "").strip().strip('「」"\'')
    if not text:
        if prev_text:
            return prev_text
        raise BioError("Claude 返回了空简介")
    return text
