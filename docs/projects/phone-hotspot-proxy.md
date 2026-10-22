<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-09-26

项目介绍
这是一个 Windows 上的系统级代理切换工具：连上手机热点后双击运行，自动把系统代理接到手机侧的代理服务上，让所有不支持单独配置代理的软件一次生效，关窗即关闭代理。实现上用 PowerShell 的 Get-NetRoute 枚举所有 IPv4 默认网关，在候选端口上逐一 TCP 探测，命中后备份原始设置、写入注册表并调用 Wininet 通知系统生效。

亮点
- 自动探测网关与代理端口，无需手动查 IP 和端口
- 修改前备份原始代理设置，支持一键还原
- 零依赖单文件：仅 Python 标准库 + tkinter
- 记住上次成功的网关，下次优先尝试
- PowerShell + Wininet 组合使注册表改动即时生效

简历素材
使用 Python 标准库与 tkinter 开发单文件 Windows 系统代理工具：用 PowerShell Get-NetRoute 枚举 IPv4 默认网关，TCP 探测手机侧代理端口后写入注册表，并调用 Wininet 使改动即时生效；支持原始设置备份还原，零第三方依赖。
