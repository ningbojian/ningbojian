"""repo_readmes_pr.py 测试（测试计划 GP01-GP17，git-data 推送与 PR 流，全离线）。

设计 §5.5：blob→tree→commit→ref→PR 全 API、同仓单条 open PR（force-push 刷新）、
标题带短名、body 三结局警示 + marker 说明 + commit 范围、合并检测推进到 head SHA（§12-R10）、
永不调用合并/关闭接口（合并永远由人执行）。
"""

from fake_github import FakeHttp, FakeResponse

from profile_agent.github_client import GitHubClient
from profile_agent.repo_readmes import QueueItem
from profile_agent.repo_readmes_ai import ProcessResult
from profile_agent.repo_readmes_pr import (
    PR_BRANCH,
    advance_baseline_from_merged_pr,
    build_pr_body,
    build_pr_title,
    open_or_refresh_pr,
    push_results,
    read_branch_block_hash,
)

API = "https://api.github.com"
FULL = "alice/cool-tool"
REPO_URL = f"{API}/repos/alice/cool-tool"


def _result(**kw) -> ProcessResult:
    base = dict(
        full_name=FULL,
        status="generated",
        input_hash="sha256:abc",
        base_sha="base1234567",
        head_sha="def4567890",
        content="# 标题\n托管区正文\n",
        commits=[{"sha": "def4567890", "message": "feat: 新增 add 函数"}],
        files=[{"filename": "src/core.py", "patch": "+def add(a, b)"}],
    )
    base.update(kw)
    return ProcessResult(**base)


def _client(http: FakeHttp) -> GitHubClient:
    return GitHubClient("p-pat", session=http)


def _happy_gitdata(http: FakeHttp, *, ref_exists=False):
    """预置 git-data 五连与 pulls 响应。"""
    if ref_exists:
        http.add("GET", f"{REPO_URL}/git/ref/heads/readme-auto/update",
                 FakeResponse(json_data={"object": {"sha": "oldref00"}}))
        http.add("PATCH", f"{REPO_URL}/git/refs/heads/readme-auto/update",
                 FakeResponse(json_data={"object": {"sha": "commit1"}}))
    else:
        http.add("GET", f"{REPO_URL}/git/ref/heads/readme-auto/update",
                 FakeResponse(status=404, text="not found"))
        http.add("POST", f"{REPO_URL}/git/refs",
                 FakeResponse(status=201, json_data={"ref": "refs/heads/readme-auto/update"}))
    http.add("POST", f"{REPO_URL}/git/blobs", FakeResponse(status=201, json_data={"sha": "blob1"}))
    http.add("POST", f"{REPO_URL}/git/trees", FakeResponse(status=201, json_data={"sha": "tree1"}))
    http.add("POST", f"{REPO_URL}/git/commits", FakeResponse(status=201, json_data={"sha": "commit1"}))


def _open_pr_check(http: FakeHttp, prs: list):
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=open&head=alice:readme-auto/update&base=main",
        FakeResponse(json_data=prs),
    )


# ---- GP01：git-data 调用序列与载荷 ----


