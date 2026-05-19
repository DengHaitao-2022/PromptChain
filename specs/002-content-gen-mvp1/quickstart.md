# Quickstart: PromptChain 内容生成系统 MVP1

本文档用于 `dev@8218f54` 的 MVP1 验收基线，重点收口 US1 / US2 / US3 / US4 / US5 的 quickstart、smoke 与 access 验证边界。本文只记录当前主线事实、外部依赖和下一轮必须执行的人工 smoke，不把“代码已合入”“静态 review 通过”或“PR 候选通过 CodeQL”误记为“集成完成”。

补充说明：2026-04-10 已执行一次 current-dev 验收回归。用户口述的 latest local `dev` 为 `cb79009`，但本工作区实际执行基线为 `dev@698b80d`。本次 live 证据与 blocked 结论统一记录在 [`specs/002-content-gen-mvp1/acceptance/current-dev-2026-04-10.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/current-dev-2026-04-10.md)。
2026-04-12 又在候选分支 `fix-homepage-mvp1@e994c86` 上执行了一轮 homepage 专项 live smoke，结果记录在 [`specs/002-content-gen-mvp1/acceptance/fix-homepage-mvp1-2026-04-12.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/fix-homepage-mvp1-2026-04-12.md)。该轮验证确认首页入口最后一个已知代码 blocker 已解除。

## 0. 当前主线快照（`dev@8218f54`）

- 已在当前 `dev` 合入并可作为验收前提复用：
  - Google provider 支持：`GEMINI_API_KEY` + `DEFAULT_LLM_PROVIDER=google`
  - 认证闭环：`register -> verify-email -> login` 与 `forgot-password -> reset-password -> login`
  - 登录、`/api/me`、角色菜单与工作空间上下文
  - 工作流列表 / 草稿保存 / 校验 / 显式发布 / 版本恢复
  - 首页通过共享 runtime client 拉取已发布工作流和版本并启动任务
  - 详情页 Gate、pause/resume、trace、意图卡 / 提纲 / 终稿展示、SSE 快照流、节点重跑、重跑历史与 DOCX 导出
  - `console/runs` 通过 `workflowApi.getRuns()` 展示真实运行记录列表
  - 工作流运行计划 `runtime_plan` 已支持把已发布可视化定义编译为当前内容生成引擎可执行的受限运行计划
- 本轮验收收口约定：
  - `T045 / T046` 视为已收口前提，本轮不再打开文案或错误路径实现
  - `T042` 只做 auth/access 验收闭环，不重复实现认证功能
  - `T037` 必须覆盖运行记录、Trace、Artifact history、rerun、SSE 快照与 DOCX 导出，不再只看占位页面
  - 若缺少外部依赖，只能记为“静态通过”或“待 smoke”，不能记为“集成完成”
- 当前 PR 候选边界：
  - PR #5：统一错误体系与 `frontend/src/lib/api.ts` 错误归一化，CodeQL 通过且 mergeable，但尚未合入 `dev`
  - PR #4：生产 CI/CD 与部署基线，CodeQL 通过但 PR CI 的后端质量检查和前端质量检查失败，不能作为已完成生产部署基线

### 术语说明

- 主线覆盖：代码、页面或接口已经在 `dev`
- 静态通过：已完成代码、契约或 review 核对，但本轮未在当前 `dev` 实机跑通
- 人工 smoke：必须在当前 `dev` 与有效环境上执行，完成后才能进入 acceptance sign-off

### US1 / US2 / US3 / US5 验收归档矩阵

