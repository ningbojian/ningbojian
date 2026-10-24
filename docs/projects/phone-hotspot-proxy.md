<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# phone-hotspot-proxy

- 仓库：[ningbojian/phone-hotspot-proxy](https://github.com/ningbojian/phone-hotspot-proxy)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-22

**项目介绍**

phone-hotspot-proxy 是一个 Windows 桌面小工具，解决连接手机热点后，部分不支持单独配置代理的软件无法上网的问题。它自动探测手机侧代理服务的 IP 与端口，将 Windows 系统代理一键接入，使所有软件全局生效，并在退出时关闭代理、可随时还原原始设置。项目使用 Python 标准库与 tkinter 实现，零第三方依赖、单文件运行。

**亮点**

- 用 PowerShell Get-NetRoute 枚举 IPv4 默认网关，正则提取 IP，绕开中文系统输出乱码
- 内置候选端口 TCP 探测与连通性测试，成功网关写入 config.json 下次优先复用
- 修改系统代理前备份至 backup.json，提供一键还原，不破坏原有设置
- 通过 Wininet InternetSetOptionW(39/37) 通知系统，确保注册表改动即时生效
- 零依赖单文件，仅用标准库 + tkinter；启动脚本规避 Microsoft Store 占位 python.exe 的坑

**简历素材**

开发 Windows 桌面代理助手（Python 3.7+/tkinter），用于自动接入手机热点侧代理：通过 PowerShell Get-NetRoute 枚举 IPv4 默认网关，TCP 探测 5 个内置候选端口定位代理，写入注册表并调用 Wininet InternetSetOptionW 使系统代理生效；修改前自动备份至 JSON 支持一键还原，并缓存上次成功的网关提升二次启动速度。全程零第三方依赖，单文件交付，MIT 开源。
