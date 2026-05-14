---
name: aigc-thesis-rewriter
description: chinese thesis and technical-document aigc risk analysis and rewriting workflow. use when the user asks to 降重, 去ai味, 降aigc率, rewrite high/medium/low aigc fragments, analyze ai-detection reports, create逐段替换方案, or apply a humanized academic rewrite to chinese undergraduate theses, capstone papers, abstracts, literature reviews, system design sections, or docx/pdf detection-report workflows while preserving technical facts, citations, terms, and comparable length.
---

# AIGC Thesis Rewriter

## Core purpose

Help rewrite Chinese thesis or technical-document text that has been marked as suspected AIGC. Treat the detector result as a risk signal, not as truth. Preserve the original facts, technical terms, citations, table/figure references, interfaces, code identifiers, and thesis logic while changing the expression pattern that caused the risk.

## Non-negotiable rules

- Do not claim that a rewrite will pass a detector. Say only that it is optimized against observed risk patterns.
- Keep the rewritten length close to the original unless the user explicitly asks for expansion or compression.
- Do not add implementation claims that are not supported by the user’s thesis, code, screenshots, tables, or provided materials.
- Preserve technical identifiers exactly, including names such as `Prompt Chain`, `LangGraph`, `GraphState`, `Artifact`, `WorkflowRun`, `NodeRun`, `FastAPI`, `Next.js`, `PostgreSQL`, `Redis`, `RBAC`, `JSON Schema`, paths such as `/api/me`, and citation numbers such as `[4-5,27]`.
- Do not make the text overly colloquial. Avoid forms such as “至于 xxx 呢” or “xxx 呢”.
- Avoid first-person expressions unless the original thesis style requires them. Prefer “本文”“系统”“该模块”.
- Do not simply replace synonyms. Reduce risk by changing paragraph rhythm, adding concrete project evidence, and reducing template-like evaluation.

## Intake workflow

1. **Identify the material type**
   - Detection report only: extract risky fragments and produce a replacement plan.
   - Original thesis/docx plus report: align risky fragments to the source, then produce or apply replacements.
   - Pasted paragraph only: rewrite it directly using the style rules.

2. **Extract risk fragments**
   - If the report is a PDF, use the available PDF/file tools, or run `scripts/extract_aigc_fragments.py` to create a structured list.
   - Capture fragment id, risk label, probability if available, and the exact text.
   - If the report uses only labels such as 高/中/低, keep those labels and do not invent exact probabilities.

3. **Diagnose before rewriting**
   - Load `references/risk-patterns.md` when analyzing why text was marked high, medium, or low.
   - Name the main trigger in 1 short sentence: template summary, abstract evaluation, list-heavy structure, literature-review smoothing, textbook definition, conclusion-like closure, or low project fact density.

4. **Rewrite by risk tier**
   - High risk: restructure the paragraph. Replace generic claims with concrete project actions, states, fields, tables, interfaces, or node behavior. Reduce “提高/增强/提供基础/形成闭环” unless supported by a concrete mechanism.
   - Medium risk: keep the core structure but vary sentence order, replace formulaic transitions, and bind claims to specific system objects.
   - Low risk: make only necessary local edits. Do not over-rewrite detailed implementation text.

5. **Self-check**
   - Verify that terms, citations, numbers, paths, class names, interface names, and database/table names are unchanged.
   - Compare approximate length with the original. If the rewrite is much longer, compress it.
   - Check that no unsupported project facts were introduced.

## Style transformation rules

Load `references/rewrite-style-rules.md` when the user asks to use a particular降重风格, especially the style that is slightly explanatory, professional, and not overly colloquial.

General defaults:

- Convert generic evaluation into mechanism-based description.
- Prefer project-specific verbs: “写入”, “保存”, “校验”, “恢复”, “返回”, “触发”, “关联”, “展示”.
- Reduce repeated sentence starters such as “随着”, “从……来看”, “综合来看”, “由此可见”.
- Break long symmetrical lists into one or two concrete process sentences.
- Keep citations attached to the same claims unless there is a clear reason to move them.

## Output modes

### Dialogue mode
Use for “继续”“逐个运行”“先改这一段”. Output one or two fragments at a time:

```markdown
## 第 n 段：风险等级
**问题判断**：...

**修改后**
...

**替换建议**：...
```

### Complete replacement plan
Use when the user asks for a complete plan or all fragments. Use this structure:

```markdown
# AIGC 降重逐段替换方案

## 总体判断
[brief summary of report pattern and rewrite strategy]

## 片段 n（风险：高/中/低，概率：x% if available）
**原文定位**：...
**触发原因**：...
**修改后**：
...
**替换说明**：...
```

### Direct rewrite mode
When the user provides only “原文”, output only:

```markdown
修改后：
...
```

unless they ask for explanation.

### File-update mode
When the user asks to write replacements back into a `.docx`, use the document-editing skill or appropriate document tools. Always create a backup before modifying the document, preserve formatting as much as possible, and report any replacements that could not be aligned safely.

## Bundled resources

- `references/risk-patterns.md`: detector-risk patterns and high/medium/low interpretation.
- `references/rewrite-style-rules.md`: Chinese academic rewrite rules, phrase preferences, bracket handling, and length control.
- `references/output-templates.md`: reusable templates for reports and replacement plans.
- `scripts/extract_aigc_fragments.py`: optional helper for extracting structured fragments from AIGC report PDFs or text files.
- `scripts/make_rewrite_skeleton.py`: optional helper for converting extracted fragments into a markdown replacement-plan skeleton.
