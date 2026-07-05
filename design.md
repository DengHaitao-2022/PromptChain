# PromptChain UI Design Guide

> 适用范围：PromptChain 商业化产品界面、Novel Workbench 小说深度样板、后续多场景内容生成工作台截图与前端页面设计。
>
> 关键约束：**不要使用蓝紫配色**。后续页面与截图不得再采用偏蓝紫、赛博紫、霓虹紫、蓝紫渐变作为主视觉。

---

## 1. 当前项目 UI 观察

当前前端已经具备一套比较完整的主题体系，设计上不是零散写颜色，而是通过 `globals.css` 定义 design token，并采用：

```text
primitive token → semantic token → legacy alias
```

当前项目具有以下 UI 特征：

1. 支持 `dark / light / system` 三种主题偏好。
2. 根节点通过 `html[data-theme='dark']` 与 `html[data-theme='light']` 切换主题。
3. 当前默认解析主题为 dark。
4. 页面使用控制台壳体结构：左侧导航、顶部栏、主内容区。
5. UI 风格偏现代 SaaS 控制台：圆角卡片、半透明面板、轻微毛玻璃、细边框、柔和阴影、状态徽标。
6. 控制台使用 `console.module.css` 进一步定义 console 级变量，例如 sidebar、topbar、surface、nav、accent、shadow。
7. 首页 dashboard 使用 hero card、stats grid、content grid、action card、status badge 等组件结构。

当前代码中已有的主题色倾向：

```text
现有主色：cyan / sky blue
现有强调色：amber
现有基础色：slate / near-black / white
现有状态色：green / amber / red / cyan
```

由于用户明确要求“不要使用蓝紫配色”，后续商业化视觉不应继续强化蓝紫科技感，而应将 PromptChain 迁移到更稳重、创作工具感更强的配色方向。

---

## 2. 新主题方向

### 2.1 设计关键词

PromptChain 商业化产品后续应采用以下关键词：

```text
专业、克制、沉浸、可信、结构化、创作工作台、可追踪、长期记忆
```

小说深度样板尤其要避免“通用 AI 聊天工具”的感觉，应更像：

```text
专业写作工作台 + 故事资料库 + 运行审计台 + 创作控制台
```

### 2.2 推荐主视觉方向

推荐采用：

```text
墨黑 / 石墨灰 / 森林绿 / 琥珀金 / 羊皮纸暖白
```

这套色彩比蓝紫更适合小说创作场景，既有商业软件的专业感，也有长篇写作、档案、手稿、故事 Bible 的沉浸感。

---

## 3. 色彩规范

### 3.1 禁止色彩

以下颜色不得作为主视觉或大面积强调色：

```text
#6366f1  indigo
#8b5cf6  violet
#a855f7  purple
#7c3aed  deep violet
#3b82f6  saturated blue
#2563eb  default blue
blue-purple gradient
neon purple glow
```

可以在极少数情况下保留蓝色作为系统信息色，但不允许形成“蓝紫科技风”。

### 3.2 新推荐色板

#### 深色主题

```css
:root,
html[data-theme='dark'] {
  --pc-bg-canvas: #07110f;
  --pc-bg-surface: rgba(14, 24, 21, 0.94);
  --pc-bg-surface-muted: rgba(255, 255, 255, 0.035);
  --pc-bg-elevated: #101c18;
  --pc-bg-input: rgba(7, 14, 12, 0.86);

  --pc-text-primary: #f6f3ea;
  --pc-text-secondary: #d7d0c0;
  --pc-text-tertiary: #a69d8a;
  --pc-text-muted: #756d5e;

  --pc-border-subtle: rgba(214, 196, 156, 0.12);
  --pc-border-strong: rgba(217, 178, 92, 0.28);

  --pc-brand-primary: #2f9e6d;
  --pc-brand-secondary: #1f7a56;
  --pc-brand-accent: #d9a441;
  --pc-brand-soft: rgba(47, 158, 109, 0.14);
  --pc-brand-gradient: linear-gradient(135deg, #2f9e6d 0%, #d9a441 100%);

  --pc-success: #3fbf7f;
  --pc-warning: #d9a441;
  --pc-danger: #d66a5c;
  --pc-info: #6c8f7d;
}
```

#### 浅色主题

