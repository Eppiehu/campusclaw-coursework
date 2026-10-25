# Nexus 运行与部署

Nexus 与原课程版在同一仓库，通过 `CAMPUSCLAW_EDITION=nexus` 选择新版应用。课程版的 MySQL、Qdrant、上传文件和历史报告不自动迁移或删除。新版复用原有文本切片、中文向量模型、技能文件解析等模块，业务数据使用独立 PostgreSQL。

## 本地运行

1. 安装 `requirements-nexus.txt`，启动 PostgreSQL/pgvector 和 Redis。
2. 复制 `.env.nexus.example` 为忽略文件 `.env.nexus.local`，配置数据库、随机签名密钥及模型密钥。
3. 在 `web` 中运行 `pnpm install`、`pnpm run build`。
   演示部署如需“选人后自动填密码”，构建前把演示账号的密码分别设为 `VITE_NEXUS_DEMO_TEACHER_PASSWORD`、`VITE_NEXUS_DEMO_STUDENT_PASSWORD`，值需与服务端的种子账号密码一致。构建结果会把这两个值公开给所有访问者，因此仅适用于可公开体验的演示账号；不设置时保留手动登录。
4. 执行 `python scripts/run_nexus.py init` 初始化迁移和种子；`serve` 启动 HTTP，`worker` 启动 RQ。Worker 使用 Linux/WSL 或 Docker。
5. 本地向量模型使用原 `_model_cache`，正式部署放入 `nexus-data/models`。模型为 BAAI/bge-small-zh-v1.5，512维；离线模式不将材料发送给外部Embedding服务。

## 隔离部署

使用 `Dockerfile.nexus` 与 `docker-compose.nexus.yml`。Compose 项目固定为 `campusclaw-nexus`，仅 API 暴露独立 8088 端口；PostgreSQL 和 Redis 不暴露宿主机端口。使用独立持久卷和网络，不停止或替换已有容器，不修改旧 Nginx。

部署前在本地构建前端，并准备模型缓存。发布目录位于 `/opt/campusclaw-nexus/releases/`。该目录中运行 `sh deploy/nexus-deploy.sh`。密钥通过独立、权限为600的 `.env.nexus.local` 注入，不写入源码或镜像。数据库备份使用 `deploy/nexus-backup.sh`；升级前备份，旧版发布目录保留。

用户已决定本轮先使用 IP:8088。HTTP 入口不提供传输加密，仅用于演示数据；HTTPS 域名及证书以后配置，不将其写为已完成。

小内存部署采用单 Worker，API 容器640MB上限，并将同时执行的Agent问答限制为1个，其他请求返回429以防内存耗尽。HTTP服务和验证脚本分容器运行，避免额外测试进程挤占业务进程限额。宿主机或云安全组需要单独允许8088，服务健康不等于公网可达。

## 数据与任务

应用事务先保存 Task，再将任务ID发给 Redis/RQ。队列不可用时保留 dispatch_failed，调度器恢复入队；执行失败保留 failed，可由本班教师重试，最多5次。每个学生的发卷单独建任务。周报调度器每分钟检查上一完整周，只创建一次；当前周也可由教师手动生成。

周报按北京时间周一00:00划定统计周期。观测数字直接由程序展示，模型只根据事实写观察与建议；没有上期数据时不声称上升或下降，缺少访问记录不等同于学生缺少学习投入。

材料索引完成时在事务内切换活动版本；失败沿用旧版本。撤回材料后不再参与新检索，历史消息中的引用片段、版本号与哈希继续保留。
讲义列表的“查看正文”直接在页面内展开当前生效版本，沿用下载接口的登录与班级鉴权。Markdown按原文显示；PDF展示抽取的文字，不还原原始版式。

作业页区分AI初评与教师复核后的最终分。部署验收使用的一份虚构错误答案由AI评为0分，测试脚本随后以教师身份复核为30分并保留文字依据；这是两次不同操作，AI分并未被改写。

## 测试

`python -m pytest tests_nexus -q` 使用独立 PostgreSQL schema，模型和Embedding采用测试替身，仅用于业务规则检查。`scripts/verify_nexus_live.py` 必须显式 `--live --isolated`，并连接独立空白演示数据库。真实验证使用 DeepSeek、MCP SDK stdio、Redis/RQ及本地中文Embedding，结果保存在忽略目录 `apitest/report/`。
