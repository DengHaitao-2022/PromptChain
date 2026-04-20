"""
意图卡数据模型

IntentCard: 结构化意图卡，约束内容生成的边界
Uncertainty: 不确定点，需要用户澄清
"""

from enum import Enum

from pydantic import BaseModel, Field


class Audience(str, Enum):
    """目标受众"""

    BEGINNER = "初学者"
    INTERMEDIATE = "中级读者"
    EXPERT = "专家"
    GENERAL = "通用读者"


class Tone(str, Enum):
    """语气风格"""

    FORMAL = "正式严谨"
    CASUAL = "轻松活泼"
    ACADEMIC = "学术专业"
    STORYTELLING = "叙事性"


class Uncertainty(BaseModel):
    """不确定点，需要用户澄清"""

    field: str = Field(..., description="涉及字段")
    question: str = Field(..., description="澄清问题")
    priority: int = Field(..., ge=1, le=5, description="优先级1-5，越小越重要")
    default_assumption: str | None = Field(None, description="系统默认假设")


class IntentCard(BaseModel):
    """
    结构化意图卡，约束内容生成的边界

    对应 MIGAI 框架中的 Constrain 动作
    """

    # 核心意图
    goal: str = Field(..., description="生成目标：用户想要完成什么")
    topic: str = Field(..., description="主题：文章/脚本的核心主题")

    # 受众与场景
    audience: Audience = Field(default=Audience.GENERAL, description="目标受众")
    scenario: str | None = Field(None, description="使用场景：如公众号、演讲稿、报告")

    # 风格约束
    tone: Tone = Field(default=Tone.CASUAL, description="语气风格")
    length: int = Field(default=1500, ge=100, le=10000, description="目标字数")

    # 内容约束
    must_include: list[str] = Field(default_factory=list, description="必须包含的元素/案例")
    must_exclude: list[str] = Field(default_factory=list, description="禁用项/敏感话题")

    # 素材来源
    source_references: list[str] = Field(default_factory=list, description="参考资料URL或文档")

    # 不确定点（系统识别）
    uncertainties: list[Uncertainty] = Field(default_factory=list, description="系统识别的不确定点")

    def get_high_priority_uncertainties(self, max_count: int = 3) -> list[Uncertainty]:
        """获取高优先级的不确定点（优先级<=2），最多返回max_count个"""
        return sorted([u for u in self.uncertainties if u.priority <= 2], key=lambda x: x.priority)[
            :max_count
        ]

    def has_uncertainties(self) -> bool:
        """是否有需要澄清的不确定点"""
        return len(self.get_high_priority_uncertainties()) > 0
