# PromptChain Next Planning Skill

## Purpose

把 PromptChain 当前仓库状态、共享协作文件和 worktree 状态转成“下一步怎么推进”的可执行规划。

## When To Use

当用户出现以下意图时使用：

- “给我下一步规划”
- “检查当前项目进度”
- “分析所有 worktree 状态”
- “下一步让哪些 agent 开工”
- “现在哪些分支能 CR / merge”
- “给我 5 个 agent 的任务指令”
- “做一次 coordinator 规划”

## Canonical Inputs

固定使用以下绝对路径：

- `/Users/hi/Developer/03-personal/PromptChain/AGENTS.md`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/tasks.md`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-tasks.md`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-locks.json`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/gemini-executions.jsonl`
- `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-handoffs.jsonl`

固定使用以下项目记忆路径：

`mcp__cunzhi__ji(action="回忆", project_path="/Users/hi/Developer/03-personal/PromptChain")`

## Required Workflow

1. 回忆项目记忆。
2. 读取 canonical 协作文件和 `AGENTS.md`。
3. 运行 worktree sync audit：
   - `git worktree list --porcelain`
   - 每个活跃分支的 `branch / base_commit / ahead / behind / dirty`
4. 对照锁表和热点文件 owner：
   - `backend/main.py`
   - `frontend/src/lib/api.ts`
   - `backend/graph/content_generation_graph.py`
   - `frontend/src/app/workflow/[id]/page.tsx`
5. 检查前端分支是否缺少实际执行证据（例如 IDE 智能助手执行记录或用户回报）。
6. 汇总：
   - 已合入基线
   - 进行中
   - blocked
   - ready for CR
   - ready for merge
7. 给出下一步队列：
   - blocker 优先
   - 热点文件冲突优先
   - 可评审工作优先于新开工作
8. 如果规划改变了队列或 gate，向 `subagent-events.jsonl` 追加 coordinator 事件。

## Hard Rules

- coordinator 做 sync audit，不默认替 owner 做 merge/rebase/cherry-pick。
- 前端实际编码默认由用户在 IDE 智能助手中完成，Codex 只做统筹、派工提示词、审查、验收、merge gate。
- 不要把 worktree 内的相对路径副本当作共享事实源。
- 不要把“已经有提交”误判成“已经同步到 dev”。

## Output Format

默认按这个结构输出：

### Findings
- 当前 blocker
- review readiness
- sync 风险

### Progress
- Phase / Story 进度
- agent 维度状态

### Next Queue
- 最多 5 个执行位
- 每项包含 owner、branch、goal、gate

如果用户要求派工，补充 paste-ready agent 指令。

## Notes

- 规划时优先用中文。
- 要引用具体分支名、文件路径、任务号。
- 必须明确区分：`blocked`、`in_progress`、`ready_for_cr`、`ready_for_merge`、`behind_dev`。
