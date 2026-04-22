<div align="center">

# PromptChain

基于 Prompt Chain 与 LangGraph 的自动化内容生成系统

面向长文、脚本与结构化内容生产的 AI 工作流平台，强调分阶段生成、人机门控、事实核查与全链路追踪。

<p>
  <img src="https://img.shields.io/badge/Python-3.14%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14+">
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Workflow-111111?style=flat-square" alt="LangGraph">
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js 16">
  <img src="https://img.shields.io/badge/React-19-149ECA?style=flat-square&logo=react&logoColor=white" alt="React 19">
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Redis-7-D82C20?style=flat-square&logo=redis&logoColor=white" alt="Redis">
</p>

<p>
  <a href="#为什么是-promptchain">为什么是 PromptChain</a> ·
  <a href="#核心能力">核心能力</a> ·
  <a href="#工作流总览">工作流总览</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#当前边界与后续方向">当前边界与后续方向</a>
</p>

</div>

## 为什么是 PromptChain

随着 LLM 在写作、脚本生成、知识整理和商业内容生产中的使用越来越普遍，单次 Prompt 在复杂任务里暴露出几个稳定问题：

- 长文结构容易漂移，段落层级和重点分配不稳定。
- 当输入不完整时，模型会自行补全假设，导致内容跑偏。
- 多步骤推理不可见，用户很难在关键节点进行干预。
- 事实性内容缺乏显式校验，产物难以直接进入可发布环节。
- 一次生成失败后，通常只能整体重来，成本高且不可追踪。

PromptChain 的目标不是“再包一层 Prompt”，而是把复杂内容生产拆成可管理的 AI 工作流：

- 先把用户需求转成结构化意图卡。
- 对不确定点做显式检测，并在必要时暂停等待用户澄清。
- 基于确认后的上下文生成提纲，再进入正文生成。
- 通过 Self-Refine 优化表达质量，再用事实核查筛出高风险声明。
- 将每个阶段产物版本化保存，支持 Trace、回放与定点重跑。

这套设计更接近当前 AI 系统的发展方向：`多阶段编排 + Human-in-the-Loop + 可追踪 + 可恢复 + 多模型兼容`。

## 核心能力

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 用户登录与角色权限管理 | 已实现基础版本 | 支持认证、RBAC、工作空间与后台管理相关路由。 |
| Prompt Chain 内容生成主链路 | 已实现 | 支持从用户输入启动工作流，进入意图解析、提纲、写作、自检、事实核查与最终输出。 |
| 不确定点检测与人机门控 | 已实现 | 支持澄清问题、提纲审批、事实核查高风险项确认。 |
| 事实核查与内容修订 | 已实现 | 集成 Self-Refine 与事实核查节点，支持高风险项二次确认。 |
| Trace / Artifact 追踪 / 节点重跑 | 已实现 | 支持节点详情、Artifact 历史、重跑选项与从指定节点重跑。 |
| 可视化工作流编排 | 部分实现 | 已有工作流定义、版本管理和前端编辑器骨架，保存与控制台能力仍在完善。 |
| 实时推送与控制台监控 | 部分实现 | WebSocket 路由已存在，但主执行链路的实时事件接入仍需补齐。 |

## 适用场景

- 自动生成长文、科普文、研究综述、行业分析。
- 自动生成脚本、方案文档、商业计划书、结构化内容草稿。
- 需要“先提纲审批再写作”的协同内容流程。
- 需要对不确定信息、高风险事实进行人工确认的生产链路。
- 需要回放生成过程、查看每个节点输入输出的可审计场景。

## 工作流总览

当前内容生成主链路由 LangGraph 编排，核心流程如下：

```mermaid
flowchart LR
    A["用户输入"] --> B["parse_intent<br/>意图解析"]
    B -->|"存在不确定点"| C["clarify_intent<br/>澄清补全"]
    B -->|"信息充分"| D["generate_outline<br/>生成提纲"]
    C --> D
    D --> E["approve_outline<br/>提纲审批"]
    E --> F["generate_content<br/>生成正文/脚本"]
    F --> G["self_refine<br/>自检修订"]
    G --> H["check_facts<br/>事实核查"]
    H -->|"存在高风险项"| I["approve_fact_check<br/>人工确认"]
    H -->|"风险可接受"| J["finalize<br/>最终输出"]
    I --> J
```

对应的产物和状态会被记录到版本化模型中：

- `Artifact`：节点产物，按版本写入，不覆盖旧版本。
- `NodeRun`：节点执行记录，保留输入输出关联、耗时与决策信息。
- `WorkflowRun`：一次完整工作流运行的顶层记录。

## 快速开始

### 前置要求

- Docker / Docker Compose
- Python `3.14+`
- `uv`
- Node.js `20+`

### 1. 启动基础设施

```bash
docker compose up -d postgres redis
```

默认会启动：

- PostgreSQL：`localhost:5432`
- Redis：`localhost:6380`

### 2. 启动后端

```bash
cd backend
uv sync
cp .env.example .env
uv run uvicorn app:app --reload --port 8000
```

`backend/.env` 至少需要配置一个可用模型提供方：

```env
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OLLAMA_BASE_URL=http://localhost:11434

DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL_NAME=gpt-4o
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain
```

