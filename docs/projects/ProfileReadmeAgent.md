<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# ProfileReadmeAgent

- 仓库：[ningbojian/ProfileReadmeAgent](https://github.com/ningbojian/ProfileReadmeAgent)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-21

ProfileReadmeAgent

项目介绍：ProfileReadmeAgent 是一个 Python 项目，用于自动生成 GitHub 个人主页（profile README）。它通过 GitHub Actions 的 Update Profile README workflow 触发，运行后会用生成的内容覆盖仓库的 README 占位文件，产出包含仓库统计、精选项目卡片和 AI 中文简介的个人主页。其中 AI 中文简介由 Anthropic 模型生成，需要在 Actions 中配置 ANTHROPIC_API_KEY；不配置该密钥时也能生成功能受限的数据版。完整使用说明见仓库内的 docs/guide.md。

亮点
- 基于 GitHub Actions 实现自动化，手动触发 Update Profile README workflow 即可完成更新
- README 采用模板占位文件机制，运行 workflow 后自动覆盖为生成内容
- 生成内容涵盖仓库统计与精选项目卡片等多类信息模块
- 可选接入 Anthropic API 生成 AI 中文简介，不配密钥时仍可生成数据版
- 主体使用 Python 实现，并附带 docs/guide.md 使用文档

简历素材：ProfileReadmeAgent（Python）：基于 GitHub Actions 实现的 GitHub 个人主页 README 自动生成工具。通过 workflow 触发，自动采集仓库统计并渲染精选项目卡片，可选接入 Anthropic API 生成 AI 中文简介，未配置密钥时回退生成数据版。采用占位文件覆盖机制完成主页更新，配套使用文档。
