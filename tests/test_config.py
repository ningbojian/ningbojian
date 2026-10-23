"""config.py 加载与校验测试。"""

from pathlib import Path

import pytest

from profile_agent.config import ConfigError, load_config


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_minimal_config_uses_defaults(tmp_path):
    path = _write(tmp_path, 'github:\n  username: "alice"\n')
    cfg = load_config(path)
    assert cfg.github.username == "alice"
    assert cfg.schedule.enabled is True
    assert cfg.repos.exclude_forks is True
    assert cfg.repos.exclude == []
    assert cfg.featured.count == 0  # 默认展示全部仓库
    assert cfg.featured.recency_days == 0  # 默认不限推送时间
    assert cfg.featured.pin == []  # 默认无置顶
    assert cfg.projects.featured_only is False  # 默认全部仓库参与介绍生成
    assert cfg.readme.template == "templates/profile.md.j2"
    assert cfg.ai.enabled is True
    assert cfg.ai.model == "claude-opus-5-5"
    assert cfg.snapshot.path == "data/snapshot.json"


def test_empty_username_raises_chinese_error(tmp_path):
    path = _write(tmp_path, 'github:\n  username: ""\n')
    with pytest.raises(ConfigError, match="用户名"):
        load_config(path)


def test_missing_username_key_raises(tmp_path):
    path = _write(tmp_path, "repos:\n  exclude_forks: true\n")
    with pytest.raises(ConfigError, match="用户名"):
        load_config(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="找不到"):
        load_config(tmp_path / "nope.yaml")


def test_full_config_values_respected(tmp_path):
    path = _write(
        tmp_path,
        """
schedule:
  enabled: false
github:
  username: "bob"
repos:
  exclude_forks: false
  exclude: ["bob/bob"]
featured:
  count: 3
  sort_by: "stars"
  pin: ["bob/old-repo", "bob/app"]
readme:
  cards:
    theme: "github_light"
    show: ["stats"]
ai:
  model: "claude-haiku-5-5"
  prompt_version: 2
""",
    )
    cfg = load_config(path)
    assert cfg.schedule.enabled is False
    assert cfg.repos.exclude_forks is False
    assert cfg.repos.exclude == ["bob/bob"]
    assert cfg.featured.count == 3
    assert cfg.featured.sort_by == "stars"
    assert cfg.featured.pin == ["bob/old-repo", "bob/app"]  # 置顶名单：解析、保序
    assert cfg.readme.cards.theme == "github_light"
    assert cfg.readme.cards.show == ["stats"]
    assert cfg.ai.model == "claude-haiku-5-5"
    assert cfg.ai.prompt_version == 2


def test_featured_pin_must_be_list(tmp_path):
    """置顶名单必须是列表——写成字符串直接中文报错（仿 include/exclude 校验先例）。"""
    path = _write(
        tmp_path, 'github:\n  username: "alice"\nfeatured:\n  pin: "cool-tool"\n'
    )
    with pytest.raises(ConfigError, match="featured.pin 必须是列表"):
        load_config(path)


def test_invalid_sort_by_raises(tmp_path):
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nfeatured:\n  sort_by: "magic"\n',
    )
    with pytest.raises(ConfigError, match="sort_by"):
        load_config(path)


def test_invalid_card_name_raises(tmp_path):
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nreadme:\n  cards:\n    show: ["stats", "pie"]\n',
    )
    with pytest.raises(ConfigError, match="pie"):
        load_config(path)


def test_fallback_username_used_when_empty(tmp_path):
    path = _write(tmp_path, 'github:\n  username: ""\n')
    cfg = load_config(path, fallback_username="repo-owner")
    assert cfg.github.username == "repo-owner"


def test_fallback_username_ignored_when_set(tmp_path):
    path = _write(tmp_path, 'github:\n  username: "alice"\n')
    cfg = load_config(path, fallback_username="other")
    assert cfg.github.username == "alice"


