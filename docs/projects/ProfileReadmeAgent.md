<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# ProfileReadmeAgent

- 仓库：[ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-21

**项目介绍**

ProfileReadmeAgent 是一个基于 Python 和 GitHub Actions 的自动化工具，用于自动维护 GitHub 个人主页 README。它能自动统计公开仓库数据、生成精选项目卡片、中文 AI 个人简介及每个仓库的项目介绍，支持增量更新以避免浪费 AI 额度，所有 AI 生成内容均通过 Pull Request 人工审核后才公开。

**亮点**

- 支持 Claude / DeepSeek / 千问 / Kimi / Ollama 等多 AI 模型接入
- 增量更新机制：数据无变化时不调用 AI、不产生提交
- AI 生成内容一律以 PR 形式提交，人工审核后才发布
- 无需配置 Secret 即可运行，AI 部分自动降级为占位注释
- 集成 github-readme-stats 可视化卡片，支持按 star 与活跃度排序

**简历素材**

开发 GitHub 个人主页自动化维护工具 ProfileReadmeAgent，基于 Python 与 GitHub Actions 实现仓库统计、精选项目展示、AI 简介及项目介绍自动生成。支持 Claude / DeepSeek / 千问等多模型接入，采用增量更新机制避免无效 API 调用，所有 AI 内容经 PR 人工审核后发布，兼顾效率与质量控制。