| Story | 当前主线覆盖 | 当前归类 | 下一步 |
|---|---|---|---|
| US1 | 首页工作流/版本选择、详情页关键产物展示、Google provider 支持、完成态阅读与导出入口已在 `dev` | 静态通过，待人工 smoke | 跑 Smoke E 的标准生成链路，并在完成态复核终稿展示与导出 |
| US2 | clarify / outline approval / fact-check approval / pause / resume API 与详情页交互已在 `dev` | 静态通过，待人工 smoke | 跑 Smoke E 的 Gate 路径与 Smoke F |
| US3 | save / validate / publish / published-only visibility 已在 `dev` | 静态通过，待人工 smoke | 跑 Smoke D |
| US4 | `console/runs` 真数据、Trace、Artifact history、rerun、SSE 与 DOCX 导出已在 `dev` | 静态通过，待人工 smoke | 跑 Smoke G |
| US5 | auth-flow 页面、`/api/me`、菜单守卫、运行态 ownership guard 已在 `dev` | auth-flow 有历史 smoke 证据；当前 `dev` 仍待 access smoke | 跑 Smoke A / B / C 与负向权限校验 |

## 1. 环境前提

- 已启动 PostgreSQL 与 Redis 基础设施
- 后端服务可访问
- 前端服务可访问
- 至少准备一个可接收邮件或可查看后端日志的测试邮箱
- 至少存在一个工作空间，并完成 `viewer / editor / admin` 角色分配
- 至少存在一个可运行的已发布工作流版本；若没有，先执行 Smoke D
- US1 / US2 的 live smoke 需要至少一种可用 LLM 环境：
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GEMINI_API_KEY` 且 `DEFAULT_LLM_PROVIDER=google`
  - 或可访问的 `OLLAMA_BASE_URL`
- 若没有有效 LLM 环境，Smoke E / F 只能记为“环境阻塞”或“静态通过”，不能记为通过

## 2. 启动本地环境

### 基础设施

```bash
cd /Users/hi/Developer/03-personal/PromptChain
docker compose up -d postgres redis
```

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

### 运行地址

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`

### 开发模式邮件说明

- 若未配置 SMTP，注册验证链接和密码重置链接不会真正发邮件，而是直接打印在后端服务日志中
- 本地验收时可直接从后端日志中复制 `verify-email` 或 `reset-password` 链接到浏览器打开

## 3. Smoke Test A：注册、邮箱验证与登录

### 目标

验证 `register -> verify-email -> login` 最小闭环，以及未验证邮箱的登录拦截。

### 验收归档

- 关联故事：US5 / `T042`（auth-flow 子路径）
- 当前状态：认证页面与接口已在 `dev`；历史 feature 分支存在 smoke 记录，但本轮未在当前 `dev` 重新执行
- 本轮结论：可作为 acceptance review 的必跑回归项，但不能单独代表 US5 全部通过

### 步骤

1. 访问注册页 `http://localhost:3000/register`
2. 使用一个新邮箱完成注册，确认页面停留在“去验证邮箱”的成功态，而不是自动跳转
3. 在未验证前访问登录页并尝试登录，确认前端收到“请先验证您的邮箱”之类的拦截提示
4. 若已配置 SMTP，则从邮件中打开验证链接；若未配置 SMTP，则从后端日志中复制 `http://localhost:3000/verify-email?token=...` 链接打开
5. 在验证页确认出现成功提示，并按引导返回 `/login`
6. 使用刚刚验证完成的账号登录
7. 打开控制台首页，确认页面不再跳回登录页
8. 通过浏览器或 API 调用 `GET /api/me`，确认当前工作空间与角色已返回

### 预期结果

- 注册成功后页面明确引导用户先验证邮箱，再返回登录
- 未验证邮箱不能登录
- `verify-email` 页面能正确处理 loading、缺 token、无效/过期 token、验证成功四种状态
- 邮箱验证成功后可正常登录
- 登录成功后浏览器持有 Cookie 会话
- `GET /api/me` 能返回当前用户与工作空间上下文

## 4. Smoke Test B：忘记密码、重置密码与重新登录

### 目标

验证 `forgot-password -> reset-password -> login` 最小闭环，并确认忘记密码成功态不泄露邮箱是否存在。

### 验收归档

- 关联故事：US5 / `T042`（auth-flow 子路径）
- 当前状态：页面与接口已在 `dev`；历史 feature 分支存在 smoke 记录，但本轮未在当前 `dev` 重新执行
- 本轮结论：与 Smoke A 一起构成 auth-flow 回归基线；仍不能替代 access boundary smoke

### 步骤

