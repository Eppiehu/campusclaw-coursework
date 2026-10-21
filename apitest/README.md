# 第5课接口验收

`cases/` 按真实 URL 分目录，一个接口一个 `case.py`。脚本核对 JSON、权限边界和数据库，不仅检查状态码；跨接口场景复用 `tests/` 中同一组断言，避免维护两份漂移的测试。

运行 `python apitest/run_all.py`，HTML 写入 `apitest/report/index.html`（已忽略 Git）。自动用例使用隔离的 SQLite fixture、Qdrant 测试替身和 DeepSeek mock；包括真实本机 HTTP flush 测试，但不使用真实付费模型。

生产存储单独运行 `python scripts/verify_storage_live.py --live`。真实模型单独运行 `python apitest/live_smoke.py --live`，需事先启动服务并配置环境变量，绝不由 `run_all.py` 自动触发。

双Agent有依据与Skill启停的真实模型场景：先 `python scripts/prepare_lesson5_demo.py`，再显式 `python apitest/live_scenarios.py --live`。真实模型调用会产生费用；场景测试结束后恢复种子Skill启用。

2026-10-21补充的五项课堂验证：`python scripts/verify_platform_live.py --live`。该脚本读取本地.env，在真实MySQL/Qdrant中创建专用虚构材料、模板、技能和会话，仅将这些演示数据发送至配置好的DeepSeek；真实调用独立MCP进程。结束后清理本次创建的数据，原始请求body、上游SSE事件与最终答案写入被Git忽略的`report/platform-live-evidence.json`，不保存Authorization或密钥。新增模板/MCP接口用例同样在cases/中按URL组织。五项验证不增加产品验证页面。
