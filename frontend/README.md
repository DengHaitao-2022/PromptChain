# PromptChain 前端

PromptChain 前端是基于 Next.js App Router、React 19 和 TypeScript 的工作流控制台与内容生成入口。

## 技术栈

- Next.js 16
- React 19
- TypeScript
- Radix UI
- React Flow / XYFlow
- Zustand
- Yjs / y-websocket
- 原生 CSS Modules + 全局 Design Token

## 快速开始

```bash
cd frontend
npm install
printf 'NEXT_PUBLIC_API_URL=http://localhost:8000\n' > .env.local
npm run dev
```

本地访问：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`

## 常用命令

```bash
npm run dev
npm run build
npm run lint
npm run yjs
npm run dev:prod
```

## 主要目录

```text
frontend/
├── src/app/                         # App Router 页面
│   ├── page.tsx                     # 首页工作流启动入口
│   ├── workflow/[id]/page.tsx       # 工作流详情、Gate、Trace、重跑与导出
│   └── console/                     # 控制台、运行记录、工作流、设置页
├── src/components/                  # 内容展示、Trace、进度、编辑器等组件
├── src/contexts/                    # AuthContext / ThemeContext
└── src/lib/                         # API 客户端、认证、主题、时间格式化
```

## 当前主线能力

当前主线基线为 `dev@699bf53`：

- 首页通过 `workflowApi` 拉取已发布工作流、版本、模型供应商并启动任务。
- 工作流详情页支持状态轮询、SSE 快照流、澄清、提纲审批、事实核查审批、暂停/恢复、Trace、Artifact、节点重跑、Markdown 下载和 DOCX 导出。
- 控制台运行记录页通过 `workflowApi.getRuns()` 读取真实运行记录，并提供详情跳转入口。
- 工作流编辑器支持定义、校验、发布、版本对比、恢复与画布状态一致性修复。
- 认证页面覆盖注册、登录、邮箱验证、忘记密码和重置密码。
- 主题系统使用 `primitive -> semantic -> legacy alias` 的 Design Token 分层，集中维护在 `src/app/globals.css`。

## 当前边界

- MVP1 的核心功能已接近验收尾声，但仍需要在 `dev@699bf53` 上完成最终 live smoke。
- `frontend/src/lib/api.ts` 的统一错误归一化在 PR #5，尚未合入 `dev`。
- `frontend/src/lib/auth.ts`、部分设置页和编辑器 hook 仍可能保留旧的 `detail` 错误解析路径，需要在统一错误体系合入后继续收口。
- 前端 lint/build 依赖本地 `node_modules`；若依赖未安装，不能把未运行 lint/build 写成验证通过。

## 协作规则

- 涉及前端代码落地时必须使用独立 `git worktree`。
- Codex 默认负责任务边界、派工提示词、diff review、验收与 merge gate；实际前端编码通常由用户在 IDE 智能助手中执行。
- 用户可见文案默认使用中文，专有名词、协议字段和代码标识除外。
