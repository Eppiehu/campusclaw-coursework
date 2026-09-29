# Acceptance criteria

1. A/B 班与 `teacher_a`、`student_a1`、`student_b1` 存在，A/B 各有一条可区分的演示材料；用户表只有密码哈希。
2. 正确密码登录后 session 有 `user_id`、`role`、`class_id`；错误密码无有效 session；登出清除 session。
3. 未登录 `/materials` 返回 302 到 `/login`，未登录 `/api/materials` 返回 401。
4. A 班只能看到 A 班资料，修改查询参数或表单中的 `class_id` 无效；跨班详情/下载返回 404。
5. 学生上传返回 403 且无数据库/文件副作用。教师上传 `.txt`/`.md` 后材料与知识库同时有记录，解析失败无孤立数据。
6. `/health` 返回 JSON 200；Compose 对外提供 8080 并通过健康检查。
