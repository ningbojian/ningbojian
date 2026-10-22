<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# ProfileReadmeAgent

- 仓库：[ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-21

项目介绍
ProfileReadmeAgent 是一个基于 GitHub Actions 的模板仓库，用一条工作流自动维护你的 GitHub 主页 README：统计公开仓库数、总 Star、语言分布并渲染 github-readme-stats 深色卡片，按 star 与活跃度排序展示全部公开仓库，并可调用 Claude、DeepSeek、千问、Kimi、MiMo 或本地 Ollama 生成中文个人简介、项目介绍与简历素材。增量更新机制保证数据无变化时不调用 AI、不产生提交；所有 AI 内容以 Pull Request 形式提交，人工审核后合并才公开。使用时点 "Use this template" 生成仓库、按规则命名并手动运行 Update Profile README 即可，约 3 分钟产出成品，之后每周自动更新。

亮点
- 基于 GitHub Actions 定时工作流，模板化一键生成主页
- github-readme-stats 深色卡片 + 按 star/活跃度排序的仓库展示
- 多模型可配：Claude、DeepSeek、千问、Kimi、MiMo、Ollama
- 增量更新：数据无变化不调 AI、不提交，简介 14 天不重写
- AI 内容走 PR 审核，支持逐仓库勾选强制重写

简历素材
基于 Python 与 GitHub Actions 开发模板仓库 ProfileReadmeAgent，实现 GitHub 主页 README 的自动化维护：仓库统计与语言分布可视化、按 star 与活跃度排序的项目展示，并接入 Claude、DeepSeek、千问、Kimi、MiMo 及本地 Ollama 生成中文简介与项目介绍。设计增量更新策略，数据无变化时不调用模型、不产生提交，简介 14 天内不重写，有效控制 API 开销；AI 生成内容通过 Pull Request 提交并人工审核后合并，保障输出可控。
