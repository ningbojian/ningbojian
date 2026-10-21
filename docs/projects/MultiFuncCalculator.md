<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# MultiFuncCalculator

- 仓库：[ningbojian/MultiFuncCalculator](https://github.com/ningbojian/MultiFuncCalculator)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-19

项目介绍

MultiFuncCalculator 是一个基于 Python 的桌面小工具合集，通过主菜单（FirstPage.py）统一启动，包含科学计算器、进制转换、数字华容道、数独、2048、猜数字等 7 类功能模块。科学计算器支持表达式解析（运算符、括号、三角函数、指数/对数、阶乘），数独求解器采用回溯算法，华容道/八数码求解器采用状态搜索并支持步骤回放展示。UI 部分使用 Tkinter 与 Pygame 两个框架混搭实现，子模块通过 `subprocess.Popen([sys.executable, ...])` 启动，兼容虚拟环境。

亮点

- 主菜单统一调度 7 类子模块，模块化文件结构清晰可独立运行
- 科学计算器自实现表达式解析，支持括号嵌套与三角函数等运算
- 数独求解器用回溯算法；华容道求解器用状态搜索并逐步展示解法
- 混用 Tkinter 与 Pygame 两种 GUI 框架，并修复了 Python 3.13 字体兼容问题
- 启动器改用 sys.executable 启动子进程，解决 venv 与任意目录下的运行问题

简历素材

软件工程项目（两人协作）：基于 Python/Tkinter/Pygame 开发多功能桌面应用，集成科学计算器（自实现表达式解析）、进制转换、数独（回溯求解）、华容道/八数码（状态搜索与步骤回放）、2048 等 7 个功能模块；通过主菜单统一调度，子进程启动兼容虚拟环境，并修复 Python 3.13 下 Pygame 字体枚举兼容问题。
