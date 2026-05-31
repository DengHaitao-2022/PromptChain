"""目标理解与动态计划生成。"""

from __future__ import annotations

from collections import Counter

from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
    AgentStepType,
    GoalCard,
    PlanEdge,
    PlanGraph,
    PlanNode,
    ToolRiskLevel,
)

PLANNER_PROMPT_TEMPLATE = """你是 PromptChain 的 Autonomous Agent Planner。

请根据 GoalCard、历史记忆和工具能力生成可执行 PlanGraph：
1. 每个节点必须有明确 depends_on、step_type、验收标准和风险等级。
2. 工具节点只能引用 Tool Registry 中已注册的工具。
3. 中高风险工具必须标记 Gate。
4. 计划必须覆盖 Observe / Plan / Act / Evaluate / Reflect / Replan / Finalize。
5. 输出必须是符合 PlanGraph schema 的 JSON 对象。
"""


class GoalInterpreter:
    """将开放式目标解析为 GoalCard。"""

    def interpret(self, goal: str) -> GoalCard:
        """解析目标、约束、交付物和风险边界。"""
        normalized = goal.strip()
        if not normalized:
            raise ValueError("目标不能为空")

        task_type = self._detect_task_type(normalized)
        deliverables = self._detect_deliverables(normalized, task_type)
        constraints = self._detect_constraints(normalized)
        risk_boundaries = self._detect_risks(normalized)

        return GoalCard(
            goal=normalized,
            task_type=task_type,
            constraints=constraints,
            deliverables=deliverables,
            risk_boundaries=risk_boundaries,
            success_criteria=[
                "计划图结构完整且每个步骤具备明确验收标准",
                "执行结果覆盖目标中的关键主题和交付物",
                "工具调用、评估、重规划和产物均可审计追踪",
            ],
            quality_dimensions=[
                "目标覆盖度",
                "计划可执行性",
                "事实一致性",
                "产物完整性",
                "风险可控性",
            ],
            uncertainty_questions=self._detect_uncertainties(normalized),
        )

    def _detect_task_type(self, goal: str) -> str:
        text = goal.lower()
        if any(keyword in text for keyword in ("调研", "research", "路线", "报告")):
            return "research_report"
        if any(keyword in text for keyword in ("论文", "thesis", "答辩")):
            return "academic_writing"
        if any(keyword in text for keyword in ("ppt", "演示", "presentation")):
            return "presentation"
        if any(keyword in text for keyword in ("脚本", "视频", "script")):
            return "script_writing"
        return "complex_content_goal"

    def _detect_deliverables(self, goal: str, task_type: str) -> list[str]:
        deliverables: list[str] = []
        if "报告" in goal:
            deliverables.append("调研报告")
        if "提纲" in goal:
            deliverables.append("结构化提纲")
        if "材料" in goal:
            deliverables.append("可复用材料")
        if "ppt" in goal.lower():
            deliverables.append("PPT 页结构与逐页文案")
        if not deliverables:
            fallback = {
                "research_report": "结构化调研报告",
                "academic_writing": "论文/答辩材料",
                "presentation": "演示文稿内容",
                "script_writing": "脚本文案",
            }.get(task_type, "最终内容产物")
            deliverables.append(fallback)
        return deliverables

    def _detect_constraints(self, goal: str) -> list[str]:
        constraints = []
        if "当前项目" in goal:
            constraints.append("优先复用当前项目已有 Artifact、Trace 与工作流上下文")
        if "后续" in goal:
            constraints.append("输出需支持后续继续扩展和复用")
        if "完整" in goal:
            constraints.append("不得只生成最小 Demo，需覆盖完整执行闭环")
        if not constraints:
            constraints.append("保持步骤可审计、可回放、可人工接管")
        return constraints

    def _detect_risks(self, goal: str) -> list[str]:
        risks = ["高风险工具调用必须进入 Gate 审批"]
        if any(keyword in goal for keyword in ("发布", "删除", "发送", "外部")):
            risks.append("涉及外部副作用或破坏性操作时禁止自动执行")
        return risks

    def _detect_uncertainties(self, goal: str) -> list[str]:
        tokens = [token for token in goal.replace("，", " ").replace("。", " ").split() if token]
        repeated = [token for token, count in Counter(tokens).items() if count > 2]
        questions = []
        if len(goal) < 20:
            questions.append("目标描述较短，是否需要补充受众、交付格式和质量标准？")
        if repeated:
            questions.append(f"目标中重复强调 {', '.join(repeated[:3])}，是否代表硬性优先级？")
        return questions


