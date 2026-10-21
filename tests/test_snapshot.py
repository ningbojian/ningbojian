"""snapshot.py 读写测试。"""

from pathlib import Path

from profile_agent.models import BioInfo, Snapshot
from profile_agent.snapshot import load_snapshot, save_snapshot


def _sample() -> Snapshot:
    return Snapshot(
        schema=1,
        username="alice",
        stats_fingerprint="sha256:abc",
        totals={"public_repos": 42, "followers": 128, "total_stars": 230},
        repos=[{"full_name": "alice/cool-tool", "stars": 120}],
        bio=BioInfo(
            text="你好，我是 Alice。",
            input_hash="sha256:def",
            generated_at="2026-10-21T02:00:00+00:00",
            model="claude-opus-5-5",
            prompt_version=1,
        ),
        generated_at="2026-10-21T02:00:00+00:00",
    )


def test_roundtrip(tmp_path):
    path = tmp_path / "snapshot.json"
    save_snapshot(path, _sample())
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.username == "alice"
    assert loaded.stats_fingerprint == "sha256:abc"
    assert loaded.totals["total_stars"] == 230
    assert loaded.repos[0]["full_name"] == "alice/cool-tool"
    assert loaded.bio.text == "你好，我是 Alice。"
    assert loaded.bio.prompt_version == 1


def test_load_missing_returns_none(tmp_path):
    assert load_snapshot(tmp_path / "none.json") is None


def test_load_corrupt_returns_none(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_snapshot(path) is None


def test_creates_parent_dirs(tmp_path):
    path = tmp_path / "data" / "nested" / "snapshot.json"
    save_snapshot(path, _sample())
    assert path.exists()
