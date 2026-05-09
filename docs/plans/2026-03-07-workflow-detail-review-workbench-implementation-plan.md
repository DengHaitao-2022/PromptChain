# Workflow Detail Review Workbench Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the workflow detail page into a review workbench with stronger clarification, approval, and completion-state interactions while keeping the existing API contract intact.

**Architecture:** Preserve the existing detail-page routing and workflow API calls, but wrap all states in a shared stage-shell layout. Focus the UI changes in the workflow detail page plus its state-specific components, using React state for local interaction modes and CSS Modules for motion and layout.

**Tech Stack:** Next.js App Router, React 19, TypeScript, CSS Modules, `lucide-react`

---

### Task 1: Capture Gemini UI/UX Guidance

**Files:**
- Modify: `docs/plans/2026-03-07-workflow-detail-review-workbench-design.md`

**Step 1: Run Gemini CLI with `/ui-ux-pro-max` in headless mode**

Run:

```bash
gemini --yolo -p $'/ui-ux-pro-max\n请基于 PromptChain 工作流详情页现状，输出澄清、审批、完成态的页面交互与动画设计建议，不改文件。'
```

Expected: Gemini returns a review-workbench-oriented design recommendation set.

**Step 2: Fold high-signal guidance into the design doc**

Keep only guidance that improves:

- 审阅台感
- 审批聚焦路径
- 完成态交付感
- 轻量动画与可访问性

### Task 2: Refactor Detail Page Shell

**Files:**
- Modify: `frontend/src/app/workflow/[id]/page.tsx`
- Modify: `frontend/src/app/workflow/[id]/page.module.css`

**Step 1: Build a shared stage shell in the page**

Introduce page-level regions for:

- status strip
- stage header
- stage body
- supporting summary area

**Step 2: Upgrade running state**

Replace the plain spinner card with:

- clearer stage title
- subcopy about current processing
- lightweight live status cue

**Step 3: Upgrade completed state**

Replace the plain JSON dump with:

- completion summary card
- readable preview surface
- raw-data tab or toggle for JSON access

### Task 3: Redesign Clarification Interaction

**Files:**
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.tsx`
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.module.css`

**Step 1: Add progress and completion summary**

Expose:

- total questions
- required questions remaining
- current completion status

**Step 2: Strengthen question-card focus behavior**

Each question card should support:

- clearer priority treatment
- `focus-within` emphasis
- stronger label hierarchy

**Step 3: Move primary action into a stronger footer/action area**

Keep the existing submission contract but improve the presentation and readiness feedback.

### Task 4: Redesign Fact Check Approval Flow

**Files:**
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.tsx`
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.module.css`

**Step 1: Introduce an internal review layout**

Split the component into:

- risk navigation list
- active claim detail panel

**Step 2: Prioritize high-risk handling**

Default focus should go to the first unresolved high-risk claim. Lower-risk claims should move into a collapsed or lower-priority section.

**Step 3: Clarify decision affordances**

Refine the decision UI so the user can immediately distinguish:

- confirm
- use suggestion
- manual correction

**Step 4: Strengthen the final submit area**

Keep the same `onApprove` behavior, but make submission feel like the close of a review pass.

### Task 5: Strengthen Workflow Rail Feedback

**Files:**
- Modify: `frontend/src/components/WorkflowProgress/WorkflowProgress.tsx`
- Modify: `frontend/src/components/WorkflowProgress/WorkflowProgress.module.css`

**Step 1: Replace text-only status markers with icon-backed indicators**

Use `lucide-react` icons where useful, avoiding emoji and ambiguous glyphs.

**Step 2: Improve current-step emphasis**

Add restrained pulse/glow feedback for the active step and clearer interrupted-state styling.

**Step 3: Make connector states more readable**

Show a stronger distinction between:

- completed chain
- active chain
- interrupted / failed chain

### Task 6: Align Outline Approval With The New Shell

**Files:**
- Modify: `frontend/src/components/OutlineEditor/OutlineEditor.tsx`
- Modify: `frontend/src/components/OutlineEditor/OutlineEditor.module.css`

**Step 1: Keep behavior stable**

Do not widen the editing scope beyond layout and presentation adjustments required by the new shell.

**Step 2: Harmonize its action area**

Bring its footer and stage framing in line with clarification and fact-check states.

### Task 7: Apply Motion and Accessibility Rules

**Files:**
- Modify: `frontend/src/app/workflow/[id]/page.module.css`
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.module.css`
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.module.css`
- Modify: `frontend/src/components/WorkflowProgress/WorkflowProgress.module.css`
- Modify: `frontend/src/components/OutlineEditor/OutlineEditor.module.css`

**Step 1: Standardize transition timing**

Use a restrained system around:

- 120-160ms hover/focus
- 180ms section switches
- 220ms stage entry
- 240ms success feedback

**Step 2: Add reduced-motion fallbacks**

Disable non-essential transform/pulse motion in `prefers-reduced-motion: reduce`.

**Step 3: Add accessibility signaling**

Ensure:

- focus states stay visible
- errors use alert semantics
- status changes can be announced

### Task 8: Verify Frontend Integrity

**Files:**
- Modify: `frontend/src/app/workflow/[id]/page.tsx`
- Modify: `frontend/src/app/workflow/[id]/page.module.css`
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.tsx`
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.module.css`
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.tsx`
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.module.css`
- Modify: `frontend/src/components/WorkflowProgress/WorkflowProgress.tsx`
- Modify: `frontend/src/components/WorkflowProgress/WorkflowProgress.module.css`
- Modify: `frontend/src/components/OutlineEditor/OutlineEditor.tsx`
- Modify: `frontend/src/components/OutlineEditor/OutlineEditor.module.css`

**Step 1: Run TypeScript validation**

Run:

```bash
cd frontend && npx tsc --noEmit
```

Expected: No type errors in touched files.

**Step 2: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: No ESLint errors in touched files.

**Step 3: Inspect the working tree**

Run:

```bash
git status --short
```

Expected: Only intended workflow-detail and docs changes are present.

### Task 9: Close Out The Work

**Files:**
- Modify: `docs/plans/2026-03-07-workflow-detail-review-workbench-design.md`
- Modify: `docs/plans/2026-03-07-workflow-detail-review-workbench-implementation-plan.md`

**Step 1: Record scope adjustments if implementation narrows or expands**

Keep the plan aligned with what shipped.

**Step 2: Prepare final summary**

Report:

- Gemini `/ui-ux-pro-max` design result
- main interaction changes
- animation changes
- verification outcomes
