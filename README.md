# CampusClaw Nexus 与课程平台

Nexus 是本仓库中的教学业务升级版：Flask + Vue 3、PostgreSQL/pgvector、LangGraph、MCP Python SDK、Redis/RQ。新增知识缺口审核回补、同纲不同卷、异步批改与学情周报；通过 `CAMPUSCLAW_EDITION=nexus` 启动。原课程版入口和数据保留。

- [Nexus 运行与隔离 Docker 部署](docs/nexus-running.md)
- [Nexus 实施与验收范围](docs/nexus-implementation-plan.md)
- [Nexus 实测记录](docs/nexus-verification.md)
- [Nexus OpenSpec 变更](openspec/changes/nexus-teaching-workflows/proposal.md)
- API 文档：Nexus 运行后的 `/api/nexus/openapi.json`

## 课程版记录

以用户提供的《第5课：提示词、AI技能与流式会话》正文为基础，按2026-10-21补充的课堂照片加入可复用提示词模板、标准SKILL.md及MCP外部工具。

- [修复前差异表](docs/lesson5-gap-audit.md)
- [逐层验收与场景记录](docs/lesson5-verification.md)
- [API 测试说明](apitest/README.md)
- [五项课堂验证及本次补充](docs/platform-supplement-verification.md)
- [阶段性验收PDF（2026-10-24，13页12张实际截图）](output/pdf/CampusClaw_阶段性验收报告_截图版.pdf)
- [截图版完整LLM/MCP请求与返回证据](docs/evidence/20261024-llm-requests.json)
- [原始截图与校验清单](output/screenshots/20261024/)
- [个人项目阶段性验收PDF](output/pdf/1021_CampusClaw_个人项目阶段性验收报告.pdf)
- [实际LLM请求与返回证据](docs/evidence/20261021-llm-requests.json)

## 标准运行方式

运行后端仍为 Python + Flask；Jinja 页面保留 Flask signed-cookie Session。第5课运行要求 MySQL，正文、offset、状态在 SQL，向量及 class_id/material_id payload 在 Qdrant。SQLite 仅作隔离回归 fixture 和旧课程数据导入源，应用正式运行不会静默退回 SQLite。

复制 `.env.example` 为 `.env`，填写随机 SECRET_KEY、MYSQL_PASSWORD、MYSQL_ROOT_PASSWORD、OPENAI_API_KEY；密钥不进 Git。Compose 自动配置容器内 DATABASE_URL 和 QDRANT_URL：

```powershell
docker compose up --build -d
```

外部端口仍为 8080。首次 MySQL 初始化会复制存在的 `data/app.db` 中的班级、用户、材料和知识条目，保留原 SQLite 文件；只迁移到空用户库。第5课切片迁移幂等执行一次，改为800/80，Qdrant索引按SQL chunk id建立。

当前机器未安装 Docker。本次实际验收额外在项目忽略目录 `_tools/services` 使用官方便携 MySQL 和 Qdrant，经 WSL 运行；本地 `.env` 指向 MySQL回环端口3316、Qdrant6333。旧NTFS向量索引在重启后出现读取错误，已保留旧目录，并在WSL的Linux文件系统新建运行索引、从MySQL正文重建。Docker Compose构建/启动仍需单独验收。

不通过 Compose 运行时，先准备 MySQL/Qdrant并设置 DATABASE_URL，再执行：

```powershell
python -m pip install -r requirements.txt
Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $parts = $_ -split '=',2; [Environment]::SetEnvironmentVariable($parts[0],$parts[1],'Process') }
python scripts/init_mysql.py
python -m flask --app 'app:create_app()' run --host 127.0.0.1 --port 8080
```

## 入口与账号

- `/login`：登录；`/materials`：材料；`/knowledge`：第4课单轮检索/问答。
- `/manage`：教师管理提示词模板、技能文件、AI应用及材料/技能/MCP工具绑定。
- `/tutor`：选择本班启用Agent，创建私有会话并流式提问。
- `/swagger`：本地Swagger UI；`/openapi.json`：由注册路由与处理函数注解生成。

全新MySQL初始化后，每班自动内置“数学学习助手”和“语文阅读助手”，分别绑定本班对应提示词模板和内置解题引导技能；材料由教师自行选择。初始化幂等，后续启动不会覆盖教师的修改、停用或删除。

| 用户 | 演示密码 | 角色/班级 |
|---|---|---|
| teacher_a | Teacher123! | 教师/A |
| student_a1 | Student123! | 学生/A |
| student_b1 | Student123! | 学生/B |

## JWT 与权限

JWT使用HS256，只包含 `sub/jti/iat/exp`，有效期30分钟。每次API认证都检查吊销表，再按sub查询数据库，取得当前role/class_id。前端使用localStorage和Bearer请求头；API fetch不发Cookie。重新登录时携带旧Token，服务端吊销其尚未过期的jti后签发新Token。登出写入token_revocations并清除前端Token及Session。

跨班/不存在Agent、Skill、他人或他班Conversation使用相同404；学生写教师接口403；Search显式跨班参数返回200和空hits。

## 技能、Agent与会话

Skill是单一UTF-8 `.txt`/`.md` 文件。标准格式与课堂照片一致，YAML头部仅含name和description，第二个---后是Markdown正文：