```css
html[data-theme='light'] {
  --pc-bg-canvas: #f7f3ea;
  --pc-bg-surface: rgba(255, 252, 245, 0.94);
  --pc-bg-surface-muted: #efe7d8;
  --pc-bg-elevated: #fffaf0;
  --pc-bg-input: rgba(255, 252, 245, 0.98);

  --pc-text-primary: #191713;
  --pc-text-secondary: #3f3a31;
  --pc-text-tertiary: #6f6657;
  --pc-text-muted: #8a806e;

  --pc-border-subtle: rgba(72, 62, 45, 0.12);
  --pc-border-strong: rgba(47, 111, 82, 0.28);

  --pc-brand-primary: #2f6f52;
  --pc-brand-secondary: #255b43;
  --pc-brand-accent: #b7791f;
  --pc-brand-soft: rgba(47, 111, 82, 0.12);
  --pc-brand-gradient: linear-gradient(135deg, #2f6f52 0%, #c88a2c 100%);

  --pc-success: #2f6f52;
  --pc-warning: #b7791f;
  --pc-danger: #b94a3d;
  --pc-info: #60766b;
}
```

### 3.3 语义说明

| Token | 用途 | 说明 |
|---|---|---|
| `brand-primary` | 主按钮、活动导航、关键 CTA | 采用森林绿，强调“可信、稳定、可持续” |
| `brand-accent` | 重点提示、关键指标、当前章节 | 采用琥珀金，强调“手稿、灯光、创作” |
| `success` | 通过、已确认、已写回 | 绿色，但不要过亮 |
| `warning` | 中风险、待确认、冲突提示 | 琥珀色，与小说“灯塔”意象一致 |
| `danger` | 高风险、拒绝、失败 | 柔和红棕，不使用刺眼纯红 |
| `info` | 次级信息 | 灰绿，不使用亮蓝 |

---

## 4. 布局规范

### 4.1 控制台基础结构

统一采用三段式控制台结构：

```text
左侧 Sidebar
顶部 Topbar
主内容 Main Workspace
```

页面整体应保留当前项目已有的控制台壳体体验：

- 左侧固定导航。
- 顶部显示工作空间、搜索、主题切换、通知、用户菜单。
- 主区域使用卡片网格承载工作流、资产、运行记录、检查报告。
- 桌面端优先，兼容中等宽度折叠侧栏。

### 4.2 Novel Workbench 推荐结构

小说深度样板采用：

```text
左侧：项目与故事资产导航
中间：章节 / 场景编辑与运行主区
右侧：一致性检查与记忆写回面板
底部或次级区域：相关资产、运行轨迹、版本历史
```

必须体现以下产品心智：

```text
不是普通写作编辑器，
而是可追踪、可记忆、可审查的 AI 小说创作工作台。
```

### 4.3 信息密度

商业化界面应保持中高信息密度：

- 单个页面应能同时看到项目状态、当前章节、资产、运行、风险、记忆候选。
- 不要做过度留白的营销页风格。
- 不要做只有一个输入框的 AI 聊天页。
- 卡片之间保持 16px / 20px / 24px 的一致间距。

---

## 5. 组件规范

### 5.1 卡片 Card

卡片用于承载：项目总览、Story Bible、角色卡、世界观规则、时间线、检查报告、运行记录。

建议样式：

```css
.card {
  border-radius: 24px;
  border: 1px solid var(--pc-border-subtle);
  background: var(--pc-bg-surface);
  box-shadow: 0 18px 40px rgba(8, 12, 10, 0.18);
}
```

浅色主题中卡片应接近纸张质感，避免纯白过曝。

### 5.2 主按钮

主按钮用于：继续写作、生成场景计划、确认写回、发起一致性检查。

```css
.primaryButton {
  background: var(--pc-brand-gradient);
  color: #fffaf0;
  border: none;
  border-radius: 14px;
}
```

禁止使用蓝紫渐变按钮。

### 5.3 状态徽标

状态徽标应使用透明背景 + 深色文字，不要高饱和大色块。

| 状态 | 颜色 |
|---|---|
| 已完成 / 通过 | green soft |
| 进行中 | forest soft |
| 待确认 | amber soft |
| 中风险 | amber soft |
| 高风险 | red-brown soft |
| 草稿 | neutral soft |

### 5.4 输入框与编辑器

正文编辑器是 Novel Workbench 的核心区域：

- 背景应接近暖白纸张或深色稿纸。
- 中文正文建议使用 16px - 17px 字号。
- 行高建议 1.8 - 2.0。
- 编辑区边框使用低对比度，不要抢正文注意力。
- 工具栏保持克制，不使用大面积彩色图标。

---

## 6. Novel Workbench 页面设计

### 6.1 总览页

总览页必须回答：

```text
这个小说项目现在写到哪里？
故事健康度如何？
有哪些待处理事项？
有哪些关键资产？
最近运行发生了什么？
下一步应该做什么？
```

推荐模块：

1. 项目头部：标题、类型、简介、总字数、章节数、资产数、运行次数。
2. 写作进度：整体进度、当前阶段、当前章节、当前场景、最近运行。
3. 故事健康度：人物、时间线、世界观、伏笔、文风。
4. 章节进度：章节状态、场景数、字数。
5. 关键资产概览：Story Bible、角色卡、世界规则、时间线事件、伏笔记录、场景草稿。
6. 待确认记忆更新：角色状态、关系变化、时间线事件、伏笔记录。
7. 近期活动：初始化、生成、检查、修复、写回。
8. 快速访问：核心角色、世界规则、章节大纲。

