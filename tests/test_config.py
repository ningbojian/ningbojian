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
    assert cfg.featured.count == 6
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
    assert cfg.readme.cards.theme == "github_light"
    assert cfg.readme.cards.show == ["stats"]
    assert cfg.ai.model == "claude-haiku-5-5"
    assert cfg.ai.prompt_version == 2


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
