## ADDED Requirements

### Requirement: Authenticated class-scoped retrieval
The system SHALL 从已验证的 Flask session["class_id"] 取得检索范围，并在候选查询阶段限制材料和知识条目同时属于该班级。教师和学生均可检索本班知识，不得使用客户端传入的 class_id 授权。

#### Scenario: A-class user searches a shared keyword
- **GIVEN** A/B 班材料都包含关键词“登录”
- **WHEN** 已登录 A 班用户检索“登录”
- **THEN** 候选、排序和返回结果仅来自 A 班，响应不含 B 班标题、正文、文件名或命中统计

#### Scenario: B-class student retrieves own-class content
- **GIVEN** student_b1 属于 B 班且已登录
- **WHEN** 该用户检索 B 班材料中的独有关键词
- **THEN** 返回 B 班命中片段，不返回 A 班内容

#### Scenario: Client attempts to change the class scope
- **GIVEN** 当前 session 中 class_id 为 A
- **WHEN** 客户端通过 query 或 body 提交 class_id=B
- **THEN** 系统忽略客户端班级字段，继续仅检索 A 班

#### Scenario: Anonymous request
- **WHEN** 未登录用户请求 /api/knowledge/search
- **THEN** 返回 HTTP 401，且不包含任何班级知识内容

#### Scenario: Anonymous page request
- **WHEN** 未登录用户请求 /knowledge
- **THEN** 返回 HTTP 302 到 /login，不呈现知识片段

### Requirement: Literal keyword search and deterministic ranking
The system SHALL 提供 UTF-8 文本片段的字面关键词检索，按空白拆词、casefold 匹配且所有词必须在同一片段中命中。系统 SHALL 使用参数化查询，并按完整短语命中、词频、材料上传时间、材料 ID、片段偏移给出稳定排序。

#### Scenario: Chinese phrase retrieval
- **GIVEN** 本班片段包含连续短语“会话签名”
- **WHEN** 用户以“会话签名”检索
- **THEN** 返回包含该原文短语的片段，而不要求用户先拆分汉字

#### Scenario: Multiple keyword retrieval
- **GIVEN** 本班片段同时含有“Flask”和“session”
- **WHEN** 用户检索“flask session”
- **THEN** 匹配忽略字母大小写，只有同时包含两个词的片段进入结果

#### Scenario: Query contains SQL or wildcard characters
- **WHEN** 查询包含引号、百分号、下划线或 SQL 语句片段
- **THEN** 查询被当作字面关键词，不执行输入内容，不改变班级过滤或 SQL 结构

#### Scenario: No match
- **WHEN** 有效查询在当前班级没有命中
- **THEN** API 返回 HTTP 200 和 results=[]，页面显示无结果，不扩大搜索到其他班级

### Requirement: Search input and result bounds
The system SHALL 接受长度 1～200 的非空白查询、最多 20 个词以及默认 5、范围 1～20 的整数 limit；非法参数 SHALL 返回 400。结果数量 SHALL 不超过 limit。

#### Scenario: Empty or oversized query
- **WHEN** q 缺失、仅空白、超过 200 个 Unicode 字符或超过 20 个词
- **THEN** API 返回 HTTP 400 和 JSON 错误，不执行知识检索

#### Scenario: Invalid limit
- **WHEN** limit 不是整数或不在 1～20 内
- **THEN** API 返回 HTTP 400

#### Scenario: Result limit
- **GIVEN** 本班有超过 5 个命中片段
- **WHEN** 用户未指定 limit
- **THEN** 最多返回排名前 5 个本班片段，重复请求的固定数据排序一致

### Requirement: Consistent chunk indexing and migration
The system SHALL 为知识正文建立包含原文内容、片段顺序、字符范围、行号及文本哈希的索引。新增材料、知识条目和片段 SHALL 在同一事务内写入。已有数据的迁移 SHALL 幂等且不删除原数据。

#### Scenario: Teacher uploads new text material
- **WHEN** 本班教师成功上传受支持的 txt 或 md 文件
- **THEN** 材料、知识条目和片段同时提交，新正文立即能被本班检索，其他班不能检索

#### Scenario: Chunk generation or database write fails
- **WHEN** 上传后的解析、分块或数据库写入失败
- **THEN** 事务回滚，本次文件被清理，不产生孤立材料、条目或片段

#### Scenario: Repeat existing-data migration
- **GIVEN** 已有条目的片段已经生成
- **WHEN** 再次执行迁移或重建
- **THEN** 不产生重复片段，不删除用户或原材料，片段数量和顺序保持一致

### Requirement: Preserve existing application behavior
The system SHALL 保留 Flask signed-cookie session、现有 JSON/form 登录兼容、上传角色权限和班级下载权限，以及 SQLite/Compose 8080 部署方式。

#### Scenario: Student attempts upload after search feature is added
- **WHEN** 已登录学生向材料上传接口提交 txt 文件
- **THEN** 返回 403，文件、材料、知识条目和片段均无新增

#### Scenario: Existing login and material access
- **WHEN** 用户使用 JSON 登录成功并访问本班材料
- **THEN** 登录返回 JSON 200、设置 HttpOnly/SameSite=Lax session cookie，既有材料访问正常
