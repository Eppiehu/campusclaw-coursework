# Design：班级范围检索与溯源

## Context

现有认证在 `app/auth.py` 中使用 Flask signed-cookie session。请求开始时应用核对 session 的用户、角色及班级是否与数据库一致。材料 API 和下载已按 `session["class_id"]` 过滤。

`knowledge_entries` 当前每份材料保存一条完整解析文本，并通过 `material_id` 关联 `materials`。`app/knowledge.py` 目前只有 UTF-8 文本解析。本变更在此基础上设计检索能力，不替换认证与主数据库。

## Goals / Non-Goals

### Goals

1. 教师、学生按关键词检索本班的知识片段。
2. 所有候选生成和来源访问都由服务器限定班级。
3. 每条结果可以定位到材料的确切原文片段并下载原文件。
4. 已有数据可重建索引，新材料可事务性更新索引。

### Non-Goals

- 生成式问答、聊天、Agent、跨班搜索、修改现有登录行为。
- 本轮强制部署向量数据库或接入外部 embedding API。
- 全语言语义理解和大规模检索集群。

## Decisions

### D1：必需版本采用 SQLite 关键词检索

保留 `data/app.db`，新增知识片段表。用参数化查询中的 `instr(search_text, :term) > 0` 进行字面匹配，不拼接 SQL、不使用用户输入作为 SQL/FTS 表达式。

- 输入和索引字段均用 Python `str.casefold()` 做匹配规范化，原文另行保存。
- 按空白拆分查询词，全部查询词必须匹配同一片段；无空白中文查询按一个连续短语匹配。
- 长度为 1～200 个 Unicode 字符，最多 20 个查询词。空白查询返回 400。
- `limit` 默认 5，允许整数 1～20，非法值返回 400。
- 排序依次为：完整查询短语命中优先、查询词出现次数之和降序、上传时间降序、材料 ID 升序、片段起点升序。
- 查询结果不足 limit 时只返回真实命中；无结果返回 200 与空数组。

这是可离线复现的关键词检索，不承诺同义词或语义问句召回。选择该方案是为降低本次作业的部署和验证成本；数据量增大或需要语义搜索时再启用向量适配器。

### D2：权限必须作用于候选生成

所有检索调用从验证后的 `session["class_id"]` 取得班级。SQL 候选查询同时约束材料与知识条目的班级：

```sql
SELECT c.*, k.material_id, m.title, m.original_filename
FROM knowledge_chunks AS c
JOIN knowledge_entries AS k ON k.id = c.knowledge_entry_id
JOIN materials AS m ON m.id = k.material_id
WHERE k.class_id = :session_class_id
  AND m.class_id = :session_class_id
  AND instr(c.search_text, :term) > 0;
```

多个查询词增加参数化 AND 条件。班级条件不得在排序或 LIMIT 后补做。客户端 query、JSON/body 中的 `class_id` 不参与权限决策。无权访问的片段或材料统一返回 404，不暴露另一班的标题、正文、路径或命中数量。

### D3：片段索引保留可重建的原文位置

新增 `knowledge_chunks`：

| 字段 | 类型/约束 | 用途 |
|---|---|---|
| id | TEXT PRIMARY KEY | 片段 UUID |
| knowledge_entry_id | INTEGER，外键 ON DELETE CASCADE | 关联完整知识文本 |
| chunk_index | INTEGER NOT NULL | 从 0 开始的片段顺序 |
| content | TEXT NOT NULL | 原文片段，不保存模型改写 |
| search_text | TEXT NOT NULL | content.casefold()，仅用于匹配 |
| start_char / end_char | INTEGER NOT NULL | Python Unicode 字符索引，左闭右开 |
| start_line / end_line | INTEGER NOT NULL | 原文中 1 起始的行号，含首尾 |
| text_sha256 | TEXT NOT NULL | 完整知识条目文本的 UTF-8 SHA-256 |

唯一约束 `(knowledge_entry_id, chunk_index)`；对 `knowledge_entries(class_id, material_id)`、`knowledge_chunks(knowledge_entry_id, chunk_index)` 建索引。片段不复制班级权威值，通过条目和材料 JOIN 得到所属班级。

分块优先在段落/行边界切分，每块最多 1000 个 Unicode 字符；超长行按字符数切分；无重叠、不丢失字符，按顺序拼接应等于原完整文本。分块读取已解析的 `knowledge_entries.content`，不再次改写换行或 BOM；因此 `content == full_text[start_char:end_char]`。匹配规范化不得改变溯源偏移。

