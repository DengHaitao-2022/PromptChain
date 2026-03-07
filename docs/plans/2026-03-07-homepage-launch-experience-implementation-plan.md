# Homepage Launch Experience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the homepage into a technical launch surface with clearer product positioning, richer startup feedback, and restrained workflow-themed motion.

**Architecture:** Keep the behavior anchored in the existing `workflowApi.start()` flow, but split homepage UI into a stronger hero composition plus a dedicated workflow preview component. Use React state to drive launch states and CSS modules for motion and responsive layout so the change stays localized to the homepage.

**Tech Stack:** Next.js App Router, React 19, TypeScript, CSS Modules, `lucide-react`

---

### Task 1: Capture Gemini SDD Guidance

**Files:**
- Modify: `docs/plans/2026-03-07-homepage-launch-experience-design.md`

**Step 1: Run Gemini CLI in headless mode with SDD instructions**

Run:

```bash
gemini -p $'/ui-ux-pro-max\n你是 PromptChain 首页改造协作者。按 Spec-Driven Development 执行：先阅读 docs/plans/2026-03-07-homepage-launch-experience-design.md，再给出首页 Hero、启动交互、动画节点、视觉层级的实现建议。要求保留技术感、优化全新视觉、避免过度动效、兼顾移动端与 prefers-reduced-motion。输出高信号建议，不改文件。'
```

Expected: Gemini returns a concrete homepage implementation recommendation set using `/ui-ux-pro-max`.

**Step 2: Fold any high-signal Gemini output back into implementation decisions**

Use only the parts that improve hierarchy, motion restraint, and launch feedback. Do not widen scope beyond homepage.

### Task 2: Refactor Homepage Structure

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/page.module.css`
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.tsx`
- Create: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.module.css`

**Step 1: Add the homepage-specific preview component**

Implement a component that supports at least:

- idle state
- launching state
- compact mobile rendering

**Step 2: Rebuild the homepage hero around a two-column launch surface**

Move the page away from the current title-plus-textarea stack and introduce:

- technical eyebrow
- stronger headline and supporting copy
- `Launch Composer`
- workflow preview panel
- compact capability rail

**Step 3: Replace emoji icons with `lucide-react`**

Keep the features data-driven but switch to imported SVG icons for better visual quality and accessibility.

**Step 4: Update typography imports if needed**

Add any required Google Font import in `frontend/src/app/layout.tsx` only if the new heading treatment needs it. Avoid changing the entire app’s visual system more than necessary.

### Task 3: Wire Startup Interaction and Motion States

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.tsx`
- Modify: `frontend/src/app/page.module.css`
- Modify: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.module.css`

**Step 1: Introduce local homepage launch states**

Track enough UI state to distinguish:

- default idle
- launching
- launch success just before route transition
- error recovery

**Step 2: Keep API behavior intact while improving perceived feedback**

On submit:

- start loading immediately
- switch preview into active orchestration mode
- wait long enough for the transition to register visually
- navigate once `workflow_run_id` is available

**Step 3: Implement restrained CSS motion**

Add:

- hero reveal
- chip/button hover states
- preview node activation
- reduced-motion fallbacks

Avoid long-running decorative animations.

### Task 4: Upgrade Supporting Sections

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/page.module.css`

**Step 1: Redesign the capability rail**

Represent the workflow pipeline clearly in a compact section beneath hero.

**Step 2: Rework feature cards**

Improve visual hierarchy, supporting text density, and hover response while keeping the original product ideas.

**Step 3: Add a compact engineering-trust section**

Highlight:

- approval gates
- fact checks
- versioned artifacts
- trace visibility

### Task 5: Verify Without Expanding Test Infra

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/page.module.css`
- Modify: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.tsx`
- Modify: `frontend/src/components/HomeWorkflowPreview/HomeWorkflowPreview.module.css`
- Modify: `frontend/src/app/layout.tsx`

**Step 1: Run TypeScript validation**

Run:

```bash
cd frontend && npx tsc --noEmit
```

Expected: No type errors.

**Step 2: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: No ESLint errors in touched files.

**Step 3: Inspect working tree**

Run:

```bash
git status --short
```

Expected: Only intended homepage/design-plan changes are present.

### Task 6: Summarize Outcome

**Files:**
- Modify: `docs/plans/2026-03-07-homepage-launch-experience-design.md`
- Modify: `docs/plans/2026-03-07-homepage-launch-experience-implementation-plan.md`

**Step 1: Record final implementation notes if scope changed**

Keep design and implementation plan aligned with any scoped adjustments made during development.

**Step 2: Prepare close-out summary**

Report:

- Gemini `/ui-ux-pro-max` usage result
- homepage interaction changes
- animation changes
- verification command results
