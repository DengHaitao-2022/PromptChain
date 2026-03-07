# 开发规范和规则

- ## 企业级项目目录结构规范

### 后端 (Python/FastAPI)
```
backend/
├── main.py                    # 应用入口
├── config/                    # 配置管理 (settings.py, logging.py)
├── api/v1/                    # API 路由层，版本控制
├── core/                      # 核心逻辑 (security.py, exceptions.py)
├── db/                        # 数据库层 (session.py, migrations/, repositories/)
├── models/                    # ORM 模型 (SQLAlchemy)
├── schemas/                   # Pydantic 数据模型 (请求/响应)
├── services/                  # 业务服务层
├── graph/                     # AI 工作流图 (LangGraph: nodes/, chains/)
├── utils/                     # 工具函数
└── tests/                     # 测试 (unit/, integration/)
```

### 前端 (Next.js 15 + TypeScript)
```
frontend/src/
├── app/                       # App Router 页面
│   ├── (auth)/                # 认证路由组
│   ├── (dashboard)/           # 仪表盘路由组
│   └── api/                   # API 路由 (BFF)
├── components/                # UI 组件
│   ├── ui/                    # 基础 UI 组件
│   ├── layout/                # 布局组件
│   ├── forms/                 # 表单组件
│   ├── modals/                # 弹窗组件
│   └── features/              # 功能组件 (如 WorkflowEditor/)
├── contexts/                  # React Context
├── hooks/                     # 自定义 Hooks
├── lib/                       # 工具库 (api.ts, utils.ts, constants.ts)
├── types/                     # TypeScript 类型定义
└── styles/                    # 全局样式
```

### 分层原则
- API层 → 服务层 → 模型/数据库层，依赖向下
- 每个目录职责单一，命名清晰
- PromptChain 多智能体协作遵循 AURA-X-KYS 适配版：任务开始先回忆项目记忆；方案与实现默认遵循 KISS/YAGNI/SOLID；关键决策需显式确认；若记忆与当前仓库或 AGENTS.md 冲突，以当前仓库事实和 AGENTS.md 为准，并在确认后修正记忆；交接时只沉淀稳定规则、偏好、模式和高价值上下文，避免写入临时噪声。
- 多智能体 CLI 协作规则：1. 任务必须是 DAG，即显式依赖图，禁止“大家先做着看”。2. 每个任务必须包含 owner、输入、输出、完成标准。3. 同一时刻同一文件域只允许一个 agent 持有写锁。4. 所有状态变化都必须追加到共享日志，不能依赖口头同步。5. 合并前必须经过独立 review gate，不能由执行者自行宣布完成后直接合并。
- 规则：凡涉及前端页面、组件、交互、动画或 UI/UX 优化的开发任务，Codex 在开始实现前应先启动 Gemini CLI，并在 gemini 中使用 /ui-ux-pro-max 参与页面交互与动画设计；实现阶段必须使用 git worktree 隔离工作区，并创建新的 code/feat-* 分支或进入对应的已有 code/feat-* 分支后再开发。原因：前端任务需要专门的 UI/UX 设计工作流与隔离开发环境，减少主工作区污染和并行开发冲突。范围：适用于 PromptChain 仓库内所有前端开发、前端重构、样式优化、交互改造、页面动效设计任务。例外：纯文档修改、仅后端改动、纯契约讨论且不落地前端代码时可不启动 gemini，也可不创建前端 worktree。
