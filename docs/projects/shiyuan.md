<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# shiyuan

- 仓库：[ningbojian/shiyuan](https://github.com/ningbojian/shiyuan)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-20

**项目介绍**

氏源是一个以姓氏文化为主题的检索与可视化阅读网站，收录 348 个姓氏、6,251 位历史人物，支持姓氏源流、迁徙、分布、人物关系等多维浏览。项目基于 Django 5.2 + SQLite 服务端渲染，前端使用本地 ECharts 呈现分布地图、词云、关系图与迁徙时间轴，数据由唯一的 `catalog.json` 经管理命令校验加载，保证可复现。

**亮点**

- Django 5.2 服务端渲染，无 SPA 与 Node 构建链，架构简单可维护
- 本地 ECharts 呈现地图、词云、关系图、迁徙时间轴，懒加载且提供文本替代
- 222 个自动化测试，覆盖 CSRF/IDOR、XSS、API、SEO 与部署配置
- 页面严格控制查询预算（首页 6 条、详情 ≤16 条），Lighthouse 无障碍 1.00
- 提供只读 JSON API v1 与 JSON-LD 结构化数据，GitHub Actions 持续集成

**简历素材**

独立开发姓氏文化查询与可视化网站：基于 Django 5.2 + SQLite 构建服务端渲染应用，使用本地 ECharts 实现分布地图、词云、关系图与迁徙时间轴可视化；整理并加载 348 个姓氏、6,251 位历史人物数据；实现搜索分页、用户认证、评论收藏及限流防护；编写 222 个自动化测试，Lighthouse 无障碍评分 1.00，通过 GitHub Actions CI 并部署至 PythonAnywhere。
