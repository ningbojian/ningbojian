"""snapshot.py 读写测试。"""

import json
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


def test_roundtrip_includes_config_hash(tmp_path):
    snap = _sample()
    snap.stats_config_hash = "sha256:cfg"
    path = tmp_path / "s.json"
    save_snapshot(path, snap)
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.stats_config_hash == "sha256:cfg"


def test_load_non_dict_json_returns_none(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("[]", encoding="utf-8")
    assert load_snapshot(path) is None


# ---- schema 3 与 repo_readmes（模式 B，测试计划 SB01-SB04）----


def test_schema2_upgrades_to_3_with_empty_repo_readmes(tmp_path):
    """SB01：schema 2 旧快照读入自动升级并补空 repo_readmes，旧字段原样保留。

    有意变更（schema 4 双语/面板/三路合并）：升级目标由 3 改为 4。
    """
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "username": "alice",
                "stats_fingerprint": "sha256:abc",
                "bio": {"text": "旧简介", "input_hash": "sha256:def"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.schema == 4
    assert loaded.repo_readmes == {}
    assert loaded.username == "alice"
    assert loaded.bio.text == "旧简介"
    # 二次往返后仍 schema=4 且含 "repo_readmes": {}
    save_snapshot(path, loaded)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == 4
    assert data["repo_readmes"] == {}


def test_schema1_upgrades_to_3(tmp_path):
    """SB02：schema 1 快照同样兼容读入。

    有意变更（schema 4 双语/面板/三路合并）：升级目标由 3 改为 4。
    """
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"schema": 1, "username": "alice", "stats_fingerprint": "sha256:abc"}),
        encoding="utf-8",
    )
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.schema == 4
    assert loaded.repo_readmes == {}
    assert loaded.stats_fingerprint == "sha256:abc"


def test_repo_readmes_full_field_roundtrip(tmp_path):
    """SB03：repo_readmes 全字段往返（含 last_input_hash 与 pending，逐仓独立）。"""
    snap = _sample()
    snap.repo_readmes = {
        "alice/cool-tool": {
            "sha": "abc123",
            "block_hash": "sha256:b1",
            "mode": "block",
            "failed_hash": "",
            "last_input_hash": "sha256:i1",
            "pending": False,
            "updated_at": "2026-10-22T00:00:00+00:00",
        },
        "alice/old-thing": {
            "sha": "def456",
            "block_hash": "",
            "mode": "full",
            "failed_hash": "sha256:f1",
            "last_input_hash": "",
            "pending": True,
            "updated_at": "2026-10-22T01:00:00+00:00",
        },
    }
    path = tmp_path / "s.json"
    save_snapshot(path, snap)
    loaded = load_snapshot(path)
    assert loaded is not None
    cool = loaded.repo_readmes["alice/cool-tool"]
    assert cool["sha"] == "abc123"
    assert cool["mode"] == "block"
    assert cool["last_input_hash"] == "sha256:i1"
    assert cool["pending"] is False
    old = loaded.repo_readmes["alice/old-thing"]
    assert old["mode"] == "full"
    assert old["failed_hash"] == "sha256:f1"
    assert old["pending"] is True


def test_malformed_repo_readme_entry_fills_defaults(tmp_path):
    """SB04：残缺条目读入补缺省不崩溃。"""
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "schema": 3,
                "username": "alice",
                "repo_readmes": {"alice/x": {"sha": "abc", "updated_at": "t"}},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_snapshot(path)
    assert loaded is not None
    entry = loaded.repo_readmes["alice/x"]
    assert entry["sha"] == "abc"
    assert entry["pending"] is False
    assert entry["last_input_hash"] == ""
    assert entry["failed_hash"] == ""
    assert entry["mode"] == "block"


def test_snapshot_schema4_roundtrip_pins_and_bio_en(tmp_path):
    """schema 4：新增 pins（生效置顶名单）、bio.text_en（英文简介）、
    readme_last（上次写入内容，三路合并 base）——保存后读回逐字段一致。"""
    snap = Snapshot(
        schema=4,
        username="alice",
        pins=["alice/cool-tool", "alice/web-app"],
        bio=BioInfo(text="你好。", text_en="Hi.", input_hash="sha256:x"),
        readme_last="# 上次写入的 README\n",
    )
    p = tmp_path / "snapshot.json"
    save_snapshot(p, snap)
    got = load_snapshot(p)
    assert got is not None
    assert got.schema == 4
    assert got.pins == ["alice/cool-tool", "alice/web-app"]
    assert got.bio.text_en == "Hi."
    assert got.readme_last == "# 上次写入的 README\n"


def test_schema3_upgrades_to_4(tmp_path):
    """旧快照（schema 3、无新字段）读入自动升级：schema=4、新字段空缺省。"""
    old = {
        "schema": 3,
        "username": "alice",
        "stats_fingerprint": "sha256:abc",
        "repos": [],
        "bio": {"text": "你好。", "input_hash": "h", "generated_at": "", "model": "", "prompt_version": 1},
        "repo_readmes": {},
        "generated_at": "",
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    got = load_snapshot(p)
    assert got is not None
    assert got.schema == 4
    assert got.pins == []
    assert got.bio.text_en == ""
    assert got.readme_last == ""
