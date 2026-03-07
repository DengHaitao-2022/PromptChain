# 项目上下文信息

- 项目名称: PromptChain
技术栈: Python FastAPI + LangGraph + PostgreSQL
功能: 基于Prompt Chain的自动化内容生成系统

核心模块:
1. 意图解析 - 结构化意图卡生成
2. 提纲生成 - HITL中断审批
3. 事实核查 - CoVe四步验证链
4. 内容生成 - 分段+Self-Refine
5. Artifact版本化 - 不可覆盖存储+版本链

工作流: parse_intent → generate_outline → generate_content → self_refine → check_facts → finalize

关键设计:
- 每个节点创建NodeRun记录
- 每个产物落库为Artifact（版本递增，不覆盖）
- LLM调用使用get_current_model_info()动态获取配置
- PostgreSQL持久化存储（db/postgres_store.py）
- 核心功能规划：1. 登录与权限/角色管理 2. Prompt Chain工作流可视化编排 3. 一键生成长文/脚本 4. 不确定点检测与人机门控 5. 任务监控与结果回放。技术栈：Spring Boot(权限管理)、Python/FastAPI(AI工作流)、Next.js前端。
- PromptChain 当前仓库技术栈以代码和 AGENTS.md 为准：后端为 FastAPI + LangGraph + SQLAlchemy，前端为 Next.js App Router + React + TypeScript，基础设施为 PostgreSQL + Redis。若历史记忆中出现 Spring Boot 等描述，应视为过时信息。
