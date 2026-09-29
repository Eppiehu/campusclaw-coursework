# 第四课变更：限定班级范围的知识库检索与内容溯源

## Why

CampusClaw 已将教师上传的 `.txt`、`.md` 材料解析到 `knowledge_entries`，但目前只能逐份查看材料，无法按问题中的关键词定位知识片段，也没有检索结果到原文位置的溯源链路。

本变更依据本次作业提供的要求编写：限定班级范围的知识库检索、支持内容溯源、可考虑向量数据库。接口、分块参数和存储选择是本项目的设计方案，不作为未提供的第四课课件原文。

## What Changes

- 新增班级知识库检索页面与 API。教师和学生只检索自己所属班级的材料。
- 检索范围由服务器从已验证的 `session["class_id"]` 取得；忽略客户端提交的 `class_id`。
- 为解析后的知识文本建立片段索引，返回命中原文、材料标题、原文件名、片段编号和原文位置。
- 新增来源详情页，展示完整原文并定位命中片段；原文件下载复用现有权限检查。
- 为已有材料提供不丢失数据的索引迁移；新上传材料与知识条目、片段在同一 SQLite 事务内写入。
- 必需版本采用 SQLite 关键词检索。设计保留向量检索适配位置，向量数据库不作为本次最低验收的依赖。

## Capabilities

### New Capabilities

- `class-knowledge-search`：受登录与班级权限约束的知识片段检索、排序、参数校验和索引维护。
- `knowledge-source-traceability`：检索片段到知识条目、材料原文和原文件的可验证溯源。

### Modified Capabilities

无已归档规范需要修改。现有登录、角色、材料权限及上传事务在实现时继续保留；新增能力的约束在本变更的 delta specs 中说明。

## Impact

- 保持 Python、Flask 3.x、Jinja SSR、SQLite、signed-cookie session、`data/app.db`、Compose 8080。
- 预计修改 `app/knowledge.py`、应用路由注册、材料上传、Jinja 模板、数据库迁移及测试。
- SQLite 新增片段表及索引；已有 `users`、`materials`、`knowledge_entries` 数据保留。
- 不增加聊天、生成式问答、跨班管理员检索或自动调用外部模型的功能。
- 当前提交阶段是 OpenSpec 变更描述；检索功能尚未实现，不能将文档验收通过称为业务测试通过。
