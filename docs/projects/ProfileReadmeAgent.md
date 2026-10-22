<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# ProfileReadmeAgent

- 仓库：[ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-21

项目介绍

ProfileReadmeAgent 是一个基于 GitHub Actions 的模板仓库，用一键生成并自动维护 GitHub 个人主页 README。它自动统计公开仓库数、总 Star 与语言分布，生成精选项目卡片与中文 AI 简介，并为每个仓库产出可直接用于简历的中文项目介绍。数据无变化时不调用 AI、不产生提交，AI 内容一律以 Pull Request 形式提交供人工审核。

亮点

- 基于 GitHub Actions 定时自动刷新，约 3 分钟完成初始化
- 兼容 Claude、DeepSeek、千问、Kimi、MiMo 与本地 Ollama
- 增量更新：数据无变化不调 AI、不产生提交，控制额度开销
- AI 内容经 Pull Request 人工审核后才合并公开
- 支持勾选框按仓库指定重写，`featured` 配置可定制展示范围

简历素材

基于 GitHub Actions 与 Python 开发个人主页自动维护模板，集成 github-readme-stats 统计卡片，支持 Claude、DeepSeek、Ollama 等多模型生成中文简介与项目介绍；实现增量更新机制，数据无变化不调用 AI、不提交变更，AI 输出经 Pull Request 人工审核，兼顾额度成本与内容可控性。
