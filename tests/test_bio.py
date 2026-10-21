"""bio.py 提示词构建与生成逻辑测试（假 client，无网络）。"""

from types import SimpleNamespace

import pytest

from profile_agent.bio import BioError, build_prompt, generate_bio
from profile_agent.config import AIConfig

PAYLOAD = {
    "name": "Alice Zhang",
    "blog": "https://alice.dev",
    "bio": "全栈工程师",
    "totals": {"public_repos": 42, "followers": 128},
    "repos": [
        {"name": "cool-tool", "description": "一个很酷的工具", "language": "Python", "stars": 120},
        {"name": "web-app", "description": "网页应用", "language": "JavaScript", "stars": 80},
    ],
}


def _block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


class FakeClient:
    """返回真实 SDK 形态的 content blocks；记录 create 调用。"""

    def __init__(self, blocks, raise_exc=None):
        self.calls = []
        self._blocks = blocks
        self._exc = raise_exc
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return SimpleNamespace(content=self._blocks)


def test_build_prompt_contains_zh_instructions_and_repos():
    cfg = AIConfig(prompt_version=7)
    prompt = build_prompt(PAYLOAD, cfg)
    assert "简体中文" in prompt
    assert str(cfg.bio_min_chars) in prompt
    assert str(cfg.bio_max_chars) in prompt
    assert "亮点" in prompt
    assert "cool-tool" in prompt
    assert "网页应用" in prompt
    assert "128" in prompt  # followers 注入


def test_generate_reuses_existing_recent_bio():
    cfg = AIConfig()
    client = FakeClient([_block("不应被调用")])
    text, generated = generate_bio(
        PAYLOAD,
        cfg,
        input_hash="sha256:whatever",
        prev_hash="sha256:whatever",
        prev_text="这是我已有的简介。",
        prev_generated_at="2099-01-01T00:00:00+00:00",  # 尚未过期
        client=client,
    )
    assert text == "这是我已有的简介。"
    assert generated is False
    assert client.calls == []  # 未调用 API


def test_generate_joins_text_blocks_and_strips_quotes():
    client = FakeClient(
        [
            SimpleNamespace(type="thinking", text="思考过程……"),
            _block("  「第一段简介。」  "),
            _block("第二段亮点。"),
        ]
    )
    text, generated = generate_bio(
        PAYLOAD,
        AIConfig(model="claude-opus-5-5"),
        input_hash="sha256:new",
        prev_hash="sha256:old",
        prev_text="旧简介",
        prev_generated_at="2000-01-01T00:00:00+00:00",
        client=client,
    )
    assert generated is True
    assert text == "第一段简介。\n第二段亮点。"  # 只拼 text 块（块间换行），去引号
    assert client.calls[0]["model"] == "claude-opus-5-5"
    assert client.calls[0]["max_tokens"] >= 4096
    assert client.calls[0]["messages"][0]["role"] == "user"


def test_generate_api_error_falls_back_to_previous():
    client = FakeClient([], raise_exc=RuntimeError("api down"))
    text, generated = generate_bio(
        PAYLOAD,
        AIConfig(),
        input_hash="sha256:new",
        prev_hash="sha256:old",
        prev_text="旧简介必须保留",
        prev_generated_at="2000-01-01T00:00:00+00:00",
        client=client,
    )
    assert text == "旧简介必须保留"
    assert generated is False


def test_generate_empty_response_falls_back_to_previous():
    client = FakeClient([_block("")])
    text, generated = generate_bio(
        PAYLOAD,
        AIConfig(),
        input_hash="sha256:new",
        prev_hash="sha256:old",
        prev_text="旧简介",
        prev_generated_at="2000-01-01T00:00:00+00:00",
        client=client,
    )
    assert text == "旧简介"
    assert generated is False


def test_generate_no_previous_and_error_raises():
    client = FakeClient([], raise_exc=RuntimeError("api down"))
    with pytest.raises(BioError):
        generate_bio(
            PAYLOAD,
            AIConfig(),
            input_hash="sha256:new",
            prev_hash="",
            prev_text="",
            prev_generated_at="",
            client=client,
        )
