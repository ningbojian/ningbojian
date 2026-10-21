<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# ProfileReadmeAgent

- 仓库：[ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-21

项目介绍：ProfileReadmeAgent 是一个基于 Python 的 GitHub Actions 模板仓库，能自动生成并每周定时更新个人主页 README，涵盖公开仓库统计、精选项目卡片与 AI 生成内容。它通过增量检测跳过无变化的数据，避免不必要的 AI 调用，并将生成的项目介绍存入 docs/projects/ 便于直接引用。

亮点：
- 全部公开仓库按 star 与活跃度排序上主页，支持 featured 精选配置
- 集成 github-readme-stats 深色主题可视化卡片展示统计
- 支持 Claude、DeepSeek、千问、Kimi、Ollama 等多模型生成中文简介
- 无数据变化时跳过 AI 调用，简介 14 天内不重写，节省额度
- AI 内容以 Pull Request 提交，经人工 Diff 审核后才公开

简历素材：基于 Python 与 GitHub Actions 开发 ProfileReadmeAgent 模板项目，实现个人主页 README 的自动生成与每周定时更新；通过增量检测机制跳过无变化数据以节省 AI 调用额度，支持多模型中文简介生成、仓库统计可视化卡片及精选项目配置，AI 生成内容经 Pull Request 人工审核后发布。