class AutonomousPlanner:
    """生成和调整动态 Plan Graph。"""

    def __init__(self, interpreter: GoalInterpreter | None = None):
        self.interpreter = interpreter or GoalInterpreter()

    def create_initial_plan(
        self, run: AgentRun, memory_hits: list[dict] | None = None
    ) -> AgentPlan:
        """生成初始计划。"""
        goal_card = self.interpreter.interpret(run.goal)
        candidates = self._build_candidate_plan_graphs(goal_card, memory_hits or [])
        selected = max(candidates, key=lambda item: item["score"])
        return AgentPlan(
            run_id=run.id,
            version=1,
            status=AgentPlanStatus.ACTIVE,
            goal_card=goal_card,
            plan_graph=selected["plan_graph"],
            created_by="planner",
            reason="initial_goal_plan",
            metadata={
                "memory_hit_count": len(memory_hits or []),
                "planner_prompt_version": "autonomous-agent-planner-v1",
                "planner_prompt": PLANNER_PROMPT_TEMPLATE,
                "selected_template": selected["template_id"],
                "plan_candidates": [
                    {
                        "template_id": item["template_id"],
                        "score": item["score"],
                        "reason": item["reason"],
                    }
                    for item in candidates
                ],
            },
        )

    def create_replan(
        self,
        *,
        run: AgentRun,
        previous_plan: AgentPlan,
        failed_node_id: str,
        reflection: dict,
        next_version: int,
    ) -> AgentPlan:
        """基于失败反思创建局部重规划计划。"""
        nodes = [node.model_copy(deep=True) for node in previous_plan.plan_graph.nodes]
        edges = [edge.model_copy(deep=True) for edge in previous_plan.plan_graph.edges]
        repair_node_id = f"repair_{next_version}_{failed_node_id}"
        evaluate_node_id = f"evaluate_repair_{next_version}_{failed_node_id}"

        # 将失败节点的直接下游改为等待修复复评，避免新计划绕过修复步骤继续执行。
        for node in nodes:
            if failed_node_id in node.depends_on:
                node.depends_on = [
                    evaluate_node_id if dependency == failed_node_id else dependency
                    for dependency in node.depends_on
                ]
        edges = [
            edge
            for edge in edges
            if not (edge.source == failed_node_id and edge.target != repair_node_id)
        ]

        nodes.append(
            PlanNode(
                id=repair_node_id,
                title="补充修复步骤",
                step_type=AgentStepType.TOOL_CALL,
                description=reflection.get("repair_action")
                or "根据失败原因补充资料、修正输出并保留证据。",
                depends_on=[failed_node_id],
                tool_name="write_artifact",
                expected_output="修复后的中间产物",
                acceptance_criteria=["修复产物明确回应失败原因", "修复内容可被后续评估引用"],
                risk_level=ToolRiskLevel.LOW,
            )
        )
        nodes.append(
            PlanNode(
                id=evaluate_node_id,
                title="复评修复结果",
                step_type=AgentStepType.EVALUATION,
                description="重新评估修复后的结果是否满足目标约束。",
                depends_on=[repair_node_id],
                expected_output="复评结果",
                acceptance_criteria=["复评分数达到阈值", "无未关闭的高风险问题"],
            )
        )
        edges.extend(
            [
                PlanEdge(source=failed_node_id, target=repair_node_id),
                PlanEdge(source=repair_node_id, target=evaluate_node_id),
                *[
                    PlanEdge(source=evaluate_node_id, target=node.id)
                    for node in nodes
                    if evaluate_node_id in node.depends_on
                ],
            ]
        )

        return AgentPlan(
            run_id=run.id,
            version=next_version,
            status=AgentPlanStatus.ACTIVE,
            goal_card=previous_plan.goal_card,
            plan_graph=PlanGraph(
                nodes=nodes,
                edges=edges,
                quality_gates=previous_plan.plan_graph.quality_gates,
                max_steps=previous_plan.plan_graph.max_steps,
                max_replans=previous_plan.plan_graph.max_replans,
            ),
            created_by="replanner",
            reason=reflection.get("summary") or "step_quality_replan",
            metadata={"failed_node_id": failed_node_id, "reflection": reflection},
        )

    def _build_candidate_plan_graphs(
        self, goal_card: GoalCard, memory_hits: list[dict]
    ) -> list[dict]:
        """生成多候选计划并评分，供 Planner 选择最合适的执行图。"""
        template_ids = [
            "research_report_full_loop",
            "content_production_full_loop",
            "risk_first_full_loop",
        ]
        candidates = []
        for template_id in template_ids:
            graph = self._build_plan_graph(goal_card, memory_hits, template_id=template_id)
            score = self._score_candidate(goal_card, graph, template_id, memory_hits)
            candidates.append(
                {
                    "template_id": template_id,
                    "score": score,
                    "reason": self._candidate_reason(goal_card, template_id, score),
                    "plan_graph": graph,
                }
            )
        return candidates

    def _score_candidate(
        self,
        goal_card: GoalCard,
        plan_graph: PlanGraph,
        template_id: str,
        memory_hits: list[dict],
    ) -> float:
        """按任务类型、质量门控和历史记忆复用度给候选计划评分。"""
        score = 0.62
        if goal_card.task_type == "research_report" and template_id == "research_report_full_loop":
            score += 0.18
        if (
            goal_card.task_type != "research_report"
            and template_id == "content_production_full_loop"
        ):
            score += 0.12
        if goal_card.risk_boundaries and template_id == "risk_first_full_loop":
            score += 0.1
        if memory_hits:
            score += min(0.08, len(memory_hits) * 0.02)
        if any(node.tool_name == "fact_check" for node in plan_graph.nodes):
            score += 0.04
        if plan_graph.quality_gates:
            score += 0.04
        return round(min(score, 0.98), 3)

    def _candidate_reason(self, goal_card: GoalCard, template_id: str, score: float) -> str:
        """生成前端可展示的候选计划评分原因。"""
        if template_id == "research_report_full_loop":
            return f"匹配 {goal_card.task_type}，强调证据收集、事实核查和最终报告，评分 {score}"
        if template_id == "risk_first_full_loop":
            return f"优先处理风险边界和 Gate 审批，评分 {score}"
        return f"通用内容生产闭环，覆盖规划、生成、评估和收口，评分 {score}"

    def _build_plan_graph(
        self,
        goal_card: GoalCard,
        memory_hits: list[dict],
        *,
        template_id: str,
    ) -> PlanGraph:
        """构建完整的 Plan-Act-Observe-Evaluate-Reflect-Replan 图。"""
        nodes = [
            PlanNode(
                id="goal_interpretation",
                title="目标理解",
                step_type=AgentStepType.GOAL_INTERPRETATION,
                description="解析目标、约束、交付物、质量维度与风险边界。",
                expected_output="GoalCard",
                acceptance_criteria=["目标卡字段完整", "风险边界明确"],
            ),
            PlanNode(
                id="retrieve_memory",
                title="检索历史记忆与证据",
                step_type=AgentStepType.MEMORY_RETRIEVAL,
                description="检索当前工作空间历史经验、Artifact 和 Trace 线索。",
                depends_on=["goal_interpretation"],
                tool_name="retrieve_memory",
                input={"query": goal_card.goal, "preloaded_hits": memory_hits},
                expected_output="可引用的历史经验和证据列表",
                acceptance_criteria=["检索结果标明来源", "没有命中时给出空结果和原因"],
            ),
            PlanNode(
                id="draft_plan",
                title="生成执行计划",
                step_type=AgentStepType.PLANNING,
                description="生成动态任务图、依赖关系和每步验收标准。",
                depends_on=["retrieve_memory"],
                expected_output="PlanGraph",
                acceptance_criteria=["节点依赖无环", "每个节点有验收标准"],
            ),
            PlanNode(
                id="collect_evidence",
                title="收集证据",
                step_type=AgentStepType.TOOL_CALL,
                description=self._evidence_description(template_id),
                depends_on=["draft_plan"],
                tool_name="read_artifact",
                input={"goal": goal_card.goal, "template_id": template_id},
                expected_output="证据摘要",
                acceptance_criteria=["证据与目标相关", "输出包含来源"],
            ),
            PlanNode(
                id="generate_content",
                title="生成主体产物",
                step_type=AgentStepType.GENERATION,
                description="基于目标、计划和证据生成完整内容草案。",
                depends_on=["collect_evidence"],
                tool_name="write_artifact",
                expected_output=", ".join(goal_card.deliverables),
                acceptance_criteria=goal_card.success_criteria,
            ),
            PlanNode(
                id="fact_check_content",
                title="核查事实风险",
                step_type=AgentStepType.TOOL_CALL,
                description="对主体产物进行事实风险和绝对化表述核查。",
                depends_on=["generate_content"],
                tool_name="fact_check",
                expected_output="事实风险核查结果",
                acceptance_criteria=[
                    "核查结果包含风险项和修正建议",
                    "无高风险事实问题时才能进入综合评估",
                ],
            ),
            PlanNode(
                id="evaluate_output",
                title="评估产物质量",
                step_type=AgentStepType.EVALUATION,
                description="评估目标覆盖度、完整性、事实风险和可交付性。",
                depends_on=["fact_check_content"],
                expected_output="EvalResult",
                acceptance_criteria=["评分达到阈值", "问题列表具备修复建议"],
            ),
            PlanNode(
                id="reflect_or_finalize",
                title="反思或收口",
                step_type=AgentStepType.REFLECTION,
                description="低分或失败时归因并触发重规划；通过时进入最终交付。",
                depends_on=["evaluate_output"],
                expected_output="反思结论或完成判断",
                acceptance_criteria=["失败原因可行动", "通过时明确完成证据"],
            ),
            PlanNode(
                id="finalize",
                title="生成最终交付物",
                step_type=AgentStepType.FINALIZATION,
                description="保存最终 Artifact、执行摘要、质量指标和可回放索引。",
                depends_on=["reflect_or_finalize"],
                tool_name="write_artifact",
                expected_output="最终 Artifact",
                acceptance_criteria=["最终产物已版本化保存", "Trace 能关联所有关键记录"],
            ),
        ]
        edges = [
            PlanEdge(source=node.depends_on[0], target=node.id)
            for node in nodes
            if len(node.depends_on) == 1
        ]
        return PlanGraph(
            nodes=nodes,
            edges=edges,
            quality_gates=[
                {
                    "id": "risk_gate",
                    "condition": "risk_level >= medium",
                    "action": "require_human_approval",
                },
                {
                    "id": "quality_gate",
                    "condition": "evaluation_score < 0.72",
                    "action": "reflect_and_replan",
                },
            ],
            max_steps=14,
            max_replans=2,
        )

    def _evidence_description(self, template_id: str) -> str:
        if template_id == "research_report_full_loop":
            return "优先从历史产物、Trace、项目上下文和记忆中收集调研证据。"
        if template_id == "risk_first_full_loop":
            return "优先收集风险边界、权限要求和高影响操作的证据。"
        return "从历史产物、项目上下文或知识库中收集执行依据。"
