"""命令行入口与编排：拉数据 → 聚合 → 增量判断 → AI 简介 → 渲染 → 写入。"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .aggregate import (
    bio_input_hash,
    build_bio_payload,
    compute_totals,
    normalize_repos,
    select_featured,
    stats_fingerprint,
)
from .bio import BioError, generate_bio
from .config import Config, ConfigError, load_config
from .github_client import GitHubClient, GitHubError
from .models import Snapshot, TemplateContext
from .render import render_readme, write_if_changed
from .snapshot import load_snapshot, save_snapshot


def _load_fixture(fixture: Path, username: str) -> tuple[dict, list[dict]]:
    user = json.loads((fixture / "user.json").read_text(encoding="utf-8"))
    repos = json.loads((fixture / "repos.json").read_text(encoding="utf-8"))
    user.setdefault("login", username)
    return user, repos


def run(
    cfg_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    no_ai: bool = False,
    fixture: Path | None = None,
) -> int:
    try:
        cfg: Config = load_config(cfg_path)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    root = cfg_path.parent

    # 1. 取数
    try:
        if fixture is not None:
            user, raw_repos = _load_fixture(fixture, cfg.github.username)
        else:
            token = os.environ.get(cfg.github.token_env) or None
            client = GitHubClient(token)
            user = client.get_user(cfg.github.username)
            raw_repos = client.list_repos(cfg.github.username)
    except (GitHubError, OSError) as exc:
        print(f"获取数据失败：{exc}", file=sys.stderr)
        return 3

    # 2. 聚合
    repos = normalize_repos(raw_repos, cfg.repos)
    totals = compute_totals(user, repos)
    featured = select_featured(repos, cfg.featured)
    fingerprint = stats_fingerprint(totals, repos)

    # 3. 增量判断
    snap_path = root / cfg.snapshot.path
    prev = load_snapshot(snap_path)
    if (
        not force
        and prev is not None
        and prev.stats_fingerprint == fingerprint
    ):
        print("无变化，跳过更新")
        return 0

    # 4. AI 简介
    bio_text = prev.bio.text if prev else ""
    payload = build_bio_payload(user, featured, cfg.ai)
    cur_hash = bio_input_hash(payload, cfg.ai)
    ai_failed = False
    if not no_ai and cfg.ai.enabled and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            bio_text = generate_bio(
                payload,
                cfg.ai,
                input_hash=cur_hash,
                prev_hash=prev.bio.input_hash if prev else "",
                prev_text=prev.bio.text if prev else "",
                prev_generated_at=prev.bio.generated_at if prev else "",
            )
        except BioError as exc:
            print(f"简介生成失败，沿用旧简介：{exc}", file=sys.stderr)
            ai_failed = True

    now = datetime.now(timezone.utc)
    ctx = TemplateContext(
        username=cfg.github.username,
        display_name=user.get("name") or cfg.github.username,
        blog=user.get("blog") or "",
        totals=totals,
        featured=featured,
        bio_text=bio_text,
        cards_theme=cfg.readme.cards.theme,
        cards_show=cfg.readme.cards.show,
        include_update_time=cfg.readme.include_update_time,
        updated_at=now.strftime("%Y-%m-%d %H:%M"),
    )

    template_path = root / cfg.readme.template
    content = render_readme(ctx, template_path)

    if dry_run:
        print(content)
        return 0

    readme_path = root / cfg.readme.path
    changed = write_if_changed(readme_path, content)

    new_snap = Snapshot(
        schema=1,
        username=cfg.github.username,
        stats_fingerprint=fingerprint,
        totals={
            "public_repos": totals.public_repos,
            "followers": totals.followers,
            "total_stars": totals.total_stars,
        },
        repos=[
            {
                "full_name": r.full_name,
                "stars": r.stars,
                "language": r.language,
            }
            for r in featured
        ],
        bio=dataclasses.replace(
            prev.bio if prev else Snapshot().bio,
            text=bio_text,
            input_hash=cur_hash,
            generated_at=(prev.bio.generated_at if prev and bio_text == prev.bio.text else now.isoformat()),
            model=cfg.ai.model,
            prompt_version=cfg.ai.prompt_version,
        ),
        generated_at=now.isoformat(),
    )
    save_snapshot(snap_path, new_snap)

    print("已更新" if changed else "内容无差异")
    return 1 if ai_failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自动维护 GitHub Profile README")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="打印到 stdout，不写文件")
    parser.add_argument("--force", action="store_true", help="忽略增量检测，强制重新生成")
    parser.add_argument("--no-ai", action="store_true", help="跳过 AI 简介")
    parser.add_argument("--fixture", default=None, help="从本地 fixture 目录读取数据（离线测试）")
    args = parser.parse_args(argv)
    return run(
        Path(args.config),
        dry_run=args.dry_run,
        force=args.force,
        no_ai=args.no_ai,
        fixture=Path(args.fixture) if args.fixture else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
