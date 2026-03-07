# 常用模式和最佳实践

- 前端技术栈: Next.js 15 + TypeScript + Radix UI + 原生CSS
CSS模块类名: 使用camelCase格式 (如inputContainer, mainTextarea)
组件结构: components/{ComponentName}/{ComponentName}.tsx + .module.css + index.ts
API客户端: src/lib/api.ts 集中管理所有后端接口和类型定义
- 交互式 Codex CLI/TUI 中，仓库 `.codex/prompts/*.md` 会注册为 slash command，调用格式是 `/prompts:<prompt-name>`，例如 `/prompts:speckit.specify`；不要使用裸命令 `/speckit.specify`。`codex exec` 不等价于交互式 slash command 入口，不能用来判断自定义 prompt 是否已注册或可用。验证证据：在隔离仓库中执行 `/prompts:speckit.specify 添加一个最小化测试功能` 成功创建分支 `001-minimal-test`，并生成 `specs/001-minimal-test/spec.md` 与 `specs/001-minimal-test/checklists/requirements.md`。
- 运行态契约基线：`backend/main.py` 是 `WorkflowResponse` 公开语义的归一化入口，`frontend/src/lib/api.ts` 必须镜像同一套类型。公开 `status` 固定为 `running / paused / needs_clarification / awaiting_outline_approval / awaiting_fact_check_approval / completed / failed`；`state` 额外稳定暴露 `current_node`、`pause`、`gate`、`error`。`GET /api/trace/{id}` 的 `workflow.status` 也必须使用同一公开状态，并在缺少实时 emit 时通过 timeline 补偿 `workflow_paused` / `workflow_resumed` / `workflow_gate_waiting`。
