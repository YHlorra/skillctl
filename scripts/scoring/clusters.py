"""
Cluster Definitions

Defines the 8 skill clusters for evaluation.
"""

# 8 Clusters definition
CLUSTERS = {
    "document": ["docx", "pdf", "minimax-docx", "minimax-pdf", "lark-doc", "feishu-doc-reader"],
    "frontend-ui": ["frontend-design", "design", "ui-ux-pro-max", "web-artifacts-builder", "canvas-design"],
    "writing": ["write", "ljg-writes", "internal-comms", "doc-coauthoring"],
    "image": ["baoyu-image-gen", "gemini-image", "algorithmic-art", "brand-guidelines"],
    "spreadsheet": ["minimax-xlsx", "xlsx", "data-analysis"],
    "knowledge": ["learn", "ljg-learn", "ljg-paper", "ljg-paper-flow", "obsidian-markdown", "obsidian-bases"],
    "seo-growth": ["money-seo", "baoyu-infographic"],
    "video": ["remotion-video", "ffmpeg-usage", "baoyu-slide-deck"],
}

ALL_CLUSTERS = list(CLUSTERS.keys())


def get_cluster_skills(cluster_name: str) -> list:
    """Get list of skills in a cluster."""
    return CLUSTERS.get(cluster_name, [])


def get_all_skills() -> list:
    """Get all skills across all clusters."""
    skills = []
    for cluster_skills in CLUSTERS.values():
        skills.extend(cluster_skills)
    return skills