### 6.2 正文页

正文页必须回答：

```text
当前场景要写什么？
生成内容是否遵守设定？
冲突在哪里？
哪些事实需要写回长期记忆？
```

推荐模块：

1. 当前章节 / 当前场景选择器。
2. 生成模式选择器。
3. 场景计划卡片。
4. 正文编辑器。
5. 操作按钮：生成场景计划、续写、重写、扩写、压缩、分支生成、风格润色。
6. 一致性检查报告。
7. 修复建议。
8. 待确认记忆更新。
9. 相关资产速览。

### 6.3 Story Bible 页

应包含：

- 故事定位。
- 世界规则。
- 主线冲突。
- 叙事视角。
- 文风指南。
- 禁止改动设定。
- 已确认 canon 状态。

### 6.4 人物页

应包含：

- 人物卡。
- 当前状态。
- 动机。
- 弱点。
- 关系边。
- 口吻特征。
- 最近出场章节。
- 与本章相关性。

### 6.5 一致性页

应包含：

- 人物一致性。
- 时间线一致性。
- 世界观一致性。
- 伏笔状态。
- 文风一致性。
- 风险等级。
- 冲突片段。
- 相关 canon 资产。
- 最小修复建议。
- 可应用替换文本。

---

## 7. 图像生成与截图规范

后续生成 PromptChain 网页截图时，必须遵守：

```text
不要使用蓝紫配色。
不要使用 neon cyberpunk 风。
不要生成过度发光的紫色边框。
不要使用通用 AI 聊天界面。
不要使用卡通插画风。
不要让 UI 看起来像静态海报。
```

推荐描述：

```text
真实 SaaS 网页截图效果，现代商业软件界面，森林绿与琥珀金强调色，
石墨黑 / 暖白背景，克制阴影，细边框，中高信息密度，
Awwwards 级别的细节，但保持真实可实现的工程后台风格。
```

Prompt 中应包含：

```text
- desktop browser screenshot
- realistic web app UI
- PromptChain Novel Workbench
- Simplified Chinese interface
- forest green and amber accent colors
- no blue-purple palette
- no purple gradient
- no neon glow
- not a poster, not a wireframe
```

---

## 8. 代码落地建议

### 8.1 不要直接散写颜色

新增页面不要直接写：

```css
color: #3b82f6;
background: linear-gradient(135deg, #3b82f6, #8b5cf6);
```

应使用 token：

```css
color: var(--pc-semantic-brand-primary);
background: var(--pc-semantic-brand-gradient);
```

或在模块内定义场景级 token：

```css
.novelWorkbench {
  --novel-accent: var(--pc-semantic-brand-primary);
  --novel-accent-soft: var(--pc-semantic-brand-soft);
  --novel-paper: var(--pc-semantic-bg-elevated);
}
```

### 8.2 Novel Workbench 可单独扩展场景 token

小说场景可以在页面根节点定义：

```css
.novelWorkbench {
  --novel-bg-canvas: var(--pc-bg-canvas);
  --novel-bg-paper: var(--pc-bg-elevated);
  --novel-border: var(--pc-border-subtle);
  --novel-accent: var(--pc-brand-primary);
  --novel-accent-warm: var(--pc-brand-accent);
  --novel-risk-warning: var(--pc-warning);
}
```

这样可以保证小说样板既继承全局主题，又保留更强的创作场景风格。

---

## 9. 后续页面验收标准

设计稿、截图或前端页面完成后，需要满足：

- [ ] 没有蓝紫主视觉。
- [ ] 主色为森林绿 / 墨绿 / 石墨色，强调色为琥珀金。
- [ ] 页面看起来像真实商业 SaaS 产品，而不是宣传海报。
- [ ] 保留 PromptChain 当前控制台的侧栏、顶部栏、卡片化结构和主题切换逻辑。
- [ ] 支持深色和浅色主题。
- [ ] 状态色清晰但不过度刺眼。
- [ ] 小说页面能体现 Story Bible、角色卡、世界观、时间线、一致性检查、记忆写回等深度能力。
- [ ] 所有新增颜色优先通过 token 管理。
- [ ] 交互元素有 hover / focus-visible / disabled 状态。
- [ ] 页面信息密度足够支撑商业化演示。

---

## 10. 推荐一句话视觉方向

> PromptChain 不再走蓝紫 AI 科技风，而是采用“森林绿 + 琥珀金 + 石墨黑 + 暖纸白”的专业创作工作台视觉，让产品既有商业 SaaS 的可信感，也有长篇内容生产的沉浸感。
