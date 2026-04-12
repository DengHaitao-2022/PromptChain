# Quickstart: unified-error-system legacy alignment

本 quickstart 只覆盖 `workflow_definition` / `workflow_version` 两个遗留域接入统一错误体系后的最小验收，不把范围扩展到 frontend consumer 或其他后端域。

## 1. 目标

确认以下事实成立：

1. 这两个 legacy 路由的错误出口已经进入统一错误 envelope
2. `backend/models/result.py` 只作为兼容桥接层继续存在
3. 成功响应暂时仍保持旧 `Result.success(...)` 形状，不在本次切片顺手改动

## 2. 最小自动化验证

在 `backend/` 目录执行：

```bash
uv run --extra dev pytest tests/test_error_system_foundation.py tests/test_unified_error_legacy_alignment.py -q
```

预期：

- 所有测试通过
- 不需要启动前端
- 不需要跑完整业务主链

## 3. 契约检查项

### A. workflow definition not-found

请求不存在的工作流定义详情：

- `GET /api/workflows/{workflow_id}`

预期：

- HTTP `404`
- 响应为统一错误 envelope
- `code == "WORKFLOW_NOT_FOUND"`

### B. publish validation failed

对一个未通过发布校验的工作流发起发布：

- `POST /api/workflows/{workflow_id}/publish`

预期：

- HTTP `400`
- 响应为统一错误 envelope
- `code == "WORKFLOW_VALIDATION_FAILED"`
- `details.validation` 内保留校验失败详情，供旧编辑器或后续 consumer 过渡使用

### C. workflow version not-found

请求不存在的工作流版本：

- `GET /api/workflows/{workflow_id}/versions/{version_id}`

预期：

- HTTP `404`
- 响应为统一错误 envelope
- `code == "WORKFLOW_VERSION_NOT_FOUND"`

### D. result bridge compatibility

通过 `Result.from_error_envelope()` 桥接 `WORKFLOW_VALIDATION_FAILED`。

预期：

- 仍得到 legacy 数字错误码 `40000`
- 说明 `result.py` 仍可服务于旧消费者，但不再是新错误路径的首选出口

## 4. 真实边界说明

### 本次已完成

- workflow definition 域错误风格收敛
- workflow version 域错误风格收敛
- workflow 版本缺失 / 发布校验失败拥有稳定错误码
- `result.py` 的桥接层角色明确

### 本次未完成

- frontend consumer 迁移
- workflow definition / version 成功响应去 `Result.success`
- 删除 `backend/models/result.py`
- 其他未迁移域的 legacy success / error 风格清理
