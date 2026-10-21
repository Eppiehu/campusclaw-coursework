# 课堂照片补充与五项自验

日期：2026-10-21。范围来自用户提供的“应用平台”五项列表、完整验证照片及SKILL.md模板照片；五项验证仅用于实际测试，不增加验证页面。

## 正式阶段验收补充

按正式作业截图补齐首次初始化的内置多应用：MySQL初始化为每班创建数学学习助手、语文阅读助手，并分别绑定本班模板与内置技能；有一次性迁移标记，后续启动不覆盖教师编辑、停用与删除。相关2项初始化与隔离测试已通过。最终完整单元回归48/48、API回归31/31通过，未跳过。五项真实模型证据保持原始记录，完整请求/返回正文导出到`docs/evidence/20261021-llm-requests.json`，不含认证信息和模型推理正文。一个600 token上限截断的真实样例已在PDF中如实注明。

提交报告为`output/pdf/1021_CampusClaw_个人项目阶段性验收报告.pdf`，共7页，内嵌完整JSON证据。运行`python scripts/build_acceptance_report.py`可根据原始测试记录重建（文档生成额外需要reportlab与pypdf）。以下保留补充前后各阶段执行记录。

## 五项平台能力

| 能力 | 实现与入口 |
|---|---|
| AI应用 | /manage创建本班助手，/tutor选择启用应用并创建私有流式会话；既有会话锁定应用 |
| 提示词模板 | /manage独立创建、编辑、启停与删除；应用绑定模板后每轮实时读取并注入system；无有效模板时使用应用角色设定 |
| 知识库检索 | 保留MySQL正文和offset、Qdrant向量、三种检索与RRF；仅本班∩应用绑定材料∩可选subject过滤；最多4片，每片800字 |
| Skill技能 | 接受name/description的YAML头部加Markdown正文；兼容原中文字段格式；按绑定和启用过滤，再路由至多一个技能并注入正文 |
| 外部工具MCP | 独立stdio进程、真实初始化和工具发现、模型function tools映射、流式tool_calls组装、工具执行及role=tool回传后的下一轮模型回答 |

默认外部工具为有限四则运算计算器、北京时间。管理员可配置其他stdio MCP服务器及允许的工具名称。当前范围不包括远程HTTP MCP、MCP资源/提示词发现、任意脚本执行。

## 五项验证结果

以下均已实际运行真实DeepSeek、MySQL、Qdrant和独立MCP进程。外发范围已获用户明确同意，仅包含脚本新建的虚构历史教学材料、测试提示词、测试问题、模型自身历史回答与计算器结果。

| 验证 | 结果 | 实际核对 |
|---|---|---|
| 1. 每轮LLM参数、返回内容、模板传递 | PASS | 捕获实际POST body的model/messages/stream/temperature/max_tokens；模板完整进入system；保存上游原始SSE事件与最终回答，区分后处理后的内容 |
| 2. 绑定知识库后是否全量发送 | PASS | 构建超过4片的演示材料，确认本轮仅Top4检索片段进入user消息，整份材料未全量发送；另有跨班及未绑定材料泄露的自动断言 |
| 3. 绑定Skill后具体发送内容 | PASS | history-lab命中后，完整Markdown正文进入system；YAML的name/description用于元数据及路由，未将文件头和其他技能整体注入 |
| 4. Skill具体执行逻辑 | PASS | 同班候选→应用绑定→启用→描述/关键词评分→最高分且同分id小优先→注入正文→限定材料检索→模型生成；停用后下一轮不再命中。文件中的代码不被执行 |
| 5. MCP接入后模型的具体参数 | PASS | 第一轮tools仅calculator且tool_choice=auto；DeepSeek实际产生tool_calls；独立MCP执行(127+36)*8得到1304；第二轮messages包含assistant.tool_calls和role=tool结果，最终答案含1304 |

真实模型证据：`apitest/report/platform-live-evidence.json`。内部LLM_OBSERVER仅由显式验证脚本启用，常规请求不持久化调试记录，不存在公共调试接口。证据目录被Git忽略，未记录模型密钥、登录Token、数据库凭据或Authorization。

## 回归与运行限制

- PASS：新增10项标准技能、提示词模板权限、真实MCP进程、原始请求与响应、工具闭环与拒绝未绑定工具的测试。
- PASS：全套46项回归中，45项在默认环境通过；HTTP flush一项首次受沙箱本机网络权限阻挡，获得网络执行权限后单独重跑通过（首个delta早于模型完成）。原有认证、班级隔离、上传下载等测试通过。
- PASS：按URL组织的API回归29/29，HTML位于`apitest/report/index.html`。
- PASS：前端模块语法检查、UTF-8增量SSE解析器、Git空白检查。
- NOT RUN：浏览器实际按钮点击和视觉验收；Docker Compose构建/启动；Nginx部署。本次不把接口测试等同于浏览器点击测试。

## 本机向量存储修复

真实验收发现旧Qdrant在WSL挂载的NTFS目录读取payload时出现OutputTooSmall并返回500。保留了旧索引目录及配置备份，运行索引改到WSL Linux文件系统`/home/spark/.local/share/campusclaw/qdrant-20261021/`，端口仍6333，从MySQL正文重建向量。未删除原始材料或数据库正文。此项为本机环境修复；Compose仍使用已有qdrant_data命名卷。

## 重现

先安装requirements.txt并按README启动真实MySQL/Qdrant，设置.env，然后：

```text
python -m unittest tests.test_platform -v
python apitest/run_all.py
python scripts/verify_platform_live.py --live
node tests/test_sse_parser.mjs
```

live脚本会调用已配置的外部模型；普通自动回归使用模拟模型，MCP默认服务器仍为真实独立进程。
