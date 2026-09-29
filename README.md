# CampusClaw · 课程项目

## 第四课：OpenSpec 变更描述

本次变更：**限定班级范围的知识库检索，支持内容溯源**。

变更目录：[`openspec/changes/add-class-scoped-knowledge-search/`](openspec/changes/add-class-scoped-knowledge-search/)

- [proposal.md](openspec/changes/add-class-scoped-knowledge-search/proposal.md)：变更动机、范围和影响。
- [design.md](openspec/changes/add-class-scoped-knowledge-search/design.md)：SQLite 检索、片段结构、来源定位、迁移与可选向量库方案。
- [检索规范](openspec/changes/add-class-scoped-knowledge-search/specs/class-knowledge-search/spec.md)：登录、服务器端班级过滤、排序、输入限制、索引一致性。
- [溯源规范](openspec/changes/add-class-scoped-knowledge-search/specs/knowledge-source-traceability/spec.md)：原文片段、字符范围、行号、哈希、来源页和原文件下载。
- [tasks.md](openspec/changes/add-class-scoped-knowledge-search/tasks.md)：后续 Apply 的实施与验收清单。

**状态：变更描述完成，检索功能尚未实现。** 文档中的接口与参数是基于本次作业基本要求提出的方案。必需版本使用 SQLite 关键词检索；向量数据库作为可选扩展，不替换现有 Flask/SQLite 业务后端。

2026-09-29 使用官方 OpenSpec CLI 1.13.2 实际执行并通过：

```text
openspec validate add-class-scoped-knowledge-search --strict --no-interactive
Change 'add-class-scoped-knowledge-search' is valid
```

以下为已经实现的第二课系统说明。

按《互联网软件开发技术与实践》第 2 课提供的规约实现：Flask 3 + SQLite 3 + Flask signed-cookie session + Docker Compose。范围限于登录、教师/学生角色、A/B 班隔离、教师上传 `.txt`/`.md` 并写入知识库表、`/health`。

## 项目结构

```text
campusclaw/
├── app/
│   ├── __init__.py        # Flask 配置与健康检查
│   ├── auth.py            # 登录、登出、身份校验
│   ├── db.py              # SQLite 连接
│   ├── knowledge.py       # UTF-8 文本解析
│   ├── materials.py       # 班级查询、上传、下载
│   ├── static/
│   └── templates/
├── scripts/init_db.py    # 表结构与演示数据
├── tests/
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── .env.example
└── requirements.txt
```

运行后生成 `data/app.db` 和 `uploads/`，这两个目录不提交。没有预先存在的项目密码，因此演示初始化密码是：

| 用户名 | 密码 | 身份 | 班级 |
|---|---|---|---|
| `teacher_a` | `Teacher123!` | 教师 | A 班 |
| `student_a1` | `Student123!` | 学生 | A 班 |
| `student_b1` | `Student123!` | 学生 | B 班 |

数据库只保存 Werkzeug 生成的 `password_hash`，不保存明文密码。演示密码仅用于本地课程作业。可在首次初始化前通过 `DEMO_TEACHER_PASSWORD` 和 `DEMO_STUDENT_PASSWORD` 环境变量修改。

## Docker Compose 启动

在本目录执行：

```powershell
Copy-Item .env.example .env
$key = python -c "import secrets; print(secrets.token_hex(32))"
(Get-Content .env) -replace '^SECRET_KEY=.*$', "SECRET_KEY=$key" | Set-Content .env
docker compose up --build -d
docker compose ps
curl.exe -i http://localhost:8080/health
```

如果 `python` 不在 PATH，请使用已安装的 Python 绝对路径生成密钥。`SECRET_KEY` 必须通过 `.env` 环境变量提供；空值会使应用拒绝启动。打开 <http://localhost:8080/login>。首次启动自动初始化 `data/app.db`；`docker compose down` 后再次启动保留数据。

当前机器如果没有 Docker，可用本地 Flask 开发服务器预览（正式作业的标准启动仍为上面的 Compose）：

