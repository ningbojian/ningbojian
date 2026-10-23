# GitHub Overview Auto Agent 使用指南

自动维护你的 GitHub 个人主页 README（`你的用户名/你的用户名` 仓库）：拉取公开仓库数据、整理统计、项目列表（默认全部仓库）、用 AI 生成中文简介，并做增量检测省额度。

## 它做什么

1. **拉数据**：通过 GitHub API 获取你的公开仓库（star、语言、最近 push 等）
2. **项目列表**：全部公开仓库按 star 与活跃度排序展示在主页（默认全部；想只展示一部分在 `featured` 里配）
3. **生成统计**：中文统计表格 + github-readme-stats 可视化卡片
4. **AI 简介**：把仓库数据交给 Claude，生成 100–150 字中文简介
5. **增量更新**：数据没变化就不调 AI、不改文件、不产生提交
6. **各仓库 README 自动更新（可选，默认关闭）**：某个仓库有代码提交时，AI 顺手把它的 README 也更新了——开 PR 给你审，主页 Overview 会在同一轮吸收最新可用内容（详见下文「各仓库 README 自动更新」）

> **只扫公开仓库**：工具调用的 `/users/{用户名}/repos` 接口只会返回 public 仓库；即使返回里混入 private 条目也会被强制跳过，私有仓库永远不会出现在 README 或统计里。

## 快速开始（零克隆，全程网页操作，约 3 分钟）

**不需要 clone、不需要本地环境**，全程在浏览器里完成：

1. **一键获取仓库**：打开模板仓库 [ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)，点绿色 **"Use this template" → Create a new repository**，把新仓库改名为 `你的用户名/你的用户名`。
   > 用户名不用填：工具会自动读取仓库所有者作为用户名。
2. **配 AI key（可选）**：仓库 → Settings → Secrets and variables → Actions → New secret，名称 `ANTHROPIC_API_KEY`，值是你的 Claude API key。不配也能用（AI 内容降级为数据版）。
3. **配模式 B 令牌（要用「各仓库 README 自动更新」必配，2 分钟）**：生成一个 classic PAT（勾 `repo` + `workflow` 两项），存成 secret `WORKFLOW_PAT`——没有它模式 B 无法推送分支/开 PR，其余功能不受影响。详细步骤与常见坑见下文「配置 WORKFLOW_PAT」。
4. **手动跑一次**：Actions 页面 → Update Profile README → Run workflow。完成后：
   - **overview 更新**直接出现在 README；
   - **项目介绍 / 简历素材**（AI 生成内容，默认关闭）开启后会以 **Pull Request** 形式出现——在 PR 的 Diff 里审核、可直接编辑，点 **Merge** 才把文件放进 `docs/projects/`（你的简历素材库，**不会逐个链接到主页**，主页保持干净）；不想要就点 **Close**（同一内容之后不会重复打扰你）。

之后默认每 3 天定时自动更新（北京时间约 10:23 唤醒检查），也可随时手动触发。所有可选项都在 `config.yaml` 里，网页上点 Edit 就能改。

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

环境变量：`GITHUB_TOKEN`（可选，不填走匿名配额 60 次/小时；建议去 GitHub → Settings → Developer settings 生成一个 classic PAT）、AI key（见下一节，名字由 `ai.key_env` 决定，默认 `ANTHROPIC_API_KEY`）。

## 换用其他模型（DeepSeek / 千问 / Kimi / MiMo / Ollama）

AI 后端支持两种 provider：

```yaml
ai:
  provider: "anthropic"          # Claude 官方（默认）
  # ---- 或者用任意 OpenAI 兼容接口 ----
  provider: "openai"
  base_url: "https://api.deepseek.com"  # 服务商文档里的接口地址（通常带 /v1），照抄
  key_env: "AI_API_KEY"                # 建议统一叫 AI_API_KEY（见下方说明）
  model: "deepseek-chat"                # 服务商文档里的模型名
```

> **Secret 命名建议**：用 Claude 就叫 `ANTHROPIC_API_KEY`；用其他任何服务商统一叫 **`AI_API_KEY`**（workflow 会把它注入运行环境，任何服务商都通用，换服务商不用改 secret）。

常见服务商照抄这三行即可（地址以你开通时文档显示的为准）：

