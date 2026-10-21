# 第5课修复与验收记录

日期：2026-10-14。唯一规范：本次用户提供的第5课正文。先审计后修复，初始差异见 `lesson5-gap-audit.md`。

最终实际计数：全量 `unittest discover` **36/36 PASS**；按URL组织的 `apitest/run_all.py` **24/24 PASS**；Node SSE解析器 **PASS**；真实MySQL/Qdrant及显式DeepSeek smoke/scenarios **PASS**。最终测试没有FAIL。下面的NOT RUN保留为未完成的环境/浏览器验收，不能据此宣称全部视觉验收通过。

## 实现与依据

| 范围 | 当前实现 | 代码 |
|---|---|---|
| JWT | HS256，仅sub/jti/iat/exp；校验吊销表，按sub回数据库取role/class；登录换发与登出吊销；前端localStorage | `app/tokens.py`、`app/auth.py`、`app/__init__.py`、`app/static/auth.js` |
| 存储 | 标准运行强制MySQL；Qdrant保存向量/payload，同SQL chunk id。原SQLite文件保留为导入源，测试用隔离SQLite fixture | `app/db.py`、`scripts/init_mysql.py`、`app/vector_store.py` |
| Schema | token_revocations；tutor_agents；tutor_agent_skills/materials；conversations/messages；技能字段；chunk状态与策略 | `app/lesson5_schema.py` |
| Agent | 班内名称唯一≤64字，prompt≤2000字且空值fallback；教师管理绑定；学生仅见启用项；不可见同不存在404 | `app/tutor_api.py` |
| Skill | 单文本文件，字段/工具/正文严格解析，五个长度上限；数学和语文种子；每轮绑定与enabled交集内按词法路由 | `app/skill_files.py`、`app/tutor_api.py` |
| Conversation | 所有者与班级校验；创建须启用Agent；永久锁定id；停用Agent不影响旧会话；每轮读取实时绑定；首问前24字标题 | `app/conversation_flow.py` |
| 历史与Prompt | SQL只读末6条，空/非法role跳过，每条≤500字；system只有角色、Skill、约束、身份、dataBoundary；材料标题/正文在user，每片≤800字 | `app/conversation_flow.py` |
| 检索 | 800/80、auto/custom/hierarchy；keyword/vector各默认最多20；Qdrant class/material filter且cosine≥0.35；hybrid为RRF K=60；会话Top4 | `app/chunks.py`、`app/hybrid_search.py` |
| 无依据 | `/api/ask`不调用模型且固定文案；Conversation仍调用DeepSeek，citations为空且不输出[n] | `app/knowledge_api.py`、`app/chat_stream.py` |
| 真SSE | POST；meta最先；新增delta；assistant/citations/skill落库后done；首帧前真实HTTP错误；首帧后error；部分失败保存 | `app/conversation_api.py` |
| Swagger | 路由表+处理函数注解实时生成OpenAPI；本地Swagger UI，Bearer Auth | `app/api_docs.py`、`app/openapi.py` |
| 前端 | 教师文件/Agent管理、学生会话；fetch POST、response.body、ReadableStream解析，不用EventSource或计时播放 | `app/static/manage.mjs`、`app/static/tutor.mjs`、`app/static/sse.mjs` |
| apitest | URL目录、每接口脚本、HTML报告；自动模型mock；真实模型仅显式live脚本 | `apitest/` |

## 分层实际测试

| 层 | 已执行检查 | 状态 |
|---|---|---|
| 存储 | SQLite fixture迁移/种子幂等、三种切片偏移、RRF、向量id和过滤；另用真实MySQL 8.4.11/Qdrant 1.15.5运行keyword/vector/hybrid和跨班检查 | PASS |
| 接口 | JWT核心声明、换发/登出吊销、文件错误拒绝、Agent/Skill写权限、会话私有性与404一致 | PASS |
| 编排 | 绑定实时生效、subject交集、锁Agent、末6条/500字、空prompt fallback、标题规则 | PASS |
| SSE | meta首帧、多段新增delta、落库后done、部分/零内容失败；真实本机HTTP在上游完成前收到delta | PASS |
| Swagger | 真实路由覆盖、Bearer定义、本地UI资源200、按文档地址携Bearer执行请求 | PASS |
| 前端代码 | 页面路由/权限、JavaScript语法、SSE解析器UTF-8逐字节拆包、CRLF/LF及多帧 | PASS |
| 浏览器视觉/点击 | Computer Use无法可靠识别当前浏览器URL，安全检查中止。未完成浏览器逐段显示或Swagger按钮点击 | NOT RUN |
| Docker Compose | 本机无docker命令。便携服务集成结果不替代容器构建/启动验收 | NOT RUN |
| Nginx | 当前应用直接运行，配置样例已提供；未实际部署Nginx | NOT RUN |

## 课件八个场景

1. **PASS**：正常教师API创建数学、语文两个Agent，各自绑定不同种子Skill与本班材料；学生接口只返回enabled项。演示数据由 `scripts/prepare_lesson5_demo.py` 幂等准备，不在回答代码中写答案。
2. **PASS**：数学Agent问语文题，不路由语文Skill，来源没有未绑定语文材料。自动断言及真实DeepSeek场景均执行。
3. **PASS**：创建选择Agent A，发送消息body传B，会话数据库agent_id仍为A；真实场景执行。
4. **PASS**：数学解题引导启用时只给检查提示；停用/解绑后下一轮立即不路由该Skill。mock验证输出边界，真实模型验证停用前后回答不同；测试后恢复种子Skill启用。
5. **PASS**：真实DeepSeek在无绑定资料情况下仍回答，meta citations=[]、正文无[n]，多个delta与最终数据库正文一致。
6. **PASS**：真实有依据回答包含引用；meta/DB来源有title、chunk_index、offset，编号仅落在当前来源集合。
7. **PASS（HTTP和解析器）/ NOT RUN（浏览器视觉）**：线上的真实POST响应分段发送，HTTP flush测试证明首个delta早于上游完成；浏览器界面因工具安全检查未实测。
8. **PASS（接口与Swagger资源）/ NOT RUN（浏览器Try it out点击）**：OpenAPI从实际处理函数生成并实际调用对应URL；没有把HTTP测试记作浏览器点击通过。

## 运行命令与报告

```text
python -m unittest discover -s tests -v
node tests/test_sse_parser.mjs
python apitest/run_all.py
python scripts/verify_storage_live.py --live
python apitest/live_smoke.py --live
python apitest/live_scenarios.py --live
```

HTML报告：`apitest/report/index.html`，已被Git忽略；summary.json保存实际计数。正式环境MySQL/Qdrant走Compose；本次无Docker时使用项目忽略目录下的官方便携服务。Qdrant在WSL/NTFS验收目录报告文件系统安全提示，因此这次结果仅证明功能集成，不构成生产存储耐久性验收。

浏览器仍需人工补验：打开`/login`重新登录，教师在`/manage`查看两个演示Agent；学生在`/tutor`新建会话提问，Network选POST messages观察meta/delta/done；在`/swagger`用login获取Token，再Authorize后Try it out。