1. 访问忘记密码页 `http://localhost:3000/forgot-password`
2. 输入一个已注册邮箱并提交
3. 确认页面显示中性成功态：“如果该邮箱已注册，您将收到密码重置邮件”
4. 若已配置 SMTP，则从邮件中打开重置链接；若未配置 SMTP，则从后端日志中复制 `http://localhost:3000/reset-password?token=...` 链接打开
5. 在重置密码页输入新密码和确认密码，验证本地校验会拦截密码不一致或长度不足
6. 提交成功后按引导返回 `/login`
7. 使用新密码重新登录

### 预期结果

- 忘记密码成功态不泄露邮箱是否存在
- `reset-password` 页面能正确处理缺 token、无效/过期 token、密码不一致、密码过短、重置成功等状态
- 密码重置成功后可使用新密码登录

## 5. Smoke Test C：登录后的身份边界与角色访问

### 目标

验证 Cookie 会话、`/api/me` 身份读取、菜单隔离和越权访问边界。

### 验收归档

- 关联故事：US5 / `T042`（access boundary）
- 当前状态：角色菜单、`/api/me`、runtime ownership guard 与工作空间级过滤逻辑已在 `dev`
- 本轮结论：当前只完成静态核对；必须在当前 `dev` 做跨角色 smoke 与负向 API 校验

### 步骤

1. 分别准备 `viewer`、`editor`、`admin` 三个已验证账号，并登录对应会话
2. 对每个角色调用 `GET /api/me`，记录 `workspace` 与 `role` 返回值
3. 在前端控制台核对导航：
   - `viewer` 应可见首页、运行记录，不应看到成员管理或模型/密钥/审计菜单
   - `editor` 应额外可进入工作流编辑/发布入口
   - `admin` 应可看到成员、模型、密钥、审计等管理入口
4. 用 `viewer` 与 `editor` 直接访问 `/console/settings/members`、`/console/settings/models` 或对应管理 API，确认前端守卫与后端授权都拦截
5. 用一个非管理员账号尝试访问其他用户的 `workflow` / `trace` / `artifact` 资源，确认返回 `403` 或 `404`，且不泄露资源内容
6. 用 `admin` 账号验证同工作空间下的运行记录、成员页和管理接口可正常打开

### 预期结果

- `GET /api/me` 返回的角色与前端菜单一致
- 普通用户只能运行已发布工作流、查看本人任务、处理 Gate
- 设计者可进入工作流编辑/发布入口
- 管理员可查看成员、日志和全量任务
- 越权访问管理入口或他人运行态资源时，不得返回非授权内容

## 6. Smoke Test D：工作流草稿、校验与发布

### 目标

验证“草稿”和“已发布版本”的分离，以及普通用户只能看到已发布版本。

### 验收归档

- 关联故事：US3 / `T031`
- 当前状态：编辑器、保存、校验、发布、工作流列表与版本恢复已在 `dev`
- 本轮结论：当前只有主线覆盖与静态核对，仍需 current-dev 人工 smoke

### 步骤

1. 使用 `editor` 账号进入工作流列表或编辑器页面
2. 创建一个最小工作流草稿，至少包含入口、处理、Gate、输出等核心节点
3. 保存草稿并重新打开，确认节点与连线仍存在
4. 故意制造一个非法流程并执行校验，确认发布前会被拦截并展示原因
5. 修复非法项后发布该工作流
6. 切换到 `viewer` 账号，确认首页与工作流可运行列表只能看到已发布版本

### 预期结果

- 草稿保存不等于发布
- 非法流程无法发布，且能看到明确校验反馈
- 发布动作产生可运行版本
- 未发布流程不会出现在普通用户的可运行列表中

## 7. Smoke Test E：标准生成链路与 Gate

### 目标

验证“意图卡 → 提纲 → 写作 → 自检修订 → 事实核查/终稿”的主链路，以及 Gate 中断后继续执行。

### 验收归档

- 关联故事：US1 / `T017`，US2 / `T024`
- 当前状态：首页 runtime client、详情页关键产物展示、Gate 交互和 Google provider 支持均已在 `dev`
- 本轮结论：必须至少跑 1 条标准主链路任务与 1 条触发 Gate 的任务；缺少有效 LLM 环境时只能记为“环境阻塞”