def test_push_sequence_blob_tree_commit_ref_pr_and_payloads():
    """GP01：按 blob→tree→commit→ref→PR 顺序执行且载荷正确；全程 api.github.com。"""
    http = FakeHttp()
    _open_pr_check(http, [])
    _happy_gitdata(http)
    http.add("POST", f"{REPO_URL}/pulls",
             FakeResponse(status=201, json_data={"number": 42, "html_url": "https://x/42"}))
    res = open_or_refresh_pr(
        _client(http),
        full_name=FULL,
        content="# 标题\n托管区正文\n",
        head_sha="def4567890",
        title=build_pr_title(FULL),
        body=build_pr_body(commits=[{"sha": "def4567890"}], base_sha="base1234567", head_sha="def4567890"),
    )
    assert (res.number, res.html_url, res.refreshed) == (42, "https://x/42", False)
    posts = [r for r in http.writes() if r["method"] == "POST"]
    assert [u for _, u in [(r["method"], r["url"]) for r in posts]] == [
        f"{REPO_URL}/git/blobs",
        f"{REPO_URL}/git/trees",
        f"{REPO_URL}/git/commits",
        f"{REPO_URL}/git/refs",
        f"{REPO_URL}/pulls",
    ]
    blob, tree, commit, ref, pr = posts
    assert blob["json"] == {"content": "# 标题\n托管区正文\n", "encoding": "utf-8"}
    assert tree["json"]["base_tree"] == "def4567890"  # 默认分支 HEAD
    assert tree["json"]["tree"] == [
        {"path": "README.md", "mode": "100644", "type": "blob", "sha": "blob1"}
    ]
    assert commit["json"]["parents"] == ["def4567890"]  # 基线侧 HEAD
    assert ref["json"]["ref"] == "refs/heads/readme-auto/update"
    assert ref["json"]["sha"] == "commit1"
    assert pr["json"]["head"] == "readme-auto/update" and pr["json"]["base"] == "main"
    assert all(r["url"].startswith(API) for r in http.requests)  # 无本地 git，纯 HTTP
    assert all(r["headers"]["Authorization"] == "Bearer p-pat" for r in http.requests)


# ---- GP02/GP03/GP04：同仓刷新与 PR 文案 ----


def test_open_pr_force_pushes_and_edits_same_pr():
    """GP02：已有 open PR → force-push 刷新同一条 + 编辑 body，不新开。"""
    http = FakeHttp()
    _open_pr_check(http, [{"number": 42, "html_url": "https://x/42"}])
    _happy_gitdata(http, ref_exists=True)
    http.add("PATCH", f"{REPO_URL}/pulls/42", FakeResponse(json_data={"number": 42}))
    body = build_pr_body(
        commits=[{"sha": "base1234567"}, {"sha": "def4567890"}],
        base_sha="base1234567",
        head_sha="def4567890",
    )
    res = open_or_refresh_pr(
        _client(http),
        full_name=FULL,
        content="x\n",
        head_sha="def4567890",
        title=build_pr_title(FULL),
        body=body,
    )
    assert res.number == 42 and res.refreshed is True
    assert not http.has("POST", "/pulls")  # 不新开
    ref_patch = [r for r in http.writes() if r["url"].endswith("/git/refs/heads/readme-auto/update")][0]
    assert ref_patch["json"] == {"sha": "commit1", "force": True}
    pr_edit = [r for r in http.writes() if r["url"].endswith("/pulls/42")][0]
    assert "def4567" in pr_edit["json"]["body"]  # 新短 SHA 已进 body
    assert "关闭本 PR = 拒绝这批文案" in pr_edit["json"]["body"]  # 三结局警示仍在


def test_title_carries_repo_short_name():
    """GP03：标题 docs(短名): README 自动更新（待审核）——多标签页靠标题分辨。"""
    assert build_pr_title("ningbojian/shiyuan") == "docs(shiyuan): README 自动更新（待审核）"


def test_body_has_three_outcomes_marker_note_and_commit_range():
    """GP04：body 首行三结局警示、marker 说明、commit 范围与短 SHA 列表。"""
    body = build_pr_body(
        commits=[{"sha": "c111111a00000000000000000000000000000001"}, {"sha": "d222222b00000000000000000000000000000002"}],
        base_sha="c111111a00000000000000000000000000000001",
        head_sha="d222222b00000000000000000000000000000002",
    )
    first = next(line for line in body.splitlines() if line.strip())
    assert "关闭本 PR = 拒绝这批文案" in first
    assert "先不处理" in first and "合并前请重读 diff" in first
    assert "profile-agent:readme" in body  # marker 说明段
    assert "HTML 注释" in body and "渲染页不可见" in body
    assert "删掉区间 = 放弃" in body
    assert "c111111a..d222222b" in body  # base..head 范围（短 SHA 取 [:8]，与全库口径一致）
    assert "c111111a" in body and "d222222b" in body  # 短 SHA 列表


