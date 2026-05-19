# Quickstart: PromptChain 统一错误体系

本文档描述 `005-unified-error-system` 的最小验收路径。目标不是跑完整业务主链，而是验证核心 API 域已经开始使用统一错误契约，并且前端/调用方可以基于稳定错误标识做处理。

## 1. 环境前提

- 后端服务可访问
- 前端服务可访问
- 至少准备一个未登录会话、一个普通用户会话、一个管理员会话
- 至少存在一个工作流、一个工作流运行记录和一个不存在的资源 ID 用于负向场景

## 2. 启动本地环境

若本轮只验证后端错误契约，可以先跑不依赖真实模型的 fake smoke，确认基础链路不是被 provider key 阻断：

```bash
cd /Users/hi/Developer/03-personal/PromptChain/backend
uv run pytest tests/test_llm_provider.py -q
DEFAULT_LLM_PROVIDER=fake uv run python ../scripts/smoke/acceptance_smoke.py
```

记录规则：

- `tests/test_llm_provider.py` 可进 CI，用于确认 fake provider 不依赖真实 OpenAI/Anthropic/Gemini key
- `scripts/smoke/acceptance_smoke.py` 需要 PostgreSQL 和后端服务；若 PostgreSQL/Redis 不可用，应记录为 `blocked`
- 真实 provider smoke 仍需人工或独立 live job 执行；未真实运行时必须记录 `manual_live_provider: not_run`

### 后端

```bash
cd /Users/hi/Developer/03-personal/PromptChain/backend
uv sync
uv run uvicorn app:app --reload --port 8000
```

### 前端

```bash
cd /Users/hi/Developer/03-personal/PromptChain/frontend
npm install
npm run dev
```

## 3. Smoke A：未登录访问受保护接口

### 目标

验证未登录请求在受保护接口上返回统一错误结构，而不是不同接口各自的 `detail` 风格。

### 步骤

1. 在未登录状态下请求受保护接口，例如 `/api/me` 或运行记录接口
2. 记录错误响应结构
3. 再请求另一个受保护接口，比较两次失败响应

### 预期结果

- 两次失败响应使用相同外部结构
- 都携带稳定错误标识和请求追踪标识
- 调用方可判断这是“需要重新登录”的场景

## 4. Smoke B：越权访问管理或他人资源

### 目标

验证权限不足场景能返回稳定的业务错误标识，而不是仅依赖中文文案。

### 步骤

1. 用 `viewer` 账号访问成员管理或模型配置接口
2. 用普通账号访问他人运行记录或 trace 资源
3. 对比不同越权场景的错误响应

### 预期结果

- 错误语义可稳定识别为权限不足或资源不可访问
- 响应不泄露底层资源内部信息
- 调用方能够区分“重新登录”和“权限不足”

## 5. Smoke C：资源不存在

### 目标

验证不存在资源的错误语义在不同 API 域中保持一致。

### 步骤

1. 请求一个不存在的工作流
2. 请求一个不存在的 trace 或 artifact
3. 对比错误响应

### 预期结果

- 资源不存在场景使用统一错误语义
- 调用方可稳定识别为 `not_found` 类处理方向

## 6. Smoke D：基础设施异常脱敏

### 目标

验证基础设施依赖故障不会把底层异常原文直接透传给前端。

### 步骤

1. 制造一个可控的数据库、缓存、模型服务或邮件依赖失败场景
2. 触发对应接口
3. 检查响应和服务端日志

### 预期结果

- 前端收到的是稳定错误语义和请求追踪标识
- 响应中不包含底层堆栈或原始异常字符串
- 服务端日志仍保留足够的问题定位信息

## 7. Smoke E：前端错误处理分支

### 目标

验证前端或客户端逻辑能基于稳定错误标识而不是文案做分支。

### 步骤

1. 触发至少三类错误：
   - 未登录
   - 权限不足
   - 资源不存在
2. 检查前端提示与页面行为

### 预期结果

- 前端能区分重新登录、无权限、资源不存在三类处理方向
- 文案变化不会破坏分支行为

## 8. Acceptance Notes

- 本特性第一阶段重点是统一错误契约，不要求一次性完成所有旧接口迁移
- 若某个 API 域仍返回旧格式，应记录为迁移缺口，而不是把统一错误体系判定为整体失败
