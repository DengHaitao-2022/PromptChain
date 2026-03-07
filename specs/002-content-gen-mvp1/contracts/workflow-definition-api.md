# Workflow Definition & Publication API Contract

## 1. Response Envelope

工作流定义、版本与发布类接口统一使用 `Result` 包装：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误时：

```json
{
  "code": 40000,
  "message": "请求参数错误",
  "data": null
}
```

## 2. Core Resource Shape

### WorkflowDefinition

```json
{
  "id": "wf_def_123",
  "name": "内容生成工作流",
  "description": "用于长文生成",
  "version": 3,
  "nodes": [],
  "edges": [],
  "created_at": "2026-03-07T00:00:00Z",
  "updated_at": "2026-03-07T00:00:00Z",
  "created_by": "user_123"
}
```

### Node Contract

| Field | Meaning |
|---|---|
| `id` | 节点唯一标识 |
| `type` | 持久化通用类型：`input` / `process` / `gate` / `checker` / `output` |
| `position` | 画布坐标 |
| `data.label` | 节点显示名 |
| `data.config` | Prompt、条件、门控类型等配置 |

### Edge Contract

| Field | Meaning |
|---|---|
| `id` | 连线唯一标识 |
| `source` | 起点节点 ID |
| `target` | 终点节点 ID |
| `type` | 连线类别 |
| `data.condition` | 条件表达式 |
| `data.label` | 标签 |

## 3. Endpoint Contract

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/api/workflows` | Existing | 获取当前工作空间的工作流列表 |
| `POST` | `/api/workflows` | Existing | 创建工作流草稿 |
| `GET` | `/api/workflows/{workflow_id}` | Existing | 获取工作流定义详情 |
| `GET` | `/api/workflows/{workflow_id}/definition` | Existing | 获取工作流定义（编辑器语义化路径） |
| `PUT` | `/api/workflows/{workflow_id}` | Existing | 更新工作流草稿 |
| `PUT` | `/api/workflows/{workflow_id}/definition` | Existing | 更新工作流定义（编辑器语义化路径） |
| `DELETE` | `/api/workflows/{workflow_id}` | Existing | 软删除工作流 |
| `POST` | `/api/workflows/{workflow_id}/validate` | Existing | 校验工作流合法性 |
| `POST` | `/api/workflows/{workflow_id}/compile` | Existing | 编译为可执行图预览 |
| `POST` | `/api/workflows/{workflow_id}/publish` | Target New | 将当前草稿发布为可运行版本 |
| `GET` | `/api/workflows/{workflow_id}/versions` | Existing | 获取版本历史 |
| `GET` | `/api/workflows/{workflow_id}/versions/{version_id}` | Existing | 获取单个历史版本快照 |
| `GET` | `/api/workflows/{workflow_id}/versions/compare` | Existing | 对比两个版本 |
| `POST` | `/api/workflows/{workflow_id}/versions/{version_id}/restore` | Existing | 从历史版本恢复并形成新当前版本 |

## 4. Validation Contract

`POST /api/workflows/{workflow_id}/validate` 的目标输出必须至少覆盖：

- 是否存在可作为入口的节点
- 是否存在输出节点
- 是否存在重复节点 ID
- 连线源/目标是否引用存在的节点
- 是否存在孤立节点
- 是否缺失关键配置（Prompt、条件、Gate 配置等）

### Target Validation Response

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

## 5. Publication Rules

1. 草稿保存不会自动发布。
2. 发布动作必须生成可运行版本边界，供普通用户运行。
3. 已发布版本在普通用户运行期间必须保持稳定，不应被草稿编辑影响。
4. 恢复历史版本时，应形成新的当前版本，而不是回写覆盖旧快照。

## 6. Migration Notes

- 当前模型中已有 `is_published` 和 `WorkflowVersionORM`，但缺少独立发布接口；本契约将其补齐。
- 当前节点类型是通用技术类型，不直接等同于规格中的业务节点名称；两者的语义映射应由前端节点模板和 `config` 字段承担。