### 步骤

1. 使用 `viewer` 账号登录首页，选择一个已发布工作流和版本
2. 启动 1 条标准内容生成任务，优先使用能稳定完成的低风险提示词
3. 观察任务状态变化，确认至少能看到运行态和当前节点
4. 任务完成后查看意图卡、提纲、终稿和关键中间产物
5. 再启动 1 条更容易触发澄清、提纲审批或事实核查的任务
6. 若任务触发澄清 Gate，提交回答后继续执行
7. 若任务触发提纲审批 Gate，执行确认、修改或重生成
8. 若任务触发事实核查审批 Gate，提交决策并继续执行
9. 确认 Gate 回答后任务从中断位置恢复，而不是从头重跑

### 预期结果

- 状态流转符合 `running / needs_clarification / awaiting_outline_approval / awaiting_fact_check_approval / completed / failed / paused`
- 每个 Gate 最多给出 1-3 个关键问题
- 提交 Gate 回答后从中断位置继续，而不是从头重跑
- 中间产物至少包含意图卡、提纲、自检结果和终稿
- US1 不应只靠“能触发 Gate”来签收；US2 也不应只靠“无 Gate 标准链路”来签收

## 8. Smoke Test F：手动暂停与恢复

### 目标

验证与 Gate 无关的用户主动暂停/恢复能力。

### 验收归档

- 关联故事：US2 / `T024`
- 当前状态：pause 与 Gate 状态分离、接口与详情页交互已在 `dev`
- 本轮结论：当前只做静态核对；需要 live smoke 证明暂停后状态可持续读取、恢复后上下文不丢

### 步骤

1. 启动一个相对较长的内容生成任务
2. 在任务运行过程中触发“暂停”
3. 刷新页面或重新进入任务详情，确认状态仍为 `paused`
4. 触发“恢复”
5. 观察任务从原执行点继续

### 预期结果

- 手动暂停不会丢失当前上下文和已生成产物
- 恢复后不会重复生成已经确认的阶段内容
- `paused` 与三个 Gate 状态不会混淆
- 验收时应以“节点完成后进入 paused 读模型”为准，不要求中断同一 HTTP 请求中的正在执行节点

## 9. Smoke Test G：回放、产物历史、重跑与导出

### 目标

验证任务可回放、产物可追踪、rerun 有版本链，并且完成态最终产物可以导出。

### 验收归档

- 关联故事：US4（本轮非主签收范围）
- 当前状态：`trace`、`artifact history`、`rerun`、SSE 快照流、DOCX 导出与 `console/runs` 真数据列表都已在 `dev`
- 本轮结论：US4 已具备验收入口，但仍需在当前 `dev@8218f54` 上跑 live smoke 后才能签收

### 步骤

1. 打开 `/console/runs` 或一个已完成任务的详情页
2. 查看节点时间线、节点输入输出、异常记录和人工干预记录
3. 打开某个 Artifact 的版本历史
4. 从指定节点发起 rerun
5. 确认系统创建新的任务实例，并保留与原任务的关联信息
6. 在已完成任务详情页点击导出 DOCX，确认下载文件可打开且包含最终产物内容

### 预期结果

- 任务完成或失败后都可以回放
- 每个节点的 `NodeRun` 和相关 `Artifact` 可追溯
- rerun 会生成新任务和新产物版本，不会覆盖旧记录
- DOCX 导出仅允许已完成任务，未完成任务应返回明确错误
- SSE 快照流可以增强详情页实时体验，但 REST 状态与 Trace 仍是最终对账入口

## 10. 快速 API 验证示例

以下命令用于最小化验证会话与运行态接口。它们依赖目标功能已经实现完成。