| 服务商 | base_url（示例） | model（示例） |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Kimi（月之暗面） | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| MiMo（小米） | 保持 `provider: "anthropic"` + `base_url: https://api.xiaomimimo.com/anthropic` | `mimo-v2.6-flash` |
| Ollama（本地，免费） | `http://localhost:11434/v1` | `qwen2.5:7b` 等 |

改完配置，在 Secrets 里添加对应名字的 key（如 `DEEPSEEK_API_KEY`），然后手动触发一次 force 即可。数据没变化时不会调用任何模型，换 provider 不会产生额外开销。

## 控制开销（重要）

你的 key 你做主，三层控制：

| 层级 | 怎么做 | 效果 |
| --- | --- | --- |
| **运行频率** | Run workflow 对话框里选「定时运行间隔」（不修改 / 每 1–7 天） | 选了天数，本轮结束时自动把定时改为每 N 天一次；不勾不影响本轮回调 |
| **定时开关** | `config.yaml` 里 `schedule.enabled: false` | 定时运行第一步就结束（不装依赖不调 API）；手动触发不受影响。更彻底可在 Actions 页面点 "Disable workflow" |
| **AI 调用** | 增量检测 + `ai.max_age_days` | 数据没变化完全不调 API；简介 14 天内不重新生成（可调） |

### 定时是怎么运作的（间隔门）

默认机制是「**每天唤醒 + 间隔门**」：cron 每天 02:23 UTC（北京 10:23）唤醒一次，第一步读 workflow 文件里的两行标记决定今天是否真跑——

```yaml
# interval_days: 3       ← 每 N 天跑一次（Run workflow 下拉改写）
# interval_anchor: 2026-10-22  ← 间隔锚点日期（改间隔时自动重置为当天）
```

- **改间隔**：Run workflow → 「定时运行间隔」下拉选「每 3 天」之类 → 本轮结束时自动改写上面两行并提交（需 WORKFLOW_PAT）；选「不修改」只跑本轮不改周期；
- 没到日子的唤醒会在第一步直接结束（绿色秒过，日志写明「非每 N 天的运行日」），不装依赖不调 API；
- 想完全手动控制：直接删掉这两行标记，恢复纯 cron 语义。

### cron 对照表（手动改 cron 时参考）

| 频率 | cron（UTC） | 北京时间 |
| --- | --- | --- |
| 每天 | `23 2 * * *` | 每天 10:23 |
| 每周一 | `23 2 * * 1` | 周一 10:23 |
| 每月 1 号 | `23 2 1 * *` | 每月 1 日 10:23 |

> GitHub 的 cron 按 UTC 计，且高峰期可能有几分钟延迟；避开整点（如 23 分）更稳定。`*/N` 之类的写法在 GitHub cron 里语义与直觉不同（每月 1 号重置），想每 N 天一次请用上面的间隔门，别用 `*/N`。

## 灵活开关：只更新其中一部分

overview 和项目介绍（简历素材）互相独立，三种玩法：

| 想要的效果 | 配置（config.yaml） | 或手动触发时 |
| --- | --- | --- |
| overview + 项目介绍都更新 | `projects.enabled: true` | 同左（对话框没有项目介绍开关，已隐式跟随 config） |
| 只更新 overview（默认） | `projects.enabled: false` | 默认 |
| 只更新项目介绍 | `readme.enabled: false` | 取消勾选 update_readme |

**选择给哪些仓库生成介绍**（多选，也可以都不选）：

```yaml
projects:
  include: ["cool-tool"]   # 只给这些仓库生成（仓库名）
  exclude: ["old-thing"]   # 这些仓库永远跳过
```

在网页上编辑 `config.yaml` 保存即可，下次运行生效。

> 项目介绍功能当前默认关闭（`projects.enabled: false`）——上面的 include/exclude 与「AI 内容审核流」一节在你重新开启后生效。

**每次运行都有逐仓库明细**：运行完成后打开该次运行页面，Summary 里有一张表，逐仓库列出这次做了什么（项目介绍：跳过/已重新生成/数据版；主页描述补位：复用/新生成/失败）。

**主页「暂无描述」自动补位**：项目列表里 description 为空的仓库，会用它自己 README 的内容生成一句 ≤80 字的中文短描述顶上（不再显示「暂无描述」）。不想要这个行为：`ai.fill_empty_descriptions: false`。profile 仓库自身（`用户名/用户名`）始终除外——它的 README 是工具自己的输出，若也补位会自引用导致每轮重生成、反复开 PR烧额度。

