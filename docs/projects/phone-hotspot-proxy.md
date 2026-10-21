<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-09-26

## 项目介绍
phone-hotspot-proxy 是一个面向 Windows 的桌面小工具，解决连接手机热点后部分软件无法上网、且不支持单独配置代理的问题。它自动探测手机侧代理服务的 IP 与端口，一键写入系统级代理，让所有软件全局生效，关窗时自动关闭。项目为纯 Python 单文件实现（tkinter GUI），零第三方依赖，改动前自动备份原代理设置，可随时还原。

## 亮点
- 自动遍历 IPv4 默认网关并 TCP 探测候选端口，免手动查 IP
- 零依赖，仅 Python 标准库 + tkinter，单文件即可运行
- 修改系统代理前备份到 backup.json，支持一键还原
- 记住上次可用网关并优先尝试，内置连通性测试按钮
- 通过 Wininet InternetSetOptionW 广播代理变更，确保浏览器即时生效

## 简历素材
开发 Windows 系统代理自动化工具 phone-hotspot-proxy（Python/tkinter，单文件零依赖）：调用 PowerShell Get-NetRoute 枚举默认网关并 TCP 探测手机代理端口，自动写入注册表并调用 Wininet 广播变更；内置配置记忆、代理设置备份还原与连通性测试，实现手机热点场景下系统级代理的一键切换。
