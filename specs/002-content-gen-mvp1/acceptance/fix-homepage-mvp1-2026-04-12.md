# MVP1 Homepage 候选分支验收记录（2026-04-12）

## 执行基线

- 执行时间：2026-04-12（Asia/Shanghai）
- 候选 worktree：`/Users/hi/Developer/03-personal/PromptChain/.worktrees/fix-homepage-mvp1`
- 候选分支：`fix-homepage-mvp1`
- 候选修复 commit：`e994c86`
- 合并后主线归档 commit：`7257356`
- 验收目标：确认首页工作流入口最后一个已知代码 blocker 已解除，并判断是否可以把 MVP1 从“待最终 live smoke 复核”推进到“可归档的 sign-off 候选”

## 本轮修复范围

### 前端首页修复

- 修正工作流列表响应解包层级：`response.data.workflows -> response.workflows`
- 修正版本列表响应解包层级：`response.data.versions -> response.versions`
- 切换工作流时重置版本态，避免旧版本残留
- 区分“加载工作流失败”“加载版本失败”“启动工作流失败”三类首页错误提示

### 后端版本接口修复

- 允许 `viewer` 使用 `read` 权限获取首页所需版本列表
- 对 `viewer` 只暴露当前已发布版本
- 不暴露草稿或编辑态历史版本

## Smoke 范围

本轮只验证首页入口候选修复，不重复跑完整 `Smoke A-F`。必验事实为：

1. `viewer` 可见已发布工作流
2. `viewer` 可获取版本列表
3. 版本列表只暴露当前已发布版本
4. 首页可正常启动工作流
5. 不再出现 `Cannot read properties of undefined (reading 'workflows')`

## 环境与准备

- 候选后端服务使用 `fix-homepage-mvp1/backend` 代码启动在 `127.0.0.1:8000`
- 候选前端服务使用 `fix-homepage-mvp1/frontend` 代码启动在 `127.0.0.1:3000`
- 候选后端临时运行环境：
  - 复用主工作区 `.env`
  - 临时切换 `DEFAULT_LLM_PROVIDER=google`
  - 显式设置 `CORS_ORIGINS=http://127.0.0.1:3000`
- 数据样本：
  - `viewer` 用户：`pc_accept_viewer_1773283165@example.com`
  - `viewer` 可访问工作空间：`fcdd9e5a-1cd5-42ab-bac6-f7061fca80d6`
  - 已发布工作流：`1c267aff-ad58-40b6-a152-b2825468ed1d`
  - 已发布版本：`8a993708-cbbf-49a7-9358-02778315b203`

## 验收证据

### 1. viewer 可见已发布工作流

通过候选后端 `GET /api/workflows`，在 `viewer` 工作空间下返回：

- `workflow_count = 1`
- `workflow_name = 验收最小内容流`
- `is_published = true`

结论：`pass`

### 2. viewer 可获取版本列表

通过候选后端 `GET /api/workflows/1c267aff-ad58-40b6-a152-b2825468ed1d/versions`，返回：

- `current_version = 1`
- `versions_count = 1`

结论：`pass`

### 3. 版本列表只暴露当前已发布版本

同一接口返回中只存在：

- `id = 8a993708-cbbf-49a7-9358-02778315b203`
- `snapshot_type = publish`
- `is_current_published = true`

未返回草稿或编辑态历史。

结论：`pass`

### 4. 首页可正常启动工作流

使用 headless Chrome + viewer cookie 打开候选首页，点击示例 prompt 后再点击“启动工作流”，浏览器最终跳转到：

- `http://127.0.0.1:3000/workflow/93754870-0fae-4f41-ba73-2d6da1177008`

同时候选后端日志记录：

- `POST /api/workflow/start -> 200 OK`

结论：`pass`

### 5. 不再出现 `Cannot read properties of undefined (reading 'workflows')`

在候选首页的浏览器自动化记录中：

- `WORKFLOWS_ERROR_COUNT = 0`
- 未捕获到 `Cannot read properties of undefined (reading 'workflows')`

结论：`pass`

## 非阻塞观察

本轮浏览器侧仍捕获到一个与首页入口无直接因果关系的前端异常：

- `ThemeSwitcher` 相关 hydration mismatch

这不是本轮 homepage blocker 的回归点，也未阻止：

- workflow 列表渲染
- version 列表渲染
- 启动按钮执行
- 跳转到 workflow 详情页

因此本轮将其记为**非阻塞观察**，不回退本次 homepage 修复结论。

## 结果结论

### 本轮结论

- `fix-homepage-mvp1` 候选分支上的首页工作流入口代码 blocker 已解除
- 用户先前定义的 5 个验收前提全部满足
- 该修复已具备进入主线归档的条件

### 对 MVP1 状态的影响

- **US1**：从“首页入口待复核”推进为“首页入口 blocker 已解除，可进入最终 sign-off 候选”
- **US2**：从“首页入口待复核”推进为“已恢复 Gate/恢复链路的首页验证前提”
- **US3 / US5**：沿用既有验收状态，不因本轮首页修复变化

### 归档口径

截至 2026-04-12，可以将 MVP1 归档为：

- **实现收口完成**
- **首页入口最后一个已确认代码 blocker 已解除**
- **可进入最终 sign-off 候选**

但不应把这份记录写成“所有后续业务结果都已完全无风险”。本轮只证明 homepage 入口修复通过，不替代后续更高层的业务演示和论文答辩口径管理。