```bash
API=http://localhost:8000

# 登录并保存 Cookie
curl -c cookies.txt -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"verified@example.com","password":"password123"}'

# 查看当前身份
curl -b cookies.txt "$API/api/me"

# 查看运行记录列表
curl -b cookies.txt "$API/api/workflow/runs"

# 启动工作流
curl -b cookies.txt -X POST "$API/api/workflow/start" \
  -H "Content-Type: application/json" \
  -d '{"user_input":"写一篇面向初学者的 Prompt Chain 介绍文章","workflow_definition_id":"<published_workflow_id>","workflow_version_id":"<published_version_id>"}'

# 查看工作流状态
curl -b cookies.txt "$API/api/workflow/<workflow_run_id>"

# 查看 SSE 事件流
curl -N -b cookies.txt "$API/api/workflow/<workflow_run_id>/events"

# 导出已完成任务的 DOCX
curl -L -b cookies.txt "$API/api/workflow/<workflow_run_id>/exports/docx" \
  -o PromptChain-final.docx

# 负向权限示例：非管理员或非 owner 访问他人运行态资源时应返回 403 或 404
curl -b viewer-cookies.txt "$API/api/trace/<other_users_workflow_run_id>"
```

## 11. Current-dev 验收执行结果（2026-04-10，`dev@698b80d`）

### 结果摘要

| Smoke | 状态 | 类型 | 当前结论 |
|---|---|---|---|
| Smoke A | blocked | 静态通过 + 运行阻塞 | `/register` 页面可达，但 `POST /api/auth/register` 因 PostgreSQL `Connection refused` 返回 `500` |
| Smoke B | blocked | 静态通过 + 运行阻塞 | `/forgot-password` 页面可达，但 `POST /api/auth/forgot-password` 同样因 PostgreSQL 不可达返回 `500` |
| Smoke C | blocked | 静态通过 | `/api/me` 未登录返回 `401` 正常，但无法建立任意已验证会话，角色/越权 smoke 未执行 |
| Smoke D | blocked | 静态通过 | 无法建立 editor 会话，也无法访问工作流持久化链路 |
| Smoke E | blocked | 静态通过 | PostgreSQL 不可达；同时当前默认 provider 指向 `anthropic` 且无有效 key |
| Smoke F | blocked | 静态通过 | 依赖 Smoke E 的长任务无法启动 |

### Story 状态

| Story | current-dev 状态 | 当前结论 |
|---|---|---|
| US1 / `T017` | blocked | 标准生成链路未跑通；保留主线覆盖事实，不能签收 |
| US2 / `T024` | blocked | Gate 与 pause/resume 未进入 live smoke；不能签收 |
| US3 / `T031` | blocked | 草稿/校验/发布未进入 live smoke；不能签收 |
| US5 / `T042` | blocked | auth/access 回归未完成；不能签收 |

### 当前 blocker

