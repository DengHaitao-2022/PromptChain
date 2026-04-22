"""
提纲数据模型

Outline: 完整提纲
OutlineSection: 提纲章节
"""

import uuid

from pydantic import BaseModel, Field


class OutlineSection(BaseModel):
    """提纲章节"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一标识符")
    title: str = Field(..., description="章节标题")
    summary: str = Field(..., description="章节摘要/要点")
    target_words: int = Field(..., description="目标字数")
    subsections: list[OutlineSection] = Field(default_factory=list, description="子章节")

    # 用于回溯
    dependencies: list[str] = Field(default_factory=list, description="依赖的前序章节ID")

    # 生成状态
    is_generated: bool = Field(default=False, description="是否已生成内容")
    generated_content: str | None = Field(None, description="已生成的内容")


class Outline(BaseModel):
    """完整提纲"""

    title: str = Field(..., description="文章标题")
    abstract: str = Field(..., description="概述/导语")
    sections: list[OutlineSection] = Field(..., description="章节列表")
    total_target_words: int = Field(..., description="总目标字数")

    # 元数据
    version: int = Field(default=1, description="版本号，用于追踪修改")
    is_approved: bool = Field(default=False, description="用户是否已确认")

    def get_section_count(self) -> int:
        """获取总章节数（包括子章节）"""
        count = 0

        def _count(sections: list[OutlineSection]):
            nonlocal count
            for s in sections:
                count += 1
                _count(s.subsections)

        _count(self.sections)
        return count

    def get_flat_sections(self) -> list[OutlineSection]:
        """获取扁平化的章节列表（按顺序）"""
        result = []

        def _flatten(sections: list[OutlineSection]):
            for s in sections:
                result.append(s)
                _flatten(s.subsections)

        _flatten(self.sections)
        return result