```powershell
python -m pip install -r requirements.txt
python scripts/init_db.py
$env:SECRET_KEY = ((Get-Content .env | Where-Object { $_ -like 'SECRET_KEY=*' }) -split '=',2)[1]
python -m flask --app 'app:create_app()' run --host 127.0.0.1 --port 8080
```

## 作业截图与 HTTP 证据

### 1. 教师登录后的首页

浏览器打开 <http://localhost:8080/login>，使用 `teacher_a / Teacher123!` 登录。截图 `/materials` 页面，顶部同时显示 `teacher_a`、`教师`、`A班`，左栏有 `A班演示材料`。

### 2. 登录请求、响应及完整 HTTP 响应

Chrome 按 F12 → Network，勾选 Preserve log，再提交登录表单。选择 `POST http://localhost:8080/login`：

- Method: `POST`
- Request `Content-Type`: `application/json`
- Request Payload：`{"username":"teacher_a","password":"Teacher123!"}`
- 成功状态：`200 OK`；Response `Content-Type: application/json`
- Response Body：`{"username":"teacher_a","role":"teacher","class_id":"A"}`；关键响应头：`Set-Cookie: session=...; HttpOnly; Path=/; SameSite=Lax`
- `Set-Cookie` 中的 `session` 值由 Flask 签名；其值每次可能不同。

在 PowerShell 中打印完整响应头（`curl.exe` 避免 `curl` 别名）：

```powershell
curl.exe -i http://localhost:8080/login -H 'Content-Type: application/json' --data-binary '{"username":"teacher_a","password":"Teacher123!"}'
```

命令行会包含密码，课程演示环境使用后请清理终端历史；正式环境不要使用该演示密码。
浏览器页面通过 `fetch` 发送 JSON，收到 200 后再跳转 `/materials`；原有 form 编码请求仍兼容并返回 302。

### 3. 登录后获取材料时识别当前用户

登录后在 `/materials` 页面点击底部“获取本班材料 API”。在 Network 选择 `GET http://localhost:8080/api/materials`，在 Request Headers 中截取 `Cookie: session=...`，在 Response/Preview 中截取 `current_user` 与材料列表。登录请求的 Response Headers 中截图 `Set-Cookie: session=...`。

流程：`POST /login` 校验哈希 → Flask 在签名 session 中写入 `user_id`、`role`、`class_id` → 浏览器保存 `session` cookie → 后续请求自动携带 `Cookie` → Flask 验证签名 → 服务端读取 session 并核对数据库用户 → SQL `WHERE class_id = 当前用户 class_id`。即使请求带 `?class_id=B`，服务端也不使用它。

本地验证篡改查询参数：

```powershell
curl.exe -c cookies.txt -X POST http://localhost:8080/login -d "username=student_a1&password=Student123!"
curl.exe -b cookies.txt "http://localhost:8080/api/materials?class_id=B"
```

第二条响应仍只含 A 班材料。

## 验收命令

```powershell
python -m unittest discover -s tests -v
python scripts/verify_live.py
docker compose ps
docker compose logs --tail=100 app
curl.exe -i http://localhost:8080/health
```

## 当前环境验收记录

2026-09-23 本地测试：`python -m unittest discover -s tests -v` 为 **PASS（11/11）**；JSON 登录实测返回 200、指定 JSON 字段及 `Set-Cookie`，带 Cookie 访问 `/materials` 返回 200，失败返回 JSON 401。运行中的 Flask 服务通过 `python scripts/verify_live.py` 逐项 HTTP 验收 **PASS（14/14）**，涵盖原有 form 登录、班级隔离、txt/md 上传、PDF 拒绝、学生 403、同班下载与跨班拒绝、健康检查。Docker build 与 Compose 启动为 **NOT RUN**：当前主机未安装/未提供 `docker` 命令，执行 `docker compose build` 报命令不存在，容器构建没有开始。容器持久化测试因此也是 **NOT RUN**。