# ---- GP05-GP12：抑制、静默、重开（push_results 层）----


def test_cached_results_produce_zero_writes():
    """GP05/GP09/GP12：缓存命中（closed-unmerged 同哈希 / 分支一致 / squash 重放）→ 零写请求。"""
    http = FakeHttp()
    res = push_results(
        _client(http),
        [_result(status="cached")],
        now=None,
    )
    assert res == []
    assert http.writes() == []  # 连推送、连 PATCH pulls 都没有（Last Update 不动）
    assert http.requests == []  # 读请求也没有：抑制判定不依赖 PR 状态查询（§5.1）


def test_new_batch_reopens_pr_with_full_commit_range():
    """GP06：新提交改变哈希 → 作为新批次重开；body 带被拒批次+新提交短 SHA（刷新即全量）。"""
    http = FakeHttp()
    _open_pr_check(http, [])  # closed-unmerged 后无 open PR
    _happy_gitdata(http)
    http.add("POST", f"{REPO_URL}/pulls",
             FakeResponse(status=201, json_data={"number": 43, "html_url": "https://x/43"}))
    res = push_results(
        _client(http),
        [_result(commits=[{"sha": "old00001"}, {"sha": "new00002"}])],
        now=None,
    )
    assert [r.number for r in res] == [43]
    pr_post = [r for r in http.writes() if r["url"].endswith("/pulls")][0]
    assert "old00001" in pr_post["json"]["body"] and "new00002" in pr_post["json"]["body"]


def test_push_is_per_repo_independent():
    """GP08：一仓被抑制（cached）不影响另一仓完整推送。"""
    http = FakeHttp()
    other = f"{API}/repos/alice/old-thing"
    http.add("GET", f"{other}/pulls?state=open&head=alice:readme-auto/update&base=main",
             FakeResponse(json_data=[]))
    http.add("GET", f"{other}/git/ref/heads/readme-auto/update", FakeResponse(status=404))
    http.add("POST", f"{other}/git/blobs", FakeResponse(status=201, json_data={"sha": "b2"}))
    http.add("POST", f"{other}/git/trees", FakeResponse(status=201, json_data={"sha": "t2"}))
    http.add("POST", f"{other}/git/commits", FakeResponse(status=201, json_data={"sha": "c2"}))
    http.add("POST", f"{other}/git/refs", FakeResponse(status=201, json_data={}))
    http.add("POST", f"{other}/pulls", FakeResponse(status=201, json_data={"number": 44, "html_url": "u"}))
    res = push_results(
        _client(http),
        [_result(status="cached"), _result(full_name="alice/old-thing")],
        now=None,
    )
    assert [r.number for r in res] == [44]
    # 被抑制仓（cool-tool）零请求；写请求全部指向 old-thing
    assert all("/repos/alice/old-thing/" in r["url"] for r in http.writes())


def test_force_generated_result_pushes_even_after_closed_batch():
    """GP11：force 重新生成的结果照常推送（抑制只拦 cached，不拦 generated）。"""
    http = FakeHttp()
    _open_pr_check(http, [])
    _happy_gitdata(http)
    http.add("POST", f"{REPO_URL}/pulls",
             FakeResponse(status=201, json_data={"number": 45, "html_url": "https://x/45"}))
    res = push_results(_client(http), [_result(status="generated")], now=None)
    assert [r.number for r in res] == [45]


# ---- GP10：分支漂移检测 ----


def test_branch_drift_detection_via_block_hash():
    """GP10：分支内容被改动 → read_branch_block_hash 与缓存 block_hash 不一致（重推信号）。"""
    import base64

    from profile_agent.readme_block import END, START

    drifted = f"# 标题\n{START}\n人工改过的托管区\n{END}\n"
    http = FakeHttp()
    http.add(
        "GET",
        f"{REPO_URL}/contents/README.md?ref=readme-auto/update",
        FakeResponse(json_data={
            "content": base64.b64encode(drifted.encode("utf-8")).decode("ascii"),
            "encoding": "base64",
        }),
    )
    h = read_branch_block_hash(_client(http), FULL, PR_BRANCH)
    assert h.startswith("sha256:") and h != "sha256:缓存值"
    # 与缓存同值 → 未漂移：同一内容两次读哈希一致
    http.add(
        "GET",
        f"{REPO_URL}/contents/README.md?ref=readme-auto/update",
        FakeResponse(json_data={
            "content": base64.b64encode(drifted.encode("utf-8")).decode("ascii"),
            "encoding": "base64",
        }),
    )
    assert read_branch_block_hash(_client(http), FULL, PR_BRANCH) == h


