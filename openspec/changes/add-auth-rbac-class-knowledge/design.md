# Design

- Web：Flask 3 + Jinja SSR；SQLite 数据文件 `data/app.db`。
- 认证：Werkzeug 密码哈希；Flask signed-cookie session，包含 `user_id`、`role`、`class_id`；Cookie 为 `HttpOnly`、`SameSite=Lax`。
- 权限：`login_required` 处理页面 302/API 401；材料查询始终以服务器端 session 用户所属班级过滤；教师上传，学生上传返回 403。
- 上传：multipart/form-data，限制 1 MB 和 `.txt`/`.md`，文件保存在 `uploads/{class_id}/{uuid}_{safe_filename}`，UTF-8 解析后在同一 SQLite 事务中写入 `materials` 与 `knowledge_entries`。失败回滚并删除文件。
- 部署：Compose 映射 8080，挂载 `data`/`uploads`，首次启动自动初始化，`/health` 检查数据库。