原文件与解析文本分开处理：片段位置属于解码后的知识文本，不是文件字节偏移，也不是 PDF 页码。当前仅支持 `.txt`/`.md`。数据库保留原始上传文件，下载接口继续提供它。

### D4：检索 API 与 SSR 页面

- `GET /knowledge?q=...`：Jinja SSR 搜索页面；未登录 302 到 `/login`。
- `GET /api/knowledge/search?q=...&limit=5`：JSON；未登录 401。
- `GET /materials/<material_id>?chunk=<chunk_id>`：来源详情 SSR；检查材料和片段同时属于 session 班级，定位并高亮原文。片段必须确实属于该材料。
- `GET /api/knowledge/sources/<chunk_id>`：返回授权范围内的溯源数据；未登录 401，跨班/不存在 404。
- 原文件下载复用 `/materials/<material_id>/download`，不增加绕过权限的静态文件 URL。

检索响应示例（示例编号，不代表当前已实现接口；该示例条目全文就是 excerpt）：

```json
{
  "query": "登录",
  "results": [
    {
      "chunk_id": "example-chunk-id",
      "knowledge_entry_id": 1,
      "material_id": 1,
      "title": "A班演示材料",
      "original_filename": "A班演示材料.md",
      "excerpt": "登录成功后浏览器携带 session cookie。",
      "location": {"start_char": 0, "end_char": 26, "start_line": 1, "end_line": 1},
      "text_sha256": "c6fadc1fd3200de8e03497f65d391b557181eaca2a980223436eb6310381d23f",
      "source_url": "/materials/1?chunk=example-chunk-id",
      "download_url": "/materials/1/download"
    }
  ]
}
```

实际 location/hash 必须由每份真实原文计算，不能硬编码示例值。API 不返回内部文件路径。页面通过 Jinja 自动转义及文本节点渲染原文，不能执行上传材料中的 HTML/脚本。

### D5：索引与迁移的一致性

- 新上传流程在原有事务内插入 materials、knowledge_entries、knowledge_chunks；任一步失败全部回滚并删除本次文件。
- 提供幂等迁移/重建脚本；每个条目在单一事务内删除旧块并写入新块，失败恢复旧索引。
- 迁移不删除用户、材料、知识正文，不重新 seed 或重置 `data/app.db`。
- 尚未迁移的条目不会被伪装成已索引结果；迁移报告成功/失败数量，失败条目可以重试。
- 来源读取时校验 text_sha256 和原文切片；索引与正文不一致时不展示错误引用，返回 409，提示重建。

### D6：可选向量数据库方案

后续可增加 `search(class_id, query, limit)` 适配器，以本地 embedding + 向量库支持语义检索。SQLite 继续保存用户、材料、知识正文与来源关系，向量只保存索引。

向量记录至少包含 `chunk_id`、`material_id`、`class_id`、文本哈希、embedding 模型/版本；按班级 namespace/collection 隔离，并在向量候选生成时强制 metadata 班级过滤。返回候选后再与 SQLite 的材料、知识条目和当前 session 关联核验。不得先全库 top-k 再由前端过滤，不得在向量服务故障时退回不带班级条件的全库查询。

具体向量库、模型与维度在实施该可选方案前确定，配置从环境读取。模型/维度变更要重建索引；SQLite 与向量库不能假装共享事务，应设计持久化索引任务和重试。此项不列入本次必需实现任务。

## Risks / Trade-offs

- SQLite 字面匹配召回有限，中文无空格查询按短语处理；页面应说明搜索方式。
- 索引增加存储空间，既有 1 MB 上传限制继续生效；切块和迁移需要控制内存。
- 片段索引与正文变化可能导致溯源漂移，因此以哈希和原文切片校验。
- 多班相同关键词必须用 A/B 对照测试，防止误将客户端班级字段当作权限依据。

## Migration / Rollback

先备份数据库与 uploads → 创建新增表/索引 → 幂等回填片段 → 运行 A/B 隔离与溯源测试 → 启用检索入口。失败时关闭新增路由/入口并保留原材料功能；未确认新增数据安全前不删除表或原文件。

## Open Questions

暂无阻碍本次变更描述的问题。若第四课完整课件另有指定接口、分块算法或向量库，取得课件后先调整本方案再进入 Apply。