def test_ai_provider_openai_fields(tmp_path):
    path = _write(
        tmp_path,
        """
github:
  username: "a"
ai:
  provider: "openai"
  base_url: "https://api.deepseek.com"
  key_env: "DEEPSEEK_API_KEY"
  model: "deepseek-chat"
""",
    )
    cfg = load_config(path)
    assert cfg.ai.provider == "openai"
    assert cfg.ai.base_url == "https://api.deepseek.com"
    assert cfg.ai.key_env == "DEEPSEEK_API_KEY"
    assert cfg.ai.model == "deepseek-chat"


def test_ai_invalid_provider_raises(tmp_path):
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nai:\n  provider: "bogus"\n',
    )
    with pytest.raises(ConfigError, match="provider"):
        load_config(path)


def test_ai_fill_empty_descriptions_default_on(tmp_path):
    path = _write(tmp_path, 'github:\n  username: "a"\n')
    assert load_config(path).ai.fill_empty_descriptions is True


def test_ai_fill_empty_descriptions_can_disable(tmp_path):
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nai:\n  fill_empty_descriptions: false\n',
    )
    assert load_config(path).ai.fill_empty_descriptions is False


def test_readme_visitors_badge_default_off(tmp_path):
    path = _write(tmp_path, 'github:\n  username: "a"\n')
    assert load_config(path).readme.visitors_badge is False


def test_readme_visitors_badge_can_enable(tmp_path):
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nreadme:\n  visitors_badge: true\n',
    )
    assert load_config(path).readme.visitors_badge is True


# ---- repo_readmes 配置段（模式 B，测试计划 Q14-Q16）----


def test_repo_readmes_defaults_off(tmp_path):
    """Q14：配置缺省时模式 B 关闭，且各项取设计默认值。"""
    path = _write(tmp_path, 'github:\n  username: "a"\n')
    rr = load_config(path).repo_readmes
    assert rr.enabled is False
    assert rr.include == []
    assert rr.exclude == []
    assert rr.max_diff_chars == 6000
    assert rr.prompt_version == 1
    assert rr.pr_branch == "readme-auto/update"


def test_repo_readmes_full_values_respected(tmp_path):
    """Q15：六项字段完整解析。"""
    path = _write(
        tmp_path,
        """
github:
  username: "a"
repo_readmes:
  enabled: true
  include: ["cool-tool"]
  exclude: ["old-thing"]
  max_diff_chars: 4000
  prompt_version: 2
  pr_branch: "feat/readme-bot"
""",
    )
    rr = load_config(path).repo_readmes
    assert rr.enabled is True
    assert rr.include == ["cool-tool"]
    assert rr.exclude == ["old-thing"]
    assert rr.max_diff_chars == 4000
    assert rr.prompt_version == 2
    assert rr.pr_branch == "feat/readme-bot"


def test_repo_readmes_include_must_be_list(tmp_path):
    """Q16：include 写成字符串时报中文配置错误（镜像 projects.include 先例）。"""
    path = _write(
        tmp_path,
        'github:\n  username: "a"\nrepo_readmes:\n  include: "cool-tool"\n',
    )
    with pytest.raises(ConfigError, match="include"):
        load_config(path)


def test_readme_bilingual_defaults_true(tmp_path):
    """双语开关：默认开启；config.yaml 可显式关掉（一键回退单文件）。"""
    path = _write(tmp_path, 'github:\n  username: "alice"\n')
    assert load_config(path).readme.bilingual is True
    path2 = _write(
        tmp_path, 'github:\n  username: "alice"\nreadme:\n  bilingual: false\n'
    )
    assert load_config(path2).readme.bilingual is False


def test_ai_language_only_zh_cn_accepted(tmp_path):
    """ai.language 转正为「主语言」：仅接受 zh-CN（双语输出由 bilingual 开关控制）。"""
    path = _write(tmp_path, 'github:\n  username: "alice"\n')
    assert load_config(path).ai.language == "zh-CN"  # 默认合法
    path_en = _write(
        tmp_path, 'github:\n  username: "alice"\nai:\n  language: "en"\n'
    )
    with pytest.raises(ConfigError, match="zh-CN"):
        load_config(path_en)