- 基础设施 blocker：`docker compose ps` 返回 `Cannot connect to the Docker daemon`，调试后端日志进一步确认 DB 访问落到 `localhost:5432 Connection refused`
- LLM blocker：`backend/.env` 中 `DEFAULT_LLM_PROVIDER=anthropic` 且 `ANTHROPIC_API_KEY` 为空；虽然 `GEMINI_API_KEY` 已配置，但当前默认 provider 未切到 `google`
- 详细证据、命令回显与日志摘录见 [`specs/002-content-gen-mvp1/acceptance/current-dev-2026-04-10.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/current-dev-2026-04-10.md)

## 12. Latest-dev 验收状态（2026-05-20，`dev@8218f54`）

### 当前结论

- 实现侧：MVP1 核心功能已进入尾声，当前主线包含首页启动、工作流编辑/发布、运行详情、Gate、Trace、Artifact、Rerun、运行记录总览与 DOCX 导出。
- 验收侧：仍不能把 MVP1 写成最终通过，因为 `dev@8218f54` 尚未补一轮完整 live smoke。
- 生产侧：仍不能写成生产可用，因为独立 worker、版本化迁移、完整 CI/CD、可观测性、限流/重试/熔断等能力还未主线闭环。

### 必跑 smoke

1. Smoke A / B / C：认证、密码重置、角色菜单与越权访问
2. Smoke D：草稿、校验、发布、viewer 已发布可见性
3. Smoke E：标准生成链路与至少一个 Gate 路径
4. Smoke F：手动暂停与恢复
5. Smoke G：运行记录、Trace、Artifact history、Rerun、SSE、DOCX 导出

### PR 候选边界

- PR #5 的统一错误体系不属于当前 `dev@8218f54` 主线事实；合入前不得把统一错误 envelope 写成已发布 API 契约。
- PR #4 的生产 CI/CD 基线存在失败 checks；修复前不得把它写成生产交付完成。

## 13. Acceptance Review Gate

本轮 current-dev smoke 已执行，但 `US1 / US2 / US3 / US5` 仍存在明确环境 blocker，因此当前状态是“可进入 acceptance review 的阻塞审查”，不是“可直接签收”。

## 14. Homepage 候选修复复核（2026-04-12，`fix-homepage-mvp1@e994c86`）

### 结果摘要

| 检查项 | 状态 | 当前结论 |
|---|---|---|
| viewer 可见已发布工作流 | pass | 候选后端 `GET /api/workflows` 返回 1 条已发布 workflow |
| viewer 可获取版本列表 | pass | 候选后端 `GET /versions` 返回当前版本 |
| 版本列表只暴露当前已发布版本 | pass | viewer 只看到 `snapshot_type=publish` 的当前版本 |
| 首页可正常启动工作流 | pass | 候选首页点击“启动工作流”后跳转至 `/workflow/<id>` |
| 不再出现 `Cannot read properties of undefined (reading 'workflows')` | pass | 候选浏览器自动化记录 `WORKFLOWS_ERROR_COUNT = 0` |

### 补充观察

- 浏览器侧仍有 `ThemeSwitcher` hydration mismatch 观察项，但它未阻止 workflow 列表渲染、版本列表渲染或首页启动动作
- 这条观察项不回退 homepage blocker 解除结论

### 结论

- 首页工作流入口最后一个已确认代码 blocker 已解除
- `US1 / US2` 从“首页入口待复核”推进为“可进入最终 sign-off 候选”
- 详细证据见 [`specs/002-content-gen-mvp1/acceptance/fix-homepage-mvp1-2026-04-12.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/fix-homepage-mvp1-2026-04-12.md)

### 已归档的结论

- US1：实现仍在 `dev`，但 2026-04-10 的 current-dev smoke 因环境阻塞未执行到 live 生成链路，当前不能签收
- US2：实现仍在 `dev`，但 Gate 与 pause/resume 未进入 live smoke，当前不能签收
- US3：实现仍在 `dev`，但草稿/校验/发布未进入 live smoke，当前不能签收
- US5：auth-flow 页面与 `/api/me` 仍在 `dev`，但 auth/access 回归被数据库 blocker 截断，当前不能签收

### 环境恢复后必须重跑的 smoke 清单

1. 先跑 Smoke D，确保存在一个当前 `dev` 下新建并成功发布的最小工作流版本
2. 跑 Smoke E 的标准主链路任务，验证 US1 在有效 LLM 环境下可从首页跑到终稿
3. 跑 Smoke E 的 Gate 路径任务，验证 US2 的 clarification / outline / fact-check 至少命中 1 条真实中断与恢复路径
4. 跑 Smoke F，验证手动 pause / resume 的状态保持与上下文连续性
5. 跑 Smoke A + B，确认 auth-flow 在当前 `dev` 上未被后续提交回归
6. 跑 Smoke C 与负向 API 校验，确认角色菜单、`/api/me`、跨用户运行态资源访问和管理入口边界都正确

### 记录规则

- 若某项因缺少邮件、工作空间种子或有效 LLM 凭证而无法执行，只能记录为“环境阻塞”，不能写成“通过”
- 若某项首先被数据库、Redis、Docker daemon 或默认 provider 配置阻断，也只能记录为“环境阻塞”，不能回写成失败实现或通过
- 若某项只有代码 review、契约核对或 feature branch 历史 smoke 证据，只能记录为“静态通过”，不能写成“集成完成”
- 本轮通过的产物应直接附着在 acceptance review 记录中，不要再把实现任务重新打开
