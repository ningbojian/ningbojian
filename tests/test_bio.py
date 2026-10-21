"""bio.py 提示词构建与生成逻辑测试（假 client，无网络）。"""

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


def test_build_prompt_contains_zh_instructions_and_repos():
    cfg = AIConfig(prompt_version=7)
    prompt = build_prompt(PAYLOAD, cfg)
    assert "简体中文" in prompt
    assert str(cfg.bio_min_chars) in prompt
    assert str(cfg.bio_max_chars) in prompt
    assert "cool-tool" in prompt
    assert "网页应用" in prompt
    assert "128" in prompt  # followers 注入


def test_generate_reuses_existing_recent_bio():
    cfg = AIConfig()
    prev = "这是我已有的简介。"
    text = generate_bio(
        PAYLOAD,
        cfg,
        input_hash="sha256:whatever",
        prev_hash="sha256:whatever",
        prev_text=prev,
        prev_generated_at="2099-01-01T00:00:00+00:00",  # 尚未过期
        client=object(),  # 不应被使用
    )
    assert text == prev


def test_generate_calls_api_when_stale():
    class FakeMessage:
        def __init__(self, content):
            self.content = content

    class FakeMessages:
        def __init__(self, content):
            self._content = content

        def create(self, **kwargs):
            # 校验模型与消息结构
            assert kwargs["model"]
            assert kwargs["messages"][0]["role"] == "user"
            return FakeMessage(self._content)

    class FakeClient:
        def __init__(self, content):
            self.messages = FakeMessages(content)

    text = generate_bio(
        PAYLOAD,
        AIConfig(model="claude-opus-5-5"),
        input_hash="sha256:new",
        prev_hash="sha256:old",
        prev_text="旧简介",
        prev_generated_at="2000-01-01T00:00:00+00:00",
        client=FakeClient("  「这是新生成的简介正文」  "),
    )
    assert text == "这是新生成的简介正文"  # 去掉首尾空白与引号


def test_generate_api_error_falls_back_to_previous():
    class FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("api down")

    class FakeClient:
        messages = FakeMessages()

    text = generate_bio(
        PAYLOAD,
        AIConfig(),
        input_hash="sha256:new",
        prev_hash="sha256:old",
        prev_text="旧简介必须保留",
        prev_generated_at="2000-01-01T00:00:00+00:00",
        client=FakeClient(),
    )
    assert text == "旧简介必须保留"


def test_generate_no_previous_and_error_raises():
    class FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("api down")

    class FakeClient:
        messages = FakeMessages()

    with pytest.raises(BioError):
        generate_bio(
            PAYLOAD,
            AIConfig(),
            input_hash="sha256:new",
            prev_hash="",
            prev_text="",
            prev_generated_at="",
            client=FakeClient(),
        )
