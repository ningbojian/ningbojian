<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-09-26

项目介绍
这是一个 Windows 下的系统代理一键切换工具，解决连上手机热点后部分软件无法上网、又不支持单独设置代理的问题。它自动探测手机侧代理地址并写入系统代理，让所有软件统一生效；关窗即关闭系统代理。实现上用 PowerShell Get-NetRoute 获取 IPv4 默认网关，在候选端口上逐一 TCP 探测，写入注册表后调用 Wininet InternetSetOptionW(39/37) 使设置即时生效。改动前会把原始代理设置备份到 backup.json，可随时还原。

亮点
- 自动探测 IPv4 默认网关并在候选端口 TCP 探测，免手动填 IP 端口
- 零依赖：仅用 Python 标准库 + tkinter，单文件双击即用
- 改动前备份原始代理设置到 backup.json，支持一键还原
- 记住上次探测成功的网关，下次优先尝试，并内置连通性测试按钮
- bat 启动器按真实安装路径、py 启动器、PATH 多级查找解释器，规避 Store 占位程序

简历素材
用 Python 标准库 + tkinter 实现 Windows 系统代理一键切换（单文件、零第三方依赖）：PowerShell 获取 IPv4 网关、多端口 TCP 探测手机侧代理、写入注册表并经 Wininet 通知生效，支持原设置备份还原。
