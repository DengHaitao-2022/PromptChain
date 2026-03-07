# Quickstart: PromptChain 内容生成系统 MVP1

本文档描述目标功能完成后的最小验收路径。若任一步无法完成，说明该功能还未达到本计划定义的交付标准。

## 1. 环境前提

- 已启动 PostgreSQL 与 Redis 基础设施
- 后端服务可访问
- 前端服务可访问
- 至少存在一个已验证邮箱的测试用户
- 至少存在一个工作空间，并完成成员角色分配

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
uv run uvicorn main:app --reload --port 8000
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

## 3. Smoke Test A：登录与身份边界

### 目标

验证 Cookie 会话、`/api/me` 身份读取和业务角色映射。

### 步骤

1. 访问登录页 `http://localhost:3000/login`
2. 使用已验证邮箱的测试用户登录
3. 打开控制台首页，确认页面不再跳回登录页
4. 通过浏览器或 API 调用 `GET /api/me`，确认当前工作空间与角色已返回
5. 使用不同角色重复上述流程，确认菜单与操作范围符合预期

### 预期结果

- 未验证邮箱不能登录
- 登录成功后浏览器持有 Cookie 会话
- 普通用户只能运行已发布工作流、查看本人任务、处理 Gate
- 设计者可进入工作流编辑/发布入口
- 管理员可查看成员、日志和全量任务

## 4. Smoke Test B：工作流草稿、校验与发布

### 目标

验证“草稿”和“已发布版本”的分离，以及普通用户只能看到已发布版本。

### 步骤

1. 使用设计者账号进入工作流列表或编辑器页面
2. 创建一个最小工作流草稿，至少包含入口、处理、Gate、输出等核心节点
3. 保存草稿并重新打开，确认节点与连线仍存在
4. 执行工作流合法性校验，确认非法流程会被拦截
5. 发布该工作流
6. 切换到普通用户账号，确认只能选择已发布版本发起任务

### 预期结果

- 草稿保存不等于发布
- 发布动作产生可运行版本
- 未发布流程不会出现在普通用户的可运行列表中
- 非法流程无法发布

## 5. Smoke Test C：标准生成链路与 Gate

### 目标

验证“意图卡 → 提纲 → 写作 → 自检修订 → 事实核查/终稿”的主链路，以及 Gate 中断后继续执行。

### 步骤

1. 使用普通用户账号发起一个内容生成任务
2. 观察任务状态变化，确认至少能看到运行态和当前节点
3. 若任务触发澄清 Gate，提交回答后继续执行
4. 若任务触发提纲审批 Gate，执行确认、修改或重生成
5. 若任务触发事实核查审批 Gate，提交决策并继续执行
6. 任务完成后查看终稿和全部中间产物

### 预期结果

- 状态流转符合 `running / needs_clarification / awaiting_outline_approval / awaiting_fact_check_approval / completed / failed / paused`
- 每个 Gate 最多给出 1-3 个关键问题
- 提交 Gate 回答后从中断位置继续，而不是从头重跑
- 中间产物至少包含意图卡、提纲、草稿、自检结果、终稿

## 6. Smoke Test D：手动暂停与恢复

### 目标

验证与 Gate 无关的用户主动暂停/恢复能力。

### 步骤

1. 启动一个长内容任务
2. 在任务运行过程中触发“暂停”
3. 刷新页面或重新进入任务详情，确认状态仍为 `paused`
4. 触发“恢复”
5. 观察任务从原执行点继续

### 预期结果

- 手动暂停不会丢失当前上下文和已生成产物
- 恢复后不会重复生成已经确认的阶段内容
- `paused` 与三个 Gate 状态不会混淆

## 7. Smoke Test E：回放、产物历史与重跑

### 目标

验证任务可回放、产物可追踪、rerun 有版本链。

### 步骤

1. 打开一个已完成任务的详情页或回放页
2. 查看节点时间线、节点输入输出、异常记录和人工干预记录
3. 打开某个 Artifact 的版本历史
4. 从指定节点发起 rerun
5. 确认系统创建新的任务实例，并保留与原任务的关联信息

### 预期结果

- 任务完成或失败后都可以回放
- 每个节点的 `NodeRun` 和相关 `Artifact` 可追溯
- rerun 会生成新任务和新产物版本，不会覆盖旧记录

## 8. 快速 API 验证示例

以下命令用于最小化验证会话与运行态接口。它们依赖目标功能已经实现完成。

```bash
API=http://localhost:8000

# 登录并保存 Cookie
curl -c cookies.txt -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"verified@example.com","password":"password123"}'

# 查看当前身份
curl -b cookies.txt "$API/api/me"

# 启动工作流
curl -b cookies.txt -X POST "$API/api/workflow/start" \
  -H "Content-Type: application/json" \
  -d '{"user_input":"写一篇面向初学者的 Prompt Chain 介绍文章"}'

# 查看工作流状态
curl -b cookies.txt "$API/api/workflow/<workflow_run_id>"
```

## 9. 完成标准

当以下条件全部满足时，可认为 MVP1 已达到本计划要求：

- 登录、权限、工作流编辑、任务运行、Gate、暂停/恢复、回放都可独立演示
- 运行态契约和前端类型一致
- 任务重启后仍可恢复上下文和查看回放
- 运行轨迹可通过 `WorkflowRun`、`NodeRun`、`Artifact` 串联出来
- 所有关键用户可见文案保持中文
