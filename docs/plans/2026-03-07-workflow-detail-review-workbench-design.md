# PromptChain Workflow Detail Review Workbench Design

**Date:** 2026-03-07
**Scope:** `frontend/src/app/workflow/[id]` 详情页的澄清、审批、完成态交互与动画设计
**Design Input:** Gemini CLI `/ui-ux-pro-max` 只读设计分析 + 当前代码结构审阅

## Goal

把当前“状态切换页”重构为更像审阅台的工作流详情页，让用户能在同一屏中感知工作流进度、当前待处理事项和最终交付结果。重点提升三段体验：

- `needs_clarification` 的澄清回合感
- `awaiting_outline_approval` / `awaiting_fact_check_approval` 的审阅与审批感
- `completed` 的交付感与收束感

## Current Problems

### 1. 右侧内容区缺少统一舞台

当前详情页由 `workflow.status` 直接切换组件，右侧内容区在视觉上像“整块替换”，用户能完成任务，但不容易感知自己仍处在同一条工作流里。

### 2. 澄清交互过于表单化

`ClarificationDialog` 目前把所有问题一次性平铺成 `textarea` 列表，更像后台表单，而不是“AI 在这里卡住，需要你补一轮信息”的会话式澄清节点。

### 3. 事实核查审批缺少聚焦路径

`FactCheckViewer` 已经区分了高风险和其他声明，但高风险项仍以整页堆叠展开，导致用户在“先看什么、先决定什么、什么时候可以提交”上没有明确路径。

### 4. 完成态没有交付物仪式感

当前 `completed` 只把 `final_content` 作为 JSON 直接输出。这个结果对调试有帮助，但对用户没有“任务完成、产物可读、可继续处理”的体验。

### 5. 动画只覆盖基础反馈

现有页面只有少量 `slideUp`、hover 和 spinner 动画，没有把“运行中 -> 等待用户 -> 完成”这条状态链串起来。

### 6. 可访问性细节不足

- 错误与状态变化缺少 `aria-live`
- 动效没有统一的 reduced motion 降级策略
- 多组 radio / textarea 的层级和焦点引导不够强

## Visual Direction

### 设计气质

- 专业
- 理性
- 编辑台 / 审阅台
- 深色控制台
- 不走营销页夸张叙事
- 不退化为纯表单后台

### 视觉原则

- 保留现有暗色设计系统，不重做全局主题
- 使用更强的区块层级、细边框、面板高低层来建立“工作台”感
- 图标统一改为 SVG / `lucide-react`，去掉 emoji 图标
- 动效只服务状态理解，不做装饰性大场面

## Explored Approaches

### 方案 A：轻量增强卡片流

保留现有两栏结构和各阶段组件，只加强卡片视觉、按钮区和入场动画。

**优点**

- 实现成本最低
- 风险小
- 不容易引入结构性回归

**缺点**

- 只能改善表层观感
- 对完成态和事实核查聚焦帮助有限

### 方案 B：沉浸式向导

弱化或隐藏左侧时间线，把右侧改造成全屏步骤向导，一次只处理一个阶段。

**优点**

- 聚焦极强
- 适合新手

**缺点**

- 不符合控制台产品定位
- 会削弱“可追踪工作流”的核心感受
- 页面切换感会过强

### 方案 C：协同审阅台

保留左侧时间线作为工作流导航核心，把右侧重构为统一的审阅舞台：顶部阶段摘要，中部任务主体，底部粘性动作条。

**优点**

- 最符合当前产品定位
- 同时保留全局进度和局部决策
- 对澄清、审批、完成态都有明显提升

**缺点**

- 页面和组件都要调整
- 需要更严格的状态样式管理

## Recommended Direction

采用 **方案 C：协同审阅台**。

核心思路：

- 左侧 `WorkflowProgress` 继续承担全局流程可视化
- 右侧所有状态共享同一个 `stage shell`
- 每个阶段都由三段组成：
  - 阶段头部 `StageHeader`
  - 当前任务主体 `StageBody`
  - 吸底动作区 `ActionBar`

这样可以让“运行中、等待澄清、等待审批、已完成”都像同一台工作台上的不同操作模式，而不是四个彼此独立的页面片段。

## Information Architecture

### 1. 页面骨架

#### 左侧：Workflow Rail

- 保留 sticky 时间线
- 增强当前运行步骤的高亮和连接线状态
- 在中断节点显示“等待用户”
- 在完成节点显示更强的正反馈

#### 右侧：Review Workbench

统一为单个主容器，包含：

- `StatusStrip`
  - 当前状态文案
  - 当前阶段标签
  - 辅助说明
- `StageHeader`
  - 阶段标题
  - 阶段说明
  - 当前阶段统计信息
- `StageBody`
  - 澄清 / 提纲 / 事实核查 / 运行中 / 完成态主体
- `ActionBar`
  - 当前页面唯一主动作
  - 次级动作
  - 处理反馈

### 2. 澄清态

定位为“澄清回合”，不是普通问卷。

- 保留多题录入，但视觉上做成编号问题卡
- 显示回答进度，例如“3 个问题，1 个必填未完成”
- 当前聚焦问题高亮，其他问题降权
- 底部动作条显示继续条件

### 3. 事实核查审批态

定位为“异常检测列表”。

- 高风险项优先
- 采用内部双栏：
  - 左侧：风险项导航列表
  - 右侧：当前 claim 的验证详情和决策区
- 低风险项折叠收纳到“已自动通过”分组
- 底部动作条统一提交，不在卡片内部重复放主按钮

### 4. 完成态

定位为“交付结果”。