# ---- GP13/GP14：合并检测与基线 ----


def _entry(sha="abc1234", **kw):
    e = {
        "sha": sha,
        "block_hash": "",
        "mode": "block",
        "failed_hash": "",
        "last_input_hash": "",
        "pending": False,
        "updated_at": "old",
    }
    e.update(kw)
    return e


def test_merged_pr_advances_baseline_to_head_sha_not_merge_commit():
    """GP13：合并检测把基线推进到 head SHA 而非 merge commit；幂等。"""
    http = FakeHttp()
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=all&head=alice:readme-auto/update&base=main&sort=updated&direction=desc",
        FakeResponse(json_data=[{
            "number": 42,
            "merged": True,
            "merge_commit_sha": "MMM0000",
            "head": {"sha": "HHH1111"},
        }]),
        sticky=True,
    )
    entry = _entry("abc1234")
    assert advance_baseline_from_merged_pr(_client(http), entry, FULL, PR_BRANCH) is True
    assert entry["sha"] == "HHH1111"
    assert entry["sha"] != "MMM0000"
    # 幂等：重复检测不改写
    assert advance_baseline_from_merged_pr(_client(http), entry, FULL, PR_BRANCH) is False
    assert entry["sha"] == "HHH1111"


def test_open_pr_does_not_advance_baseline():
    """GP14：PR 仍 open（未合并）→ 基线不动。"""
    http = FakeHttp()
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=all&head=alice:readme-auto/update&base=main&sort=updated&direction=desc",
        FakeResponse(json_data=[{
            "number": 42,
            "merged": False,
            "merge_commit_sha": None,
            "head": {"sha": "HHH1111"},
        }]),
        sticky=True,
    )
    entry = _entry("abc1234")
    assert advance_baseline_from_merged_pr(_client(http), entry, FULL, PR_BRANCH) is False
    assert entry["sha"] == "abc1234"


# ---- GP15/GP16/GP17：自定义分支、安全边界、full 模式 ----


def test_custom_pr_branch_used_for_ref_and_pr_head():
    """GP15：config 自定义 pr_branch 生效于 ref 与 PR head，base 仍 main。"""
    http = FakeHttp()
    http.add("GET", f"{REPO_URL}/pulls?state=open&head=alice:docs/readme-bot&base=main",
             FakeResponse(json_data=[]))
    http.add("GET", f"{REPO_URL}/git/ref/heads/docs/readme-bot", FakeResponse(status=404))
    http.add("POST", f"{REPO_URL}/git/blobs", FakeResponse(status=201, json_data={"sha": "b"}))
    http.add("POST", f"{REPO_URL}/git/trees", FakeResponse(status=201, json_data={"sha": "t"}))
    http.add("POST", f"{REPO_URL}/git/commits", FakeResponse(status=201, json_data={"sha": "c"}))
    http.add("POST", f"{REPO_URL}/git/refs", FakeResponse(status=201, json_data={}))
    http.add("POST", f"{REPO_URL}/pulls", FakeResponse(status=201, json_data={"number": 7, "html_url": "u"}))
    res = open_or_refresh_pr(
        _client(http), full_name=FULL, content="x", head_sha="h1",
        title="t", body="b", branch="docs/readme-bot",
    )
    ref_post = [r for r in http.writes() if r["url"].endswith("/git/refs")][0]
    assert ref_post["json"]["ref"] == "refs/heads/docs/readme-bot"
    pr_post = [r for r in http.writes() if r["url"].endswith("/pulls")][0]
    assert pr_post["json"]["head"] == "docs/readme-bot" and pr_post["json"]["base"] == "main"
    assert res.number == 7


