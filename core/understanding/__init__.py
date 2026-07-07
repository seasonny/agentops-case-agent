"""Understanding layer — interpret external input into structured analysis.

Sprint 2 establishes this package as the home for semantic understanding and
deterministic action inference. Policy decisions remain outside this layer.
"""

from core.understanding.action_inference import ActionInference
from core.understanding.models import VALID_ACTION_TYPES, CommentAnalysis
from core.understanding.semantic import SemanticUnderstanding
from core.understanding.service import UnderstandingService

__all__ = [
    "ActionInference",
    "CommentAnalysis",
    "SemanticUnderstanding",
    "UnderstandingService",
    "VALID_ACTION_TYPES",
]