- 顶部显示完成摘要
- 主体默认显示可读预览
- 同时提供 `结果预览 / 原始数据` 双视图切换
- 提供后续动作入口，例如复制、返回控制台、查看 trace

## Component-Level Design

### `frontend/src/app/workflow/[id]/page.tsx`

- 引入统一的 `stage shell`
- 将各状态的主内容包入共享结构，而不是直接裸渲染
- 为 running / clarification / approval / completed 补充阶段标题和说明
- 完成态改为：
  - 完成摘要卡
  - 预览面板
  - JSON 原始数据标签页
- 错误文案区域加 `role=\"alert\"`

### `frontend/src/app/workflow/[id]/page.module.css`

- 强化右侧主舞台层级
- 补充：
  - status strip
  - stage shell
  - stage header
  - sticky action bar
  - completed preview tabs
- 移动端将两栏压成单栏，左侧时间线改为横向或顶部概览块

### `frontend/src/components/ClarificationDialog/ClarificationDialog.tsx`

- 引入回答进度和必填统计
- 每个问题卡使用明确的 `label` / `textarea`
- 聚焦问题进入强调态
- 保留一次性提交，不改接口协议
- 主按钮由组件底部粘性动作区承载

### `frontend/src/components/ClarificationDialog/ClarificationDialog.module.css`

- 增加问题卡的 hover / focus-within 状态
- 高优先级问题使用警示色边条，而不是只靠 badge
- 增加问题切换和聚焦态的轻量过渡

### `frontend/src/components/FactCheckViewer/FactCheckViewer.tsx`

- 计算一个“当前选中的高风险项”
- 左侧显示高风险列表与状态摘要
- 右侧显示当前 claim 的验证详情、建议修正和决策
- 其他非高风险项折叠到次级分组
- 提交逻辑保持不变，但动作承载切换为统一 action bar

### `frontend/src/components/FactCheckViewer/FactCheckViewer.module.css`

- 新增内部双栏布局
- 风险列表卡支持当前项、已处理项、待处理项三种视觉态
- 决策按钮区改为更清晰的 segmented / option card 风格
- 手动修正输入框在选中时展开

### `frontend/src/components/WorkflowProgress/WorkflowProgress.tsx`

- 用 SVG/Lucide 图标替代字符与 emoji 视觉
- 当前运行节点增加脉冲环
- 中断节点更明确显示“等待用户”
- 保持点击能力，但只作为辅助导航

### `frontend/src/components/WorkflowProgress/WorkflowProgress.module.css`

- 强化连接线状态
- 当前节点用品牌色 glow/pulse
- 完成节点和连接线视觉更稳定，不需要大幅动画
- 失败节点明确断开

### `frontend/src/components/OutlineEditor/OutlineEditor.tsx`

- 不重做其内部核心编辑逻辑
- 只在整页集成时补齐与 stage shell 的风格统一
- 底部按钮区与其它阶段的 action bar 对齐

## Motion System

### 动画目标

- 强化阶段切换的连续性
- 强化主动作反馈
- 缩短等待焦虑
- 不影响工作台阅读效率

### 动画规范

#### 1. 阶段入场

- 属性：`opacity`, `transform: translateY(8px)`
- 时长：`220ms`
- 曲线：`ease-out`
- 用途：stage body 首次出现、状态切换后主体刷新

#### 2. 区块切换

- 属性：`opacity`, `transform: translateY(4px)`
- 时长：`180ms`
- 曲线：`ease-out`
- 用途：标签页切换、列表详情区切换

#### 3. 运行中强调

- 属性：`box-shadow`, `opacity`
- 时长：`1400ms`
- 曲线：`ease-in-out`
- 用途：当前运行节点脉冲、running 状态提示
- 限制：全页只允许 1 到 2 个循环动效

#### 4. 成功反馈

- 属性：`transform: scale(1.02 -> 1)`
- 时长：`240ms`
- 曲线：`cubic-bezier(0.22, 1, 0.36, 1)`
- 用途：完成 badge、提交成功后的摘要卡

#### 5. Hover / Focus

- 属性：`background-color`, `border-color`, `box-shadow`, `transform`
- 时长：`120ms` 到 `160ms`
- 曲线：`ease`
- 用途：问题卡、风险列表项、按钮、标签

### Reduced Motion

在 `prefers-reduced-motion: reduce` 下：

- 取消 pulse、scale、滑入位移
- 保留最短淡入或直接无动画
- 所有 transition 缩短到近似 0
- 禁止平滑滚动

## Accessibility Notes

- 所有主状态变化文案使用 `aria-live=\"polite\"`
- 错误提示使用 `role=\"alert\"`
- icon-only 控件必须带可访问名称
- 提交按钮和关键输入维持可见 focus ring
- 不能只靠颜色表达风险与状态，需要图标或文本辅助

## Implementation Priority

### P0：详情页骨架与完成态

- 先建立统一 `stage shell`
- 先把 `completed` 从 JSON 输出改成交付预览 + 原始数据双视图

### P1：事实核查审批重构

- 这是交互提升最大的部分
- 优先改成内部双栏审阅流

### P2：澄清态增强

- 强化会话感、聚焦态、进度提示

### P3：时间线与 running 态增强

- 增加工作流 rail 的状态动量
- 让等待过程更有过程感

### P4：统一动画与 reduced motion

- 最后统一收口所有状态切换和动画边界

## Acceptance Criteria

- 详情页在所有状态下都共享统一舞台结构
- `ClarificationDialog` 不再像裸表单
- `FactCheckViewer` 对高风险项的处理路径更清晰
- `Completed` 态具备“交付完成”的视觉和信息层级
- 动画有统一规范，且支持 reduced motion
