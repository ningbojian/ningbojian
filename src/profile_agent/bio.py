"""AI 简介：提示词构建与 Claude 调用（含复用与回退）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import AIConfig

_SYSTEM = (
    "你是一位技术写作助手，为 GitHub 个人主页撰写中文简介。"
    "只输出简介正文，不要 markdown 标题、代码块或任何解释。"
)


def chat_text(
    cfg: AIConfig,
    system: str,
    user_content: str,
    *,
    client=None,
    http_post=None,
) -> str:
    """按 provider 调用模型，返回原始回复文本。

    - anthropic：官方 SDK（默认）
    - openai：OpenAI 兼容 /chat/completions（DeepSeek/千问/Kimi/MiMo/Ollama 等）
    """
    if cfg.provider == "openai":
        import os

        import requests

        post = http_post or requests.post
        key = os.environ.get(cfg.key_env_name) or ""
        resp = post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=180,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"] or "")

    if client is None:
        import os

        import anthropic

        # base_url/key_env 可指向 Anthropic 兼容端点（如 MiMo 的 /anthropic 接口）
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        key = os.environ.get(cfg.key_env_name)
        if key:
            kwargs["api_key"] = key
        client = anthropic.Anthropic(**kwargs)
    message = client.messages.create(
        model=cfg.model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return extract_text(message.content)


class BioError(Exception):
    """简介生成失败（消息为中文）。"""


def build_prompt(payload: dict, cfg: AIConfig) -> str:
    repos_text = json.dumps(payload.get("repos", []), ensure_ascii=False, indent=2)
    return (
        f"请为下面这位开发者写一段 GitHub 个人主页简介，使用简体中文。\n"
        f"简介长度在 {cfg.bio_min_chars} 到 {cfg.bio_max_chars} 字之间，"
        f"语气自然、专业，突出技术方向与代表项目，不要夸大。\n"
        f"在简介末尾另起几行，以“亮点：”开头，给出 3 条以内的要点，"
        f"每条以“- ”开头、不超过 30 字，只写可验证的事实。\n\n"
        f"个人资料：\n{json.dumps({k: payload.get(k) for k in ('name', 'blog', 'bio', 'totals')}, ensure_ascii=False, indent=2)}\n\n"
        f"代表项目：\n{repos_text}\n"
    )


def extract_text(content) -> str:
    """从真实 SDK 的 content blocks 中提取文本（忽略 thinking 等块）。

    每个 text 块单独去空白与包裹引号，块之间换行拼接。
    """
    if isinstance(content, str):
        return content.strip().strip('「」"\'')
    parts = [
        getattr(block, "text", "").strip().strip('「」"\'')
        for block in (content or [])
        if getattr(block, "type", None) == "text"
    ]
    return "\n".join(p for p in parts if p)


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
    http_post=None,
) -> tuple[str, bool]:
    """生成简介。返回 (text, generated)。

    - 输入未变且未过期：复用旧简介，generated=False
    - 调用失败/返回空：回退旧简介（若有），generated=False；否则抛 BioError
    - generated=True 时调用方才能把 input_hash 记为当前值
    """
    if prev_text and input_hash == prev_hash and _is_fresh(prev_generated_at, cfg.max_age_days):
        return prev_text, False

    try:
        raw = chat_text(
            cfg, _SYSTEM, build_prompt(payload, cfg), client=client, http_post=http_post
        )
    except Exception as exc:
        if prev_text:
            return prev_text, False
        raise BioError(f"调用模型生成简介失败（{cfg.provider}）：{exc}") from exc

    text = raw.strip().strip('「」"\'')
    if not text:
        if prev_text:
            return prev_text, False
        raise BioError("模型返回了空简介")
    return text, True
