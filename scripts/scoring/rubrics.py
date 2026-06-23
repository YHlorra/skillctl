"""
8-Dimension Rubric Definitions

Defines the scoring rubric for skill evaluation.
"""

from dataclasses import dataclass
from typing import Dict, Any

# 8-Dimension Rubric (100pt total)
DIMENSIONS: Dict[str, Dict[str, Any]] = {
    "frontmatter": {
        "max": 8,
        "weight": 0.08,
        "description": "name, description, triggers completeness"
    },
    "workflow": {
        "max": 15,
        "weight": 0.15,
        "description": "Step-by-step clarity, logical flow"
    },
    "edge_cases": {
        "max": 10,
        "weight": 0.10,
        "description": "Error handling, boundary conditions"
    },
    "checkpoints": {
        "max": 7,
        "weight": 0.07,
        "description": "Verification steps, quality gates"
    },
    "specificity": {
        "max": 15,
        "weight": 0.15,
        "description": "Action-level instructions vs vague"
    },
    "resources": {
        "max": 5,
        "weight": 0.05,
        "description": "Dependencies, external refs"
    },
    "architecture": {
        "max": 15,
        "weight": 0.15,
        "description": "Code structure, modularity"
    },
    "live_test": {
        "max": 25,
        "weight": 0.25,
        "description": "Real sub-agent execution + output quality"
    },
}


@dataclass
class Dimension:
    """Represents a single scoring dimension."""
    name: str
    max_score: int
    weight: float
    description: str


class Rubric:
    """Complete 8-dimension rubric for skill evaluation."""

    def __init__(self):
        self.dimensions = [
            Dimension(
                name=name,
                max_score=data["max"],
                weight=data["weight"],
                description=data["description"]
            )
            for name, data in DIMENSIONS.items()
        ]

    def get_dimension(self, name: str) -> Dimension:
        """Get dimension by name."""
        for dim in self.dimensions:
            if dim.name == name:
                return dim
        raise ValueError(f"Unknown dimension: {name}")

    def total_max(self) -> int:
        """Get total maximum score."""
        return sum(d.max_score for d in self.dimensions)
