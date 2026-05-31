# Workflow Definition & Version API（可视化编排）

> 对应系统设计能力：Prompt Chain 工作流的可视化编排。

## 响应包裹格式

该域接口使用统一 `Result` 格式：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

## 工作流定义接口

- `GET /api/workflows?limit=50&offset=0` 获取当前空间工作流定义列表
- `GET /api/workflows/public?limit=50&offset=0` 获取首页匿名可见的已发布工作流列表
- `POST /api/workflows` 创建定义
- `GET /api/workflows/{workflow_id}` 获取定义详情
- `GET /api/workflows/{workflow_id}/definition` 获取定义（编辑器语义路径）
- `PUT /api/workflows/{workflow_id}` 更新定义
- `PUT /api/workflows/{workflow_id}/definition` 更新定义（编辑器语义路径）
- `DELETE /api/workflows/{workflow_id}` 软删除定义
- `POST /api/workflows/{workflow_id}/validate` 校验节点/边合法性
- `POST /api/workflows/{workflow_id}/compile` 编译为可执行图预览
- `POST /api/workflows/{workflow_id}/publish` 将当前草稿发布为可运行版本

### 创建/更新请求体核心结构

```json
{
  "name": "内容生成链路",
  "description": "用于长文生成",
  "nodes": [
    {
      "id": "n1",
      "type": "input",
      "position": { "x": 120, "y": 80 },
      "data": { "label": "输入", "config": {} }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "n1",
      "target": "n2",
      "type": "default",
      "data": { "condition": null, "label": null }
    }
  ]
}
```

## 版本管理接口

- `GET /api/workflows/{workflow_id}/versions` 获取版本历史
- `GET /api/workflows/public/{workflow_id}/versions` 获取匿名可见工作流的当前已发布版本
- `GET /api/workflows/{workflow_id}/versions/{version_id}` 获取单版本详情
- `GET /api/workflows/{workflow_id}/versions/compare?version_a=1&version_b=2` 对比版本差异
- `POST /api/workflows/{workflow_id}/versions/{version_id}/restore` 回滚到指定版本（生成新版本）
