# Implementation Plan: unified-error-system legacy alignment

**Branch**: `code/feat-unified-error-system-legacy-alignment`
**Date**: `2026-04-12`
**Baseline**: `8a7a320`（foundation + core domains review-approved）

## 本次切片目标

本次只收敛 unified-error-system 在 legacy workflow definition / workflow version 域中的残留旧错误风格，不扩展到 frontend、graph/nodes 或新的业务域。实现遵循 KISS / YAGNI：

1. `workflow_definition_routes.py` 不再返回旧 `Result.not_found/error(...)` 错误对象，而是抛统一错误体系异常。
2. `workflow_version_routes.py` 不再返回旧 `Result.not_found(...)` 错误对象，而是抛统一错误体系异常。
3. `backend/models/result.py` 明确定位为 **legacy compatibility bridge**：
   - 旧成功响应仍可暂时复用 `Result.success`
   - 旧数字错误码消费者可通过 `from_error_envelope()` 过渡
   - 新错误路径不再允许继续直接构造 `Result.error/not_found/...`
4. 只补最小契约测试，覆盖这次切片真正引入的关键回归。

## 已确认的真实迁移边界

### 本次 in scope

- `backend/routes/workflow_definition_routes.py`
- `backend/routes/workflow_version_routes.py`
- `backend/models/result.py`
- `backend/core/errors/codes.py`
- `backend/tests/*`
- `specs/005-unified-error-system/quickstart.md`
- `specs/005-unified-error-system/plan.md`

### 本次 out of scope

- `frontend/*` 的错误消费迁移
- `backend/routes/auth_routes.py`、`workspace_routes.py`、`admin_routes.py`、`workflow_routes.py`、`trace_routes.py`
- `backend/nodes/*`、`backend/graph/*`
- 把 workflow definition / version 的成功响应也一起改造成新 envelope
- 删除 `backend/models/result.py`

## 最小实现策略

### 1. 新增缺失的 workflow 稳定错误码

只补这次切片真正需要的两个稳定错误码：

- `WORKFLOW_VERSION_NOT_FOUND`
- `WORKFLOW_VALIDATION_FAILED`

并同步它们到 legacy 数字 `code` 映射，保证桥接层仍可工作。

### 2. 收敛 workflow definition 域错误出口

- 工作流不存在时抛 `DomainError(code=WORKFLOW_NOT_FOUND)`
- 发布校验失败时抛 `ApplicationError(code=WORKFLOW_VALIDATION_FAILED, details={"validation": ...})`
- 成功场景继续返回 `Result.success(...)`，避免本次切片顺手改变旧成功契约

### 3. 收敛 workflow version 域错误出口

- 工作流不存在时抛 `DomainError(code=WORKFLOW_NOT_FOUND)`
- 工作流版本不存在时抛 `DomainError(code=WORKFLOW_VERSION_NOT_FOUND)`
- 成功场景继续返回 `Result.success(...)`

### 4. 明确 `result.py` 的最终角色

`backend/models/result.py` 在本次后被视为：

- **当前角色**：legacy compatibility bridge
- **保留原因**：仍有遗留成功响应与旧数字错误码消费者未完全退场
- **退出策略**：待 workflow definition / version 成功响应与前端 consumer 迁移完成后，再整体移除

## 验证边界

本次只要求最小契约验证，不做全量构建或 live smoke。最小验证包括：

1. workflow definition not-found 返回统一错误 envelope
2. publish validation-failed 返回统一错误 envelope + validation details
3. workflow version not-found 返回统一错误 envelope
4. `Result.from_error_envelope()` 仍能桥接新的 workflow 校验错误到旧数字 code
