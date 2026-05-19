# PromptChain 数据库迁移说明

## 目标

数据库 schema 从应用启动时的 `create_all` 和手写 `ALTER TABLE ... IF NOT EXISTS` 迁移到 Alembic 版本化管理。生产环境必须能回答三个问题：当前 schema 版本是什么、某次变更由哪个 revision 引入、出现问题时回滚边界在哪里。

## 当前基线

- Alembic 配置入口：`backend/alembic.ini`
- Alembic 环境：`backend/alembic/env.py`
- 当前基线 revision：`20260520_0001`
- 基线文件：`backend/alembic/versions/20260520_0001_baseline_schema.py`

该 baseline 表达当前 ORM 可创建的表结构，并把历史手写迁移已经承载的列纳入版本化基线：

- `workflow_runs.workflow_definition_id`
- `workflow_runs.workflow_version_id`
- `audit_logs` 的 request/trace/snapshot/schema 相关字段与查询索引
- `memberships(user_id, workspace_id)` 唯一约束
- `workflow_definitions` 发布字段
- `workflow_versions` 发布快照字段

本次 baseline 不做数据清洗、不回填历史行、不删除现有生产表、不调整业务字段语义。
其中 `audit_logs.event_id` 只按当前 ORM 有效结构保留普通索引；若生产审计链路后续需要强制唯一 partial index，应通过独立 revision 显式评审。

## 初始化

新环境初始化数据库时，在 `backend/` 目录执行：

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain \
uv run alembic upgrade head
```

如果是已有开发库，且表结构已经由历史 `create_all` / 手写 SQL 创建完成，可以在人工确认结构与 baseline 一致后 stamp：

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain \
uv run alembic stamp 20260520_0001
```

`stamp` 只记录 Alembic 版本，不创建或修改业务表；它适合把既有库纳入版本管理，不适合修复结构漂移。

## 升级

后续 schema 变更流程：

1. 修改 ORM 或明确 SQL 变更意图。
2. 创建新的 Alembic revision，文件名使用短动词描述变更。
3. 在 `upgrade()` 中写最小 schema 变更。
4. 在 `downgrade()` 中写可审查的反向操作；不能安全回滚的数据迁移必须在注释中说明边界。
5. 本地开发库执行 `uv run alembic upgrade head`。
6. 生产发布先跑 migration，再启动新应用版本。

不允许在生产路径继续新增应用启动时的手写 `ALTER TABLE`。复杂数据修复应拆成单独运维脚本或一次性 migration，并经过独立评审。

## 回滚

`downgrade()` 只定义 schema 回滚边界，不承诺自动恢复被清洗、合并或丢弃的数据。当前 baseline 的 downgrade 仅适用于空库或临时开发库，不应用于含生产数据的库。

生产回滚优先顺序：

1. 回滚应用版本。
2. 仅当新 schema 与旧应用不兼容时，执行目标 revision 的 downgrade。
3. 涉及数据内容的回滚必须先做备份和人工确认。

## 开发兼容路径

`backend/db/postgres_store.py` 仍保留 legacy 自动初始化：

- `Base.metadata.create_all`
- `_runtime_schema_statements()` 中的历史幂等 ALTER / INDEX

这是为了不破坏本地开发启动路径。生产环境应设置：

```bash
DATABASE_AUTO_SCHEMA_INIT=false
```

设置后应用不会在 `PostgresArtifactStore.init_db()` 中执行 `create_all` 或 runtime schema ALTER。生产库必须由 Alembic 管理 schema 版本。

## 手写 ALTER 归属与移除计划

现有手写迁移归属如下：

- `backend/db/postgres_store.py::_runtime_schema_statements()`：已归属 `20260520_0001` baseline，后续只保留开发兼容。
- `backend/services/workflow_definition_service.py::_POSTGRES_SCHEMA_STATEMENTS`：发布字段与版本快照字段已归属 `20260520_0001` baseline；该文件本轮未在允许修改范围内，后续应在确认所有环境完成 Alembic stamp/upgrade 后移除 runtime ALTER。
- `backend/db/migrations/002_audit_log_traceability.sql`：已归属 `20260520_0001` baseline，保留为历史参考。
- `backend/db/migrations/003_membership_unique_workspace.sql`：已归属 `20260520_0001` baseline，保留为历史参考。

后续移除计划：

1. 所有长期环境执行 Alembic `upgrade head` 或人工确认后 `stamp 20260520_0001`。
2. 观察一个发布周期，确认不再依赖应用 runtime ALTER 补列。
3. 新 revision 或独立清理 PR 移除 `_runtime_schema_statements()` 和 `_POSTGRES_SCHEMA_STATEMENTS`。
4. 保留文档中的历史迁移说明，避免审计链路丢失。