介绍内容以**各仓库的 README 为主要事实来源**（只有真正要生成/更新某个仓库的介绍时才会去拉它的 README，无变化不调用）；仓库没有 README 时退回只用 GitHub 上的描述等事实信息。

## AI 内容审核流（Pull Request）

你没有直接审核窗口的问题不存在——**所有 AI 写的项目介绍都必须经过你的 PR 审核才会公开**：

- **PR 里只有 `docs/projects/` 一个目录**：README、统计、快照的常规更新都直接进 main，PR 开多久都不会和它们冲突，放心挂着慢慢审。
- 万一 PR 页显示 conflict（通常是 main 上有人手工改了同一批介绍文件），**重新运行一次工作流即可**——分支会基于最新 main 重建。

1. 运行发现介绍有变化（新仓库、数据变了、prompt 升级）→ 自动开一个 PR「AI 项目介绍更新（待审核）」
2. 你在 PR 的 **Files changed** 里看 Diff，不满意可以直接在网页上编辑文件
3. 点 **Merge** → 文件进入 `docs/projects/`（简历素材库，不占用主页）；点 **Close** → 不发布，且**同一批内容之后不会重复开 PR**打扰你（想强制重新生成：改 `config.yaml` 里 `ai.prompt_version` 为 2 再手动触发 force）

纯统计/overview 的机械更新不走 PR、直接生效，不打断你。想关掉审核流直接提交：`projects.review_via_pr: false`（不建议）。

## 配置 WORKFLOW_PAT（模式 B / 改 workflow 文件必配）

GitHub 有个硬性限制——Actions 内置的 `GITHUB_TOKEN` 无权修改 `.github/workflows/` 下的文件，也无权替你向其他仓库推送分支/开 PR，所以这两件事都需要你自己的令牌：

1. 右上角头像 → Settings → Developer settings → Personal access tokens。这里有两种令牌，**选 `Tokens (classic)`**：
   - *Fine-grained tokens*（新）：按仓库、按权限项精细授权。**注意有个隐蔽坑**：如果生成时选了 "Only select repositories"，令牌对**未勾选的公开仓库也会返回 404**（表现为模式 B 状态行「读取失败 N 仓」，其余仓库一切正常）——本工具读写的是你全部公开仓库，不建议用 fine-grained；
   - *Tokens (classic)*（经典）：按「权限域」授权，对全部仓库（含之后新建的）生效。本工具只需要它。
2. **Generate new token (classic)**，勾选 **`repo`** 和 **`workflow`** 两项权限（`repo` 负责读写仓库内容，`workflow` 负责修改 workflow 文件；令牌还要替你把 README/统计提交推上去，所以不能只勾 workflow），有效期自选
3. 回到本仓库 → Settings → Secrets and variables → Actions → **New repository secret**，名称填 `WORKFLOW_PAT`，值粘贴刚生成的 token

> **换令牌后必须重新粘贴进 secret**：secret 存的是你粘贴那一刻的值，在 PAT 页面重建/续期/改权限都**不会**自动同步到 `WORKFLOW_PAT`——换了令牌却忘了更新 secret，是「明明配了 classic PAT 却还是 404」的第一大原因。

> **不配置也完全能用**：overview、统计、定时更新都不受影响；只是模式 B 静默跳过，改了 workflow 文件（如 cron）也推不上去。

## 各仓库 README 自动更新（模式 B，默认关闭）

让每个仓库的 README 也跟着代码一起长：**某仓库有新提交 → AI 更新它的 README → 开 PR 给你审 → 你的个人主页 Overview 同轮吸收最新内容**。AI 生成前会先读取仓库现有的 README 全文作为修订基础——保留仍然准确的表述、把新变更融进去，而不是只看几条提交凭空另写。写回只动 README 里一对标记之间的「托管区」，标记外你手写的内容一个字节都不会碰。

### 三结局口诀（PR 开出来后只有三种处理，怎么选都不会坏）

- **合并** → 新 README 落进仓库，主页本轮已经吸收，无需再做任何事；
- **关闭** → 拒绝这批文案：主页将不再包含它，同批内容不会自动重开（下次新提交会带新批次回来）；
- **先放着** → 完全没问题：PR 留着以后合，主页照样是新鲜的（期间有新批次时 PR 会被刷新，合并前请重读 diff）。

