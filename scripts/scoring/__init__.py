"""
Scoring Module - 8-Dimension Skill Evaluation

Standalone scoring engine decoupled from scan_and_index.py.
"""

__version__ = "1.0.0"

from .rubrics import DIMENSIONS, Dimension, Rubric
from .scoring import score_skill, score_cluster
from .reporters import to_json, to_markdown_table, save_score

__all__ = [
    "DIMENSIONS",
    "Dimension",
    "Rubric",
    "score_skill",
    "score_cluster",
    "to_json",
    "to_markdown_table",
    "save_score",
]
