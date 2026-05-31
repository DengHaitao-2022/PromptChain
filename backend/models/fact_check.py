"""
事实核查数据模型

FactClaim: 事实性声明
VerificationResult: 验证结果
FactCheckReport: 事实核查报告
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

EvidenceStatus = Literal["supported", "unsupported", "conflicting", "not_checked"]


class FactClaim(BaseModel):
    """事实性声明"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = Field(..., description="原始声明文本")
    section_id: str = Field(..., description="所属章节ID")
    category: Literal["number", "date", "statistic", "quote", "policy", "other"] = Field(
        default="other", description="声明类型"
    )
    # 原始位置（用于高亮）
    start_pos: int | None = Field(None, description="在原文中的起始位置")
    end_pos: int | None = Field(None, description="在原文中的结束位置")


class VerificationResult(BaseModel):
    """验证结果"""

    claim_id: str
    is_verified: bool = Field(..., description="是否已验证")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    evidence_status: EvidenceStatus = Field(
        default="not_checked",
        description="基于 Evidence Artifact 的证据状态",
    )
    source: str | None = Field(None, description="验证来源")
    suggested_correction: str | None = Field(None, description="建议修正")
    risk_level: Literal["low", "medium", "high"] = Field(default="low", description="风险等级")
    verification_question: str | None = Field(None, description="验证问题")
    verification_answer: str | None = Field(None, description="验证答案")


class FactCheckReport(BaseModel):
    """事实核查报告"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claims: list[FactClaim] = Field(default_factory=list, description="提取的事实声明")
    results: list[VerificationResult] = Field(default_factory=list, description="验证结果")
    high_risk_items: list[str] = Field(default_factory=list, description="需人工确认的高风险项ID")
    high_risk_count: int = Field(default=0)

    # 统计
    total_claims: int = Field(default=0)
    verified_count: int = Field(default=0)
    unverified_count: int = Field(default=0)

    def compute_stats(self):
        """计算统计数据"""
        self.total_claims = len(self.claims)
        self.verified_count = sum(1 for r in self.results if r.is_verified)
        self.unverified_count = self.total_claims - self.verified_count
        self.high_risk_items = [
            r.claim_id for r in self.results if r.risk_level == "high" or not r.is_verified
        ]
        self.high_risk_count = len(self.high_risk_items)

    def has_high_risk_items(self) -> bool:
        """是否有高风险项"""
        return len(self.high_risk_items) > 0
