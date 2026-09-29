## ADDED Requirements

### Requirement: Verifiable retrieval provenance
Each search result SHALL 包含真实的 chunk_id、knowledge_entry_id、material_id、材料标题、原文件名、原文摘录、字符范围、行号、文本 SHA-256，以及来源页和受保护下载链接。excerpt SHALL 来自实际知识原文，不能由模型生成或改写。

#### Scenario: Inspect a search result
- **GIVEN** 当前班级的某知识片段命中查询
- **WHEN** 系统返回检索结果
- **THEN** 所有来源 ID 可关联到同一份授权材料，原文摘录等于知识正文的 [start_char:end_char] 切片，text_sha256 与完整正文相符

#### Scenario: Material has a long line or Chinese text
- **WHEN** 系统分块并索引中文或超过分块上限的长行
- **THEN** 字符范围使用 Python Unicode 字符索引，行号从 1 开始，无字符丢失或偏移误用为字节偏移

### Requirement: Authorized source navigation
The system SHALL 提供来源全文页与片段来源 API，访问前核对用户登录状态、材料班级、知识条目班级、片段与材料关系。跨班或不存在的来源 SHALL 统一返回 404。

#### Scenario: User follows own-class source link
- **WHEN** 已登录用户打开本班命中片段的 source_url
- **THEN** 来源页显示原材料完整知识正文并定位命中范围，标题及片段与检索结果一致

#### Scenario: User guesses another-class chunk ID
- **GIVEN** A 班用户已登录
- **WHEN** 该用户访问 B 班片段的来源 API 或来源页
- **THEN** 返回 404，不包含 B 班标题、正文、原文件名或内部文件路径

#### Scenario: Chunk belongs to a different material
- **WHEN** 用户将 material_id 与不属于该材料的 chunk_id 拼接到来源 URL
- **THEN** 返回 404，不错误引用另一份材料

#### Scenario: Anonymous source access
- **WHEN** 未登录用户访问来源 API
- **THEN** 返回 401；来源页面访问重定向到 /login

### Requirement: Protected original-file download
The system SHALL 复用现有材料下载接口并检查 session 班级。检索结果 SHALL 不提供可绕过鉴权的 uploads 静态路径。

#### Scenario: Download original source material
- **WHEN** 已登录用户点击本班检索结果的 download_url
- **THEN** 返回该材料的原上传文件，而非生成的摘要或片段文件

#### Scenario: Cross-class or anonymous download
- **WHEN** A 班用户下载 B 班材料或未登录用户请求下载
- **THEN** 跨班请求返回 404，未登录请求跳转 /login，不返回原文件字节

### Requirement: Detect stale provenance and safely render text
The system SHALL 在来源读取时校验正文哈希与片段切片，索引失效时返回 409 而非呈现错误引用；页面 SHALL 转义原文内容，不执行上传材料中的脚本。

#### Scenario: Knowledge text no longer matches indexed source
- **GIVEN** 片段索引保存的哈希或字符切片与知识正文不一致
- **WHEN** 用户访问该片段来源
- **THEN** 返回 HTTP 409 并提示重建索引，不展示过期高亮或虚假来源

#### Scenario: Source contains HTML or JavaScript
- **WHEN** 命中原文包含 script 标签、HTML 属性或其他可执行代码
- **THEN** 页面将其显示为文本，不在浏览器执行