```markdown
---
name: history-lab
description: 当用户需要设计历史探究课程、进行史料研读时使用
---

# 历史探究实验室

## 重要提示
先询问教学对象与历史主题，再设计史料研读活动。
```

`demo/history-lab/SKILL.md`采用照片中的名称和描述；照片未展示的正文由本项目编写，文件已注明。description用于确定性关键词路由；命中后仅将完整Markdown正文注入system，头部及其他候选技能不整体发送。中文描述使用去重二字词、英文单词匹配，排除部分通用词；该路由不调用LLM，也不执行文件中的代码。名称最多32字，描述与正文分别最多2000字，整文件最多8000字。

兼容原中文格式，原有路由规则和种子不变：

```text
名称：数学解题引导
适用条件：数学,方程,计算,几何
资料：数学
工具：knowledge_search
启用：是

只指出学生错在哪一步、下一步检查什么，不给最终答案、选项、得数或完整过程。
```

严格拒绝重复/未知字段、缺必填/正文及非法工具；限制8000/32/120/2000/32字。提供数学、语文解题引导种子。候选技能仅取本班、当前Agent已绑定且enabled；关键词按课件分隔符切分，lowercase substring每个计1分，同分id小者优先，0分不选，最多一个。

Agent名称最多64字、班内唯一；prompt最多2000字，空值使用默认角色。创建会话只能选择本班启用Agent；会话agent_id锁定。已有会话可继续使用后来停用的Agent，但每轮重新读取其当前技能/材料绑定。标题从“新的提问”改为首个问题前24字，后续只更新时间。

提示词模板按班级独立管理，支持创建、编辑、启停、删除及多个Agent复用。Agent绑定启用模板时，每轮从数据库读取模板正文作为角色提示；模板停用则回退到Agent自己的prompt。跨班绑定404，学生写操作403，仍有绑定的模板删除409。

## MCP外部工具

`/manage`可为每个AI应用选择MCP工具；`GET /api/mcp/tools`实际进行初始化和工具发现。默认工具在独立stdio进程中提供`calculator`和`current_time`，支持MCP `2025-06-18`的initialize、initialized、tools/list及tools/call。协议依据：[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[工具协议](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。

模型请求仅携带当前Agent所绑定工具的名称、描述和JSON Schema。DeepSeek流式返回tool_calls后，后端检查绑定、参数Schema和数量，再向MCP发送tools/call；结果作为role=tool写入下一次模型请求，继续流式回答。最多3轮模型请求、每轮4次工具调用；末轮禁止继续调用。未绑定工具会被拒绝。MCP工具进程不继承模型密钥、数据库凭据或用户Token。

默认计算器只解析有限长度的数字四则运算；没有eval、任意代码执行、文件访问或网络访问。管理员可通过`.env`的`MCP_SERVER_COMMAND`配置其他stdio服务器（JSON命令参数数组），并用`MCP_ALLOWED_TOOLS`指定允许开放的名称。当前未实现远程HTTP MCP或网页编辑服务器命令。

## 检索与提示词

默认800字符、80重叠，支持auto/custom/hierarchy；offset对应原文且end不包含。keyword/vector各最多SEARCH_MAX_RESULTS（默认20）；Qdrant使用班级和材料filter，Cosine阈值0.35。Hybrid用RRF：每个排名贡献 `1/(60+rank)`，不再加权原始分数。

会话检索取“当前用户班级 ∩ Agent绑定材料 ∩ 命中Skill的subject_text标题过滤”，最终最多4个非空chunk，引用连续编号。向量使用本地BAAI/bge-small-zh-v1.5，聊天沿用DeepSeek兼容接口。

System仅组装Agent角色、Skill说明、资料约束、模型身份和dataBoundary。检索标题和正文放在user数据消息，每片最多800字。历史仅读末6条，正文截取500字，只允许user/assistant并跳过空正文或非法role。

第4课 `/api/ask`（兼容`/api/knowledge/ask`）无依据时不调用模型；第5课Conversation无依据仍调用模型，citations为空且输出不含[n]引用。

## 真流式SSE

`POST /api/conversations/{id}/messages` 返回text/event-stream：首帧meta（skill、citations）→ 多个新增delta → assistant、citations、skill_name成功落库后的done。首帧前使用真实HTTP错误码，首帧后失败发送error；部分内容失败仍保存。前端用fetch POST、response.body和ReadableStream解析SSE，不用EventSource或整段答案逐字动画。

Response设置X-Accel-Buffering:no、Cache-Control:no-cache、Connection:keep-alive。可选Nginx样例在`deploy/nginx.conf`；标准Compose当前直接暴露Gunicorn。

## 测试

```powershell
python -m unittest discover -s tests -v
node tests/test_sse_parser.mjs
python apitest/run_all.py
```

apitest按URL组织，HTML报告写入`apitest/report/index.html`且不进Git。自动用例的DeepSeek全部mock；Qdrant测试替身仅在TESTING中可注入。真实存储、真实模型分别显式开启：

```powershell
python scripts/verify_storage_live.py --live
python apitest/live_smoke.py --live
```

实际结果及NOT RUN项目见验收记录。`openspec/`和`output/pdf/`保留此前课程材料，不作为第5课规范。