def test_never_calls_merge_or_close_endpoints():
    """GP16：全流程永不调用合并或关闭接口——写请求仅 git-data 与 PR 创建/编辑。"""
    http = FakeHttp()
    _open_pr_check(http, [{"number": 42}])
    _happy_gitdata(http, ref_exists=True)
    http.add("PATCH", f"{REPO_URL}/pulls/42", FakeResponse(json_data={}))
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=all&head=alice:readme-auto/update&base=main&sort=updated&direction=desc",
        FakeResponse(json_data=[]),
        sticky=True,
    )
    open_or_refresh_pr(
        _client(http), full_name=FULL, content="x", head_sha="h1", title="t", body="b"
    )
    advance_baseline_from_merged_pr(_client(http), _entry(), FULL, PR_BRANCH)
    assert http.writes()  # 确有写请求可检查
    for r in http.writes():
        u = r["url"]
        assert "/merge" not in u and r["method"] != "DELETE"
        # 写请求只允许：git-data 四件套 + PR 创建/编辑
        assert (
            u.endswith("/git/blobs")
            or u.endswith("/git/trees")
            or u.endswith("/git/commits")
            or "/git/refs" in u
            or "/pulls" in u
        )


def test_full_mode_blob_is_whole_generated_content():
    """GP17：mode=full 时 blob 载荷就是整份 AI 生成内容。"""
    http = FakeHttp()
    full_doc = "# My Tool\n\n完整文档正文。\n"
    _open_pr_check(http, [])
    _happy_gitdata(http)
    http.add("POST", f"{REPO_URL}/pulls", FakeResponse(status=201, json_data={"number": 9, "html_url": "u"}))
    open_or_refresh_pr(
        _client(http), full_name=FULL, content=full_doc, head_sha="h1", title="t", body="b"
    )
    blob = [r for r in http.writes() if r["url"].endswith("/git/blobs")][0]
    assert blob["json"]["content"] == full_doc  # 整份，无 marker 强加


def test_queue_item_unused_import_guard():
    """保持 QueueItem 导入被使用（lint 占位）。"""
    assert QueueItem is not None


# ---- 终审 I2 回归：PR base 跟随仓库默认分支（不再硬编码 main）----


def test_pr_base_follows_default_branch_keyword():
    """终审 I2 回归：base 可指仓库默认分支（master）——开 PR 检查 URL 与创建载荷都用它。"""
    http = FakeHttp()
    _happy_gitdata(http)
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=open&head=alice:readme-auto/update&base=master",
        FakeResponse(json_data=[]),
    )
    http.add(
        "POST", f"{REPO_URL}/pulls",
        FakeResponse(status=201, json_data={"number": 9, "html_url": "u"}),
    )
    res = open_or_refresh_pr(
        _client(http), full_name=FULL, content="# x", head_sha="def4567890",
        title="t", body="b", base="master",
    )
    assert res.number == 9
    pr_post = next(
        r for r in http.writes() if r["method"] == "POST" and r["url"].endswith("/pulls")
    )
    assert pr_post["json"]["base"] == "master"  # 载荷 base = 默认分支


def test_merged_pr_detection_respects_default_branch_base():
    """终审 I2 回归：合并检测的 base 同样跟随默认分支（master 仓库不再永远检不到合并、
    基线永不推进）。"""
    http = FakeHttp()
    http.add(
        "GET",
        f"{REPO_URL}/pulls?state=all&head=alice:readme-auto/update"
        "&base=master&sort=updated&direction=desc",
        FakeResponse(json_data=[{"number": 3, "merged": True, "head": {"sha": "newsha1"}}]),
    )
    entry = {"sha": "oldsha"}
    assert advance_baseline_from_merged_pr(
        _client(http), entry, FULL, "readme-auto/update", base="master"
    )
    assert entry["sha"] == "newsha1"