### 怎么启用

1. 需要已配置 `WORKFLOW_PAT` secret（classic PAT，`repo` + `workflow` 两个 scope，见上文「配置 WORKFLOW_PAT」）——没有它工具无法替你推送分支/开 PR，会静默跳过模式 B，其余功能不受影响。
2. `config.yaml` 打开开关。**灰度建议先放 1 个仓库试跑**：

   ```yaml
   repo_readmes:
     enabled: true
     include: ["你的某个仓库名"] # 空 = 全部仓库；先放 1 个灰度，稳了再清空
   ```

3. 手动触发 Run workflow 时有三个可选勾选（不勾 = 与定时跑完全一样的默认行为）：
   - **force**：强制重生成 A+B——忽略增量门重写主页 overview，并把**全部公开仓库**的 README 全量重跑一遍（AI 生成 → 开 PR → 主页吸收）。新仓库/没提交过的仓库也会立即出第一份 README PR，不用等真实提交；
   - **repo_readmes**：只强制模式 B（同上的全量重跑），不影响主页 overview 的增量门；
   - **wait_for_merges**：暂停，等你合并 PR（最多 30 分钟），合并完立刻继续；不勾则直接继续，PR 事后随时可合。

### 清单在哪、怎么通知你

- 每轮有 open PR 时，本仓库会出现/刷新一个 issue：**「🔔 README 更新待合并清单」**——逐条 PR 链接、新版 README 预览链接、三种处理方式说明，@你 且指派给你（自开的 PR 不会通知自己，这里特意用 @mention 制造通知）。
- 状态变化只原地改这个 issue 的 body，**永远不发评论**（不轰炸通知）；PR 全部处理完自动关闭（关闭本身就是「可以收工」的信号）。
- 本轮确实更新了 Overview（主 README 有新内容）时，收尾会在 issue 里追加「本轮 Overview 已进入 main」终态行；Overview 没变化则不加。项目介绍的 PR 由随后的工作流步骤创建，issue 里不写它的链接（CLI 运行时它还不存在）。
- **请勿关闭本仓库的 Issues**——它是模式 B 的通知通道；关了还有 Step Summary 快照兜底，但收不到 @提醒。

### 主页为什么永远是新鲜的（不用等你合并）

主页 Overview 对每个仓库按这个优先级取 README 内容，B 跑完 A 就是新的，不跨轮：**已合并**（含等待窗口内合并）→ 读默认分支真源；**仍 open** → 用本轮刚生成的内容（跨轮静默跳过时直接读 PR 分支）；**等待期间被你关闭** → 回退旧文；**本轮没产出** → 旧文。每次运行的 Step Summary 末尾有一行「本轮 A 的 README 输入来源：…」对账，来源一目了然。

### 不产出也是正常状态（静默路径）

Summary 里每轮必有一行「模式 B 状态」：没变化、首见记基线（新仓库默认等下一次真实提交才出第一份 README；不想等就勾 force/repo_readmes 立即全量生成）、AI 缺 key 积压、与上次失败输入相同已跳过（新提交或 force 才重试）……这些都不是错误。读取失败（如某仓 token 不可见导致 404）、AI 失败、推送失败都被逐仓隔离——一个仓库出问题只会把它自己跳过并在「模式 B 状态」里显示「读取失败 N 仓」，绝不影响其他仓库与主页更新。

## 配置项参考（config.yaml）

