"""小说工作台领域契约。"""

from models.scenario import ProjectAssetLifecycleStatus as NovelAssetLifecycleStatus

from .taxonomy import (
    NOVEL_ASSET_TYPES,
    NOVEL_CORE_CANON_TYPES,
    NOVEL_MEMORY_CANDIDATE_TYPES,
    NOVEL_REQUIRED_GENERATION_MODES,
)

__all__ = [
    "NOVEL_ASSET_TYPES",
    "NOVEL_CORE_CANON_TYPES",
    "NOVEL_MEMORY_CANDIDATE_TYPES",
    "NOVEL_REQUIRED_GENERATION_MODES",
    "NovelAssetLifecycleStatus",
]
