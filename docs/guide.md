# GitHub Overview Auto Agent 使用指南

自动维护你的 GitHub 个人主页 README（`你的用户名/你的用户名` 仓库）：拉取公开仓库数据、整理统计、精选项目、用 AI 生成中文简介，并做增量检测省额度。

## 它做什么

1. **拉数据**：通过 GitHub API 获取你的公开仓库（star、语言、最近 push 等）
2. **精选项目**：按 star 与活跃度打分，自动挑出最值得展示的项目
3. **生成统计**：中文统计表格 + github-readme-stats 可视化卡片
4. **AI 简介**：把仓库数据交给 Claude，生成 100–150 字中文简介
5. **增量更新**：数据没变化就不调 AI、不改文件、不产生提交

> **只扫公开仓库**：工具调用的 `/users/{用户名}/repos` 接口只会返回 public 仓库；即使返回里混入 private 条目也会被强制跳过，私有仓库永远不会出现在 README 或统计里。

## 快速开始（5 分钟）

1. **建 profile 仓库**：新建名为 `你的用户名/你的用户名` 的仓库（勾选"使用 README 初始化"），把本仓库的全部文件复制进去（或直接 fork 后改名）。
2. **填用户名**：编辑 `config.yaml`，把 `github.username` 改成你的 GitHub 用户名。
3. **配 AI key（可选）**：仓库 → Settings → Secrets and variables → Actions → New secret，名称 `ANTHROPIC_API_KEY`，值是你的 Claude API key。不配也能用，只是没有 AI 简介（该区块会显示占位注释）。
4. **启用 Actions**：进入 Actions 页面，如果提示就点 "Enable"。
5. **手动跑一次**：Actions → Update Profile README → Run workflow → 勾选 force → 等待完成，回仓库看生成的 `README.md`。

之后每周一定时自动更新（北京时间约 10:23），也可以随时手动触发。

## 本地运行

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m profile_agent --no-ai            # 不调 AI，直接生成
python -m profile_agent                    # 完整运行（需 ANTHROPIC_API_KEY）
python -m profile_agent --dry-run          # 只打印不写文件
python -m profile_agent --force            # 忽略增量检测
python -m profile_agent --fixture tests/fixtures --no-ai --dry-run   # 完全离线演示
```

环境变量：`GITHUB_TOKEN`（可选，不填走匿名配额 60 次/小时；建议去 GitHub → Settings → Developer settings 生成一个 classic PAT）、`ANTHROPIC_API_KEY`（AI 简介用）。

## 控制开销（重要）

你的 key 你做主，三层控制：

| 层级 | 怎么做 | 效果 |
| --- | --- | --- |
| **运行频率** | 改 `.github/workflows/update-profile.yml` 里的 `cron` | 见下方对照表 |
| **定时开关** | `config.yaml` 里 `schedule.enabled: false` | 定时运行第一步就结束（不装依赖不调 API）；手动触发不受影响。更彻底可在 Actions 页面点 "Disable workflow" |
| **AI 调用** | 增量检测 + `ai.max_age_days` | 数据没变化完全不调 API；简介 14 天内不重新生成（可调） |

### cron 对照表

| 频率 | cron（UTC） | 北京时间 |
| --- | --- | --- |
| 每天 | `23 2 * * *` | 每天 10:23 |
| 每 3 天 | `23 2 */3 * *` | 每 3 天 10:23 |
| 每周一（默认） | `23 2 * * 1` | 周一 10:23 |
| 每月 1 号 | `23 2 1 * *` | 每月 1 日 10:23 |

> GitHub 的 cron 按 UTC 计，且高峰期可能有几分钟延迟；避开整点（如 23 分）更稳定。

## 配置项参考（config.yaml）

```yaml
schedule:
  enabled: true            # false = 关掉定时更新（手动仍可触发）
github:
  username: "your-name"    # 必填
  token_env: "GITHUB_TOKEN"  # token 读哪个环境变量
repos:
  exclude_forks: true      # 不展示 fork 的仓库
  exclude_archived: false  # 是否排除已归档仓库
  exclude: ["you/you"]     # 黑名单（建议排除 profile 仓库自身）
featured:
  count: 6                 # 精选项目个数
  min_stars: 0             # 入选最低 star
  recency_days: 365        # 只考虑一年内有 push 的仓库；0 = 不限
  sort_by: "score"         # score | stars | updated
  score_stars_weight: 1.0
  score_recency_weight: 0.5
readme:
  path: "README.md"
  template: "templates/profile.md.j2"
  cards:
    theme: "github_dark"   # github_dark | github_light 等
    show: ["stats", "top_langs", "streak"]  # 三种卡片任选
  include_update_time: true
ai:
  enabled: true
  model: "claude-opus-5-5" # 降本可换 "claude-haiku-5-5"
  max_repos: 15            # 最多把多少仓库喂给 AI
  max_age_days: 14         # 简介最长复用天数
  prompt_version: 1        # 改了 prompt 后 +1 可强制重新生成
```

改完 `ai.prompt_version` 或想立刻刷新简介时，手动触发并勾选 force。

## 常见问题

- **想关掉自动更新**：`config.yaml` 里 `schedule.enabled: false` 提交即可；或在 Actions 页面 Disable workflow。
- **AI 简介没生成**：检查 secret 名称是否为 `ANTHROPIC_API_KEY`；工具在 AI 失败时会保留旧简介，不会让任务失败。
- **README 被我改坏了**：手动改动会被下次运行覆盖——所有可定制内容都在 `config.yaml` 与 `templates/profile.md.j2` 里改。
- **数据是旧的**：Actions 手动触发 + force 即可刷新。
- **把本工具分享给别人**：对方只需完成「快速开始」5 步；本仓库既是工具源码也是 profile 仓库。

## 开发

```bash
pip install -e ".[dev]"
pytest            # 全部离线运行，不碰网络
```

代码结构见 `src/profile_agent/`：`github_client`（取数）→ `aggregate`（过滤/统计/精选/指纹）→ `bio`（AI 简介）→ `render`（模板）→ `cli`（编排与增量门）。
