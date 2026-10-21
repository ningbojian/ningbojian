<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-09-26

**项目介绍**
phone-hotspot-proxy 是一个面向 Windows 的单文件 Python 工具：连上手机热点后双击运行，自动探测手机侧代理的网关与端口，并把代理设置写入 Windows 系统代理，使不支持单独配代理的软件全部生效。它通过 PowerShell 获取 IPv4 默认网关、对候选端口做 TCP 探测，再修改注册表并调用 Wininet 通知系统，关闭窗口或点击按钮即可关闭/还原代理设置。

**亮点**
- 自动遍历 IPv4 默认网关并 TCP 探测候选端口，无需手动查 IP 端口
- 单文件 Python 标准库 + tkinter，零第三方依赖，无需 pip install
- 修改前备份原系统代理到 backup.json，支持一键还原原始设置
- 记住上次可用网关到 config.json，下次优先尝试并内置连通性测试
- 用正则提取 IP 绕开中文系统 PowerShell 输出乱码，并调用 Wininet 确保生效

**简历素材**
phone-hotspot-proxy（Python，单文件 GUI）：针对手机热点下 Windows 软件代理配置繁琐的问题，基于 PowerShell Get-NetRoute 枚举网关、TCP 探测代理端口，并通过修改注册表与 Wininet InternetSetOptionW 实现系统级代理切换；自动备份/还原原代理配置，全程仅依赖标准库与 tkinter，支持配置文件记忆可用网关与自定义连通性测试地址。
