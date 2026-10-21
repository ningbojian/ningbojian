<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# RoboArmDev-Showcase

- 仓库：[ningbojian/RoboArmDev-Showcase](https://github.com/ningbojian/RoboArmDev-Showcase)
- 语言：Python　⭐ 0　🍴 0
- 最近推送：2026-10-19

**项目介绍**

该项目（团队项目，2024）将图片、线稿与汉字笔顺 GIF 转换为六自由度 ArmPi 机械臂可执行的绘画与写字轨迹。绘画链路经 GrabCut 与可选风格化生成线稿后，使用 HALCON `lines_gauss` 提取 XLD 轮廓并简化为轨迹点；写字链路用帧差法解析笔顺 GIF，生成有序笔画坐标。所有轨迹统一做坐标归一化、镜像变换与工作空间映射，最终通过机械臂执行接口交付（IK 与硬件驱动由团队完成，本仓库提供 dry-run 接口）。

**亮点**

- HALCON `lines_gauss` 提取 XLD 轮廓，配合道格拉斯-普克控制点数与顺序
- 汉字笔顺 GIF 经帧差、形态学处理生成有序笔画坐标，支持“永”等字
- 轨迹按最长边缩放并平移，映射到 20×20 目标工作空间
- 提供 `DryRunController` 最小接口，无硬件也可预览机械臂执行轨迹
- 记录 Canny、DBSCAN 等早期方案对比与笔尖高度、舵机故障等工程折中

**简历素材**

负责六自由度机械臂绘画/写字项目的轨迹生成模块：基于 OpenCV 与 HALCON 实现线稿轮廓提取、汉字笔顺 GIF 帧差解析与笔画坐标生成，完成坐标归一化、镜像变换与工作空间映射，并封装机械臂 dry-run 执行接口；经 Canny、DBSCAN 等多方案对比后确定轮廓提取加道格拉斯-普克简化方案。
