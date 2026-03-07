# PromptChain Homepage Launch Experience Design

**Date:** 2026-03-07
**Scope:** `frontend/src/app/page.tsx` homepage visual redesign, startup interaction, and motion behavior

## Goal

Redesign the homepage into a technical, productized launch surface that makes PromptChain feel like a workflow system rather than a generic chat box. The page should improve first-click clarity, strengthen brand presence, and provide immediate motion feedback when a workflow is started.

## Visual Direction

- Keep the technical dark-theme foundation.
- Replace the current plain hero with a control-desk composition.
- Use a developer-tool palette:
  - background: `#0F172A`
  - surface layers: `#1E293B`, `#334155`
  - action accent: `#22C55E`
  - workflow highlight: cool cyan/blue accents
- Use a more distinctive heading voice while preserving readable body text.
- Remove emoji-as-icon usage in favor of `lucide-react` icons.

## Information Architecture

### 1. Hero Launch Surface

Use a two-column hero on desktop.

- Left column:
  - brand/navigation strip
  - technical label such as `Traceable AI Workflow`
  - stronger value proposition focused on “from request to publishable content”
  - `Launch Composer` input area for workflow kickoff
  - example prompt chips as reusable templates
  - action row with launch button and system hints

- Right column:
  - animated workflow preview card
  - visible step graph for `parse_intent -> generate_outline -> generate_content -> check_facts -> finalize`
  - small supporting cards for artifact versioning, approvals, and traceability

### 2. Capability Rail

Directly below hero, add a compact horizontal rail listing the workflow chain so users understand the pipeline at a glance.

### 3. Feature Grid

Retain the current core features, but present them as stronger product cards with clearer hierarchy, iconography, and hover feedback.

### 4. Trust / Engineering Section

Add a compact section that explains why the system is reliable:

- versioned artifacts
- human approval gates
- fact-check workflow
- rerun and trace support

## Interaction Design

### Launch Composer

- Treat the textarea as a workflow launcher, not a generic form field.
- Focus state should intensify border, glow, and surrounding context.
- Example chips should feel like templates and support one-click fill.
- CTA label should shift from “开始生成” to a stronger action such as “启动工作流”.

### Startup Feedback

After submit:

1. Button enters loading state immediately.
2. Workflow preview switches to an active orchestration state.
3. A short animated state progression runs on the preview.
4. Once the API responds with `workflow_run_id`, navigate to `/workflow/[id]`.

This creates a visible “workflow started” moment before route transition.

## Motion System

Animation is limited to key UX moments only.

### Allowed motion

- hero stagger reveal on first load
- subtle focus/hover transitions
- workflow preview node activation during launch
- restrained card lift on hover

### Motion constraints

- no decorative infinite loops except actual loading indicators
- use `transform` and `opacity` for transitions
- micro-interactions should stay within `150ms-300ms`
- respect `prefers-reduced-motion`
- reduce or remove stagger motion on small screens

## Responsive Behavior

- `>= 1024px`: two-column hero with full preview
- `768px-1023px`: preview moves below composer while staying visually rich
- `< 768px`: single-column hero, compact preview, CTA visible in first viewport

## Technical Implementation Notes

- Keep the change localized to homepage styles and supporting homepage-specific components.
- Avoid introducing a heavy animation dependency.
- Use CSS modules and React state for preview-state switching.
- Preserve the existing workflow-start API contract.

## Acceptance Criteria

- Homepage feels materially different from the current linear layout.
- Startup flow visibly communicates that a workflow is being orchestrated.
- Motion remains restrained and accessible.
- Desktop and mobile layouts both preserve strong CTA visibility.
- Existing `workflowApi.start()` flow remains intact.
