# 第5课 gap audit

唯一规范：用户于 2026-10-14 提供的第5课正文。初始代码是第4课单轮问答基线；以下是修复前状态。

| 范围 | 差异 |
|---|---|
| JWT | HS256/数据库回查已有；payload 多余声明，无 jti/吊销表，用 sessionStorage |
| Agent | 缺管理、技能/材料绑定、按班隐藏 |
| Skill | 缺文件解析、种子、CRUD/启停、lexical route |
| Conversation | 缺私有会话、锁Agent、消息落库、末6条历史 |
| 存储/检索 | SQLite 正文/向量；700/100切片；加权融合；缺MySQL/Qdrant、RRF、三种策略 |
| 编排 | 缺绑定范围、无依据会话回答、Agent/Skill提示词边界 |
| SSE | 非流式完整JSON，缺meta/delta/done/error及部分失败保存 |
| Swagger | 缺代码源文档与Try it out |
| 前端/apitest | 缺管理、会话、ReadableStream、URL分目录脚本与HTML报告 |

顺序：存储层 → 接口层 → 编排层 → SSE → Swagger → 前端。实际验收记录在 `docs/lesson5-verification.md`。
