<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-09-26

**项目介绍**

这是一款面向 Windows 的单文件 Python 工具，解决连接手机热点后电脑上不支持单独设置代理的软件无法上网的问题。它自动探测手机侧代理服务并一键写入 Windows 系统代理，使所有软件全局生效。实现上通过 PowerShell 获取 IPv4 默认网关、TCP 探测候选端口、操作注册表并调用 Wininet API 通知系统，关闭窗口时自动关闭代理。

**亮点**

- 自动探测网关与端口，无需手动查 IP 和端口
- 改动前备份原始代理设置，支持一键还原
- 仅用 Python 标准库 + tkinter，零依赖单文件部署
- 记住上次可用网关，下次启动优先尝试
- 内置连通性测试按钮，可自定义探测地址

**简历素材**

基于 Python 标准库与 tkinter 开发 Windows 系统代理自动化工具，解决手机热点场景下多软件代理配置问题。通过 PowerShell 获取 IPv4 默认网关并 TCP 探测候选端口，自动写入注册表代理配置并调用 Wininet API 使系统代理即时生效；实现原始设置备份与一键还原、可用网关记忆、内置连通性测试等功能。零第三方依赖，单文件部署，MIT 开源。