```yaml
schedule:
  enabled: true            # false = 关掉定时更新（手动仍可触发）
github:
  username: ""             # 留空 = 自动用仓库所有者（fork 即用）
  token_env: "GITHUB_TOKEN"  # token 读哪个环境变量
repos:
  exclude_forks: true      # 不展示 fork 的仓库
  exclude_archived: false  # 是否排除已归档仓库
  exclude: ["you/you"]     # 黑名单（建议排除 profile 仓库自身）
featured:
  count: 0                 # 上主页的项目数上限；0 = 全部
  min_stars: 0             # 入选最低 star
  recency_days: 0          # 只考虑最近 N 天有 push 的仓库；0 = 不限（要「真·全部」保持 0）
  sort_by: "score"         # score | stars | updated
  score_stars_weight: 1.0
  score_recency_weight: 0.5
readme:
  enabled: true            # false = 不更新 overview
  path: "README.md"
  template: "templates/profile.md.j2"
  cards:
    theme: "github_dark"   # github_dark | github_light 等
    show: ["stats", "top_langs", "streak"]  # 三种卡片任选
  include_update_time: true
  visitors_badge: false   # true = 主页嵌入「主页访问量」计数徽章（komarev.com 免费第三方服务，页面渲染一次 +1；GitHub 不提供官方的主页访问量 API，这是业界通行做法）
ai:
  enabled: true
  model: "claude-opus-5-5" # 降本可换 "claude-haiku-5-5"
  max_repos: 15            # 最多把多少仓库喂给 AI
  max_age_days: 14         # 简介最长复用天数
  prompt_version: 1        # 改了 prompt 后 +1 可强制重新生成
  fill_empty_descriptions: true  # 项目列表里 description 为空时，用其 README 生成短描述补位
projects:
  enabled: false           # true = 生成项目介绍/简历素材（默认关闭，开启前先配好 AI key）
  dir: "docs/projects"
  featured_only: false     # true = 只给精选列表生成；false = 全部仓库都生成介绍
  include: []              # 多选白名单，非空时只生成这些仓库
  exclude: []              # 黑名单
  review_via_pr: true      # AI 内容走 PR 审核（推荐）
repo_readmes:
  enabled: false           # true = 各仓库 README 托管区自动更新（需 WORKFLOW_PAT；默认关闭）
  include: []              # 空 = 全部仓库；灰度建议先放 1 个，如 ["shiyuan"]
  exclude: []              # 在 include 之上再排除
  max_diff_chars: 6000     # 喂给模型的 diff 字符上限
  prompt_version: 2        # 改了模式 B 的 prompt 后 +1，强制重新生成
  pr_branch: "readme-auto/update"  # PR 分支名；主页从这里读未合并内容
```

改完 `ai.prompt_version` 或想立刻刷新简介时，手动触发并勾选 force。

## 常见问题

- **想关掉自动更新**：`config.yaml` 里 `schedule.enabled: false` 提交即可；或在 Actions 页面 Disable workflow。
- **想让所有仓库立刻出/更新 README PR**：Run workflow 勾 **force**（A+B 全量）或 **repo_readmes**（只 B 全量）——全部公开仓库（profile 自身除外）都会重新生成并开 PR，不勾则只处理有新代码提交的仓库。
- **某仓「读取失败 404」但它明明是公开仓库**：几乎都是 `WORKFLOW_PAT` 的问题。按顺序查：① secret 里的值是不是 **classic PAT**（`ghp_` 开头）——fine-grained PAT 若选了 "Only select repositories"，对未勾选的公开仓一律 404；② 换了新令牌后**有没有把新值重新粘进 secret**（在 PAT 页面重建/续期不会自动同步到 secret，这是最常见的坑）；③ 令牌是否已过期。一个仓读取失败只跳过它自己，不影响其他仓库。
- **AI 简介没生成**：检查 secret 名称是否为 `ANTHROPIC_API_KEY`；工具在 AI 失败时会保留旧简介，不会让任务失败。
- **README 被我改坏了**：手动改动会被下次运行覆盖——所有可定制内容都在 `config.yaml` 与 `templates/profile.md.j2` 里改。
- **数据是旧的**：Actions 手动触发 + force 即可刷新。
- **模式 B 没跑**：看 Summary 里的「模式 B 状态」行——最常见是没配 `WORKFLOW_PAT`（无法推送/开 PR，配好自动启用）或 `repo_readmes.enabled` 还是 false；勾选了 `repo_readmes` 但 config 里是 false 也会给冲突警告。
- **@提醒没收到**：确认本仓库 Issues 没被关闭、GitHub 通知设置里勾了 Issues；清单入口固定在本仓「🔔 README 更新待合并清单」issue + 运行页 Summary 快照。
- **把本工具分享给别人**：对方只需完成「快速开始」4 步；本仓库既是工具源码也是 profile 仓库。

## 开发

```bash
pip install -e ".[dev]"
pytest            # 全部离线运行，不碰网络
```

代码结构见 `src/profile_agent/`：`github_client`（取数）→ `aggregate`（过滤/统计/精选/指纹）→ `bio`（AI 简介）→ `render`（模板）→ `cli`（编排与增量门）。
