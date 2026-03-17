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
- Agent 1（运行态持久化与图编排）当前冻结边界：仅维护 backend/db/postgres_store.py、backend/services/artifact_store.py、backend/services/__init__.py、backend/models/artifact.py、backend/graph/content_generation_graph.py；守住 T006/T007/T008/T012/T013/T018/T021 已合入基线；未获 coordinator 明确排期前，不主动扩写 US4/T033 热点功能；不得新增新的运行态状态枚举；content_generation_graph.py 继续单 owner；目标是保持 graph/checkpoint/persistence 语义稳定，并为 Agent 5 的权限修复提供只读兼容，不制造契约漂移。
- 规则：PromptChain 仓库内凡属 frontend/ 目录的代码实现任务，必须由 Gemini CLI 在独立 git worktree 中使用 /ui-ux-pro-max 完成实际编码；Codex 只负责统筹分工、接口约束、diff 审查、验收和 merge gate，不直接编写前端业务代码。范围：所有 frontend 页面、组件、样式、动画、hooks、客户端代码以及 frontend/src/lib/api.ts、frontend/src/lib/auth.ts 等前端契约文件。例外：纯文档、纯后端、纯 spec/contract 讨论且不落地 frontend 代码时，Codex 可直接处理。原因：用户要求前端代码工作统一由 Gemini 执行，Codex 只保留协调和验收职责。
- 规则：PromptChain 多 worktree 协作时，长期记忆统一使用 canonical project_path=/Users/hi/Developer/03-personal/PromptChain 调用 mcp__cunzhi__ji；实时事件、锁表、Gemini 执行记录、handoff 统一写入 /tmp/promptchain-coordination/PromptChain/。仓库内 specs/002-content-gen-mvp1/subagent-events.jsonl 仅作为 coordinator 回填的里程碑快照，不作为实时共享状态源。原因：不同 worktree 的本地文件和未提交改动不会自动共享，必须把实时协作状态移出各自工作区。范围：所有 PromptChain 多 agent/worktree 协作任务。例外：单 worktree 单 agent 的临时试验可以只用本地文件，但一旦进入正式协作必须迁回共享目录。
- 规则：PromptChain 多 worktree 协作时，长期记忆统一使用 canonical project_path=/Users/hi/Developer/03-personal/PromptChain；实时共享状态也统一使用根仓库 canonical 绝对路径文件，而不是 /tmp。共享文件为 /Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl、subagent-locks.json、gemini-executions.jsonl、subagent-handoffs.jsonl。关键规则：所有 agent 必须写这几个绝对路径，不能写各自 worktree 下的相对路径副本。原因：同一机器上的 worktree 可以共同访问根仓库绝对路径文件，没必要再引入 /tmp 作为额外事实源。例外：/tmp 仅可作为临时缓存，不是 canonical 协作状态源。
- 规则：在 PromptChain 多 worktree 协作中，coordinator 后续规划必须包含 worktree sync audit。至少在派工前、dev 前进后、分支申请评审前、进入 merge gate 前，检查每个活跃 worktree 的 branch、base_commit、相对 dev 的 ahead/behind、dirty 状态，并记录到共享协作文件。重要边界：coordinator 负责检查和调度，不默认替 owner 执行 merge/rebase/cherry-pick；若分支落后 dev，需由对应 owner 在评审前自行完成同步并记录。
- 多智能体共享协作文件只认 4 个绝对路径：/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-locks.json、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/gemini-executions.jsonl、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-handoffs.jsonl；禁止在各自 worktree 写相对路径副本；开工时向 subagent-events.jsonl 追加 claimed/progress，准备评审时追加 review_requested；若分支在评审前落后 dev，由对应 agent 自行 sync 并把结果写入 subagent-events.jsonl；凡包含 frontend/ 的实际编码必须由 Gemini CLI 执行，优先 gemini-3.1-pro-preview，不可用时切换 auto-gemini-3。
- PromptChain 多智能体协作时，共享协作文件只认以下 4 个绝对路径：/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-locks.json、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/gemini-executions.jsonl、/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-handoffs.jsonl；不要在各自 worktree 里写相对路径副本。开工时向 subagent-events.jsonl 追加 claimed/progress，准备评审时追加 review_requested；若评审前分支落后 dev，由执行 agent 自己完成 sync，并把 sync 结果写入 subagent-events.jsonl。
- PromptChain 多 worktree 协作统一使用根仓库 canonical 协作文件：/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl、subagent-locks.json、gemini-executions.jsonl、subagent-handoffs.jsonl；禁止在各自 worktree 写副本。凡包含 frontend/ 的实际编码必须由 Gemini CLI 执行，优先 gemini-3.1-pro-preview；若该模型不可用，则切换 auto-gemini-3，并在切换时显式告知用户。
- 作为 PromptChain 的 coordinator，每次完成状态分析、sync audit、队列刷新或评审门禁判断后，默认直接给用户输出下一步可粘贴派工提示词；除非用户明确只要状态结论而不要派工提示词。
- PromptChain 自 2026-03-10 目录重构后，后端 canonical 结构为：app.py 作为 FastAPI 入口，main.py 仅保留兼容重导出；配置集中在 backend/core/config.py；ORM 归档到 backend/orm/*；graph 拆分为 backend/graph/state.py、conditions.py、builder.py、executor.py。后续维护时，禁止把新增业务逻辑重新堆回 main.py、旧 monolithic graph 文件或根目录零散模块；目录结构调整后必须同步 AGENTS.md、specs/002-content-gen-mvp1/plan.md 与项目记忆。
- 经 2026-03-10 git 历史核实，已正式进入 dev 的后端目录结构基线仅包含 P0/P1：app.py 作为 FastAPI 入口、main.py 兼容 shim、core/config.py、routes/workflow_helpers.py、routes/workflow_routes.py、routes/trace_routes.py，以及 graph/state.py、conditions.py、builder.py、executor.py 的拆分。backend/orm/* 尚未进入稳定 git 历史，不应作为 canonical 已落地结构对待。
- PromptChain 的 review agent 开工前必须先回忆项目记忆，并使用 using-superpowers；正式评审默认使用 code-review-excellence。若同一轮存在多条分支并行评审或需要汇总/去重 findings，追加使用 multi-reviewer-patterns。
- PromptChain 的 review agent 必须先做最小 sync audit：确认目标 branch/head、相对 dev 的 ahead/behind、worktree dirty 状态、review scope 和热点文件 owner；评审基于当前有效 head，不能基于过时 commit 或混入 worktree 的无关脏改动下结论。
- PromptChain 的 review 输出格式：findings 优先，按严重度排序；每条 finding 必须带文件路径与行号，并说明影响、触发条件和为什么构成阻塞或非阻塞。若无阻塞问题，必须明确写“无阻塞 findings，可进入 merge 候选”。若只做了静态审查且未跑测试/构建，要明确说明验证边界。
- PromptChain 的 review agent 不直接修改实现代码；收到 findings 的执行者在修复前默认使用 receiving-code-review 校验问题与最小修复面，修完后使用 requesting-code-review 重新申请复审。凡 review scope 含 frontend 变更，reviewer 必须核对 canonical gemini-executions.jsonl 中是否有对应 Gemini 执行记录。
- Reviewer 通用流程规则：开工先用 mcp__cunzhi__ji 回忆项目记忆；先按 using-superpowers 检查并使用相关 skill；正式评审默认使用 code-review-excellence；多分支并行评审/汇总去重 findings 时追加 multi-reviewer-patterns。评审前必须先做最小 sync audit：确认目标 branch/head、相对 dev 的 ahead/behind、worktree 是否 dirty、review scope、热点文件 owner；若 scope 含 frontend/ 改动，还要核对 canonical gemini-executions.jsonl 是否有对应记录。评审边界：只基于当前有效 head；不基于过时 commit 或无关 dirty 改动；reviewer 不直接改代码；重点看逻辑正确性、权限安全、契约一致性、状态机闭环、持久化一致性、回归风险、测试缺口。输出要求：findings 优先并按严重度排序；每条 finding 必须带文件路径、行号、问题描述、影响/触发条件、为何阻塞/非阻塞；若无阻塞问题明确写“无阻塞 findings，可进入 merge 候选。”；若只做静态审查且未跑测试/构建，要明确验证边界。禁止：空泛表扬、把格式问题当主 finding、越权改代码、跳过 sync audit。
- Coordinator 在 PromptChain 多 agent 协作中负责 merge gate 之后的统一推进：当分支已完成提交、同步并通过评审后，由 coordinator 直接执行合并到 dev、安排合并后的全局同步与下一轮队列推进；分支 owner 负责编码、提交、同步和处理 review findings，但不再承担最终 merge/推进职责。例外：若分支未达到 merge-ready，coordinator 只做 gate 判定和排队，不代替 owner 完成未收尾的实现或修复。
- Agent UI Side-Track 职责边界：只负责登录/注册页、首页/营销入口页、纯展示层视觉优化，以及不改变业务契约的样式/布局/动效/信息层级优化；禁止接 frontend/src/lib/api.ts、权限判断与 RBAC 语义、工作流详情页审批逻辑、编辑器发布链路逻辑、任何单 owner 热点文件（除非 coordinator 明确移交）。执行规则：所有 frontend 实际编码必须由 Gemini CLI 完成，必须在独立 git worktree 中开发，先提交侧线分支，不直接进入主 merge 队列，最终由 coordinator 判断是否并入 dev。
- Gemini CLI 模型回退规则更新：前端代码任务默认优先使用 gemini-3.1-pro-preview；若该模型因容量、网络或服务可用性不可用，则首推回退到 gemini-2.5-pro；只有 gemini-2.5-pro 也不可用时，才允许继续回退到其他 Gemini 模型。每次回退都必须在 canonical gemini-executions.jsonl 或共享日志中显式记录，不得静默切换。范围：所有 PromptChain 前端页面、组件、样式、交互、hooks、frontend/src/lib/api.ts、frontend/src/lib/auth.ts 等 frontend/ 代码任务。
- 前端开发流程已切换：Codex 不再默认通过 Gemini CLI 直接执行 frontend 编码，而是默认给用户输出可直接粘贴的派工提示词、文件边界、验收标准和 review gate，由用户在 IDE 的智能助手中于独立 git worktree 内实际执行。范围：所有 frontend 页面、组件、样式、交互、hooks、frontend/src/lib/api.ts、frontend/src/lib/auth.ts 等前端代码任务。例外：若用户明确要求恢复 Gemini CLI 执行，再按当时规则处理。
- Spec Kit 已在当前机器全局安装。PromptChain 仓库内若需使用 Spec-Driven Development，优先通过 specify check 确认工具可用，并在 Codex 交互环境中统一使用 /prompts:speckit.constitution、/prompts:speckit.specify、/prompts:speckit.clarify、/prompts:speckit.plan、/prompts:speckit.tasks、/prompts:speckit.analyze、/prompts:speckit.checklist、/prompts:speckit.implement；不要假设裸 /speckit.* 命令可用。若需要在现有仓库重新补齐模板，使用 specify init --here --ai codex，非必要不使用 --force。
- PromptChain 后续凡涉及最终进入 dev 的工作，统一走 PR + CI/CD gate，不直接在本地由 Codex 执行最终合并。Codex/coordinator 的职责是推进评审、同步状态、准备 PR/merge checklist、给出发起 PR 的提示词和后续排班；只有在用户明确要求时，才允许代为执行本地 merge。