### 3. 启动前端

```bash
cd frontend
npm install
printf 'NEXT_PUBLIC_API_URL=http://localhost:8000\n' > .env.local
npm run dev
```

启动后可访问：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 典型使用路径

1. 在首页输入写作需求，启动工作流。
2. 系统先生成结构化意图卡，并在必要时向用户发起澄清。
3. 生成提纲后暂停，等待用户审批、修改或要求重生成。
4. 通过审批后自动生成正文，并执行 Self-Refine。
5. 事实核查节点识别声明并标记高风险项，必要时再次由用户确认。
6. 系统产出最终内容，同时保留完整 Trace、Artifact 历史和重跑能力。

## 系统架构

### 后端

- `FastAPI` 提供工作流、认证、后台管理、工作空间和 Trace API。
- `LangGraph` 负责内容生成主链路的状态编排。
- `services/` 中封装 ArtifactStore、TraceService、RerunService 等核心能力。
- 认证、权限、工作流定义等能力已经接入 PostgreSQL 路径。

### 前端

- `Next.js App Router + React 19 + TypeScript`。
- 首页负责启动内容工作流。
- 工作流详情页负责轮询状态并承载澄清、提纲审批、事实核查审批等交互。
- 控制台包含工作流编辑器、成员与权限、后台管理等页面骨架。

### 数据与运行时

- PostgreSQL：账号、权限、工作空间、工作流定义与后台数据。
- Redis：为后续缓存、状态与编排扩展预留。
- 内容主链路默认使用 PostgreSQL 运行态存储；可通过 `RUNTIME_STORE_BACKEND=memory` 切换为内存模式（开发回退）。

## 关键接口

### 内容工作流

- `POST /api/workflow/start`
- `POST /api/workflow/{workflow_run_id}/clarify`
- `POST /api/workflow/{workflow_run_id}/approve-outline`
- `POST /api/workflow/{workflow_run_id}/approve-fact-check`
- `GET /api/workflow/{workflow_run_id}`
- `GET /api/workflow/{workflow_run_id}/rerun-options`
- `POST /api/workflow/{workflow_run_id}/rerun`

### 追踪与产物

- `GET /api/trace/{workflow_run_id}`
- `GET /api/trace/node/{node_run_id}`
- `GET /api/artifact/{artifact_id}`
- `GET /api/artifact/{artifact_id}/history`

### 平台能力

- `POST /api/auth/*`：登录、注册、刷新 Token、邮箱验证等
- `GET/POST/PATCH /api/workspaces*`：工作空间与成员管理
- `GET/POST/PUT /api/workflows*`：工作流定义与版本管理
- `WebSocket /ws/*`：工作流与用户级实时通道

## 项目结构

```text
PromptChain/
├── backend/                 # FastAPI + LangGraph 后端
│   ├── app.py               # 应用入口（应用工厂 + 路由注册）
│   ├── core/                # 横切关注点（config 等）
│   ├── graph/               # 内容生成工作流定义
│   ├── nodes/               # 意图解析、提纲、写作、自检、核查节点
│   ├── routes/              # 工作流、Trace、认证、工作空间、WebSocket 路由
│   ├── services/            # Artifact、Trace、Rerun 等服务
│   ├── models/              # Pydantic + ORM 模型
│   └── db/                  # PostgreSQL 持久化实现
├── frontend/                # Next.js 前端
│   ├── src/app/             # 页面入口
│   ├── src/components/      # 编辑器、审批、进度等 UI 组件
│   ├── src/contexts/        # 认证与上下文状态
│   └── src/lib/             # API 客户端与公共逻辑
├── db/                      # 初始化 SQL
├── docker-compose.yml       # PostgreSQL / Redis
├── AGENTS.md                # 项目开发指引与技能清单
└── README.md                # 项目总览
```

## 当前边界与后续方向

当前仓库已经具备“可运行的内容主链路”，但还没有完全进入生产态，主要边界如下：

- 内容工作流运行数据默认使用 PostgreSQL 持久化，服务重启后可保留历史；仅在显式切换到内存模式时才会在重启后丢失运行态数据。
- 控制台中的部分列表页、版本对比和工作流编辑保存仍处于骨架或占位状态。
- WebSocket 通道已存在，但节点执行事件尚未全面接入实时推送链路。
- 前后端契约、控制台管理能力和内容链路持久化还需要进一步统一。

下一步更合理的演进方向：

1. 将内容链路全面切换到 PostgreSQL 或统一的持久化存储。
2. 打通工作流编辑器的保存、发布、版本回滚与可执行编译链路。
3. 为内容工作流补齐实时推送、运行列表、筛选与监控面板。
4. 引入更明确的评测、模型路由和质量指标闭环。

## 设计目标

本项目最初的目标，在当前实现中被细化为以下五个方向：

1. 实现用户登录及权限/角色管理。
2. 实现 Prompt Chain 工作流的可视化编排。
3. 实现“一键生成长文/脚本”的自动化流程。
4. 实现不确定点检测与人机门控。
5. 实现任务运行监控、结果回放与定点重跑。

PromptChain 希望把“生成内容”这件事，从不可控的一次性调用，变成可设计、可审查、可恢复、可协作的 AI 工作流。
