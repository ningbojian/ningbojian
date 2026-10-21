<!-- 由 profile-agent 生成/维护，AI 内容已经过你的审核；事实数据自动更新 -->
# agri-ecommerce-platform

- 仓库：[ningbojian/agri-ecommerce-platform](https://github.com/ningbojian/agri-ecommerce-platform)
- 语言：JavaScript　⭐ 0　🍴 0
- 最近推送：2026-10-20

agri-ecommerce-platform 是一个电商助农全栈系统，由 2021 年比赛版原生微信小程序演进而来。`competition-miniprogram/` 保留历史原型，`platform/` 实现了原生小程序 + Spring Boot 三服务 + MySQL 三库 + Vue 3 管理后台的完整前后端闭环，覆盖认证、商品、地址、订单、模拟支付与供应商管理。本地主流程已跑通，后端 83 项冒烟检查通过。

亮点
- 三服务三库架构：商品/用户订单/供应商按业务边界拆分独立部署与数据库，无跨库外键
- 下单原子扣减库存（条件更新防竞态），落库失败自动补偿，金额由服务端按快照计算
- JWT 跨服务验签 + 分角色路径鉴权 + 资源归属校验 + BCrypt，敏感字段不序列化
- PaymentGateway 抽象 + 模拟实现，支付幂等，接真实微信支付只需替换网关
- 工程化交付：reset/schema/seed 建库脚本、83 项冒烟检查、后台无头回归与小程序静态校验

简历素材
电商助农全栈平台（Spring Boot 2.2 + MyBatis-Plus + MySQL 三库三服务 + 原生微信小程序 + Vue 3/Element Plus 管理后台）。设计三服务三库按业务边界拆分，JWT 跨服务验签与分角色鉴权；下单通过内部接口原子扣减库存并补偿，服务端定价防篡改；PaymentGateway 抽象支持模拟支付幂等。规模：16 控制器、59 接口、10 张表、15 小程序页面，83 项后端冒烟检查通过。
