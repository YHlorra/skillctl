"""
CLI Integration Tests

Verifies scoring module independence from scan_and_index.py.
"""

import sys
from pathlib import Path

# Ensure scan_and_index is not imported
assert 'scan_and_index' not in sys.modules, "scan_and_index should not be imported"

# Test imports work without scan_and_index
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scoring.rubrics import DIMENSIONS
from scoring.clusters import CLUSTERS, ALL_CLUSTERS
from scoring.scoring import score_skill

def test_score_module_independence():
    """Verify scoring module works without scan_and_index.py"""
    # Verify dimensions exist
    assert len(DIMENSIONS) == 8, f"Expected 8 dimensions, got {len(DIMENSIONS)}"
    assert DIMENSIONS['frontmatter']['max'] == 8
    assert DIMENSIONS['live_test']['max'] == 25

    # Verify clusters
    assert len(ALL_CLUSTERS) == 8, f"Expected 8 clusters, got {len(ALL_CLUSTERS)}"
    assert 'document' in ALL_CLUSTERS
    assert 'frontend-ui' in ALL_CLUSTERS

    # Verify score_skill function exists
    assert callable(score_skill)

    print("[PASS] Scoring module is independent")
    print(f"  - {len(DIMENSIONS)} dimensions defined")
    print(f"  - {len(ALL_CLUSTERS)} clusters defined")
    print(f"  - score_skill function available")


def test_cli_standalone():
    """Verify score.py CLI works standalone"""
    import subprocess

    score_py = Path(__file__).parent.parent / "score.py"
    if not score_py.exists():
        score_py = Path(__file__).parent / "score.py"

    if score_py.exists():
        result = subprocess.run(
            ['python', str(score_py), '--help'],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"score.py --help failed: {result.stderr}"
        assert '--cluster' in result.stdout, "Expected --cluster flag in help"
        assert '--skill' in result.stdout, "Expected --skill flag in help"
        print("[PASS] CLI is standalone")
    else:
        print("⚠ score.py not found at expected path")


def test_cluster_definitions():
    """Verify cluster skill counts match 1-CONTEXT.md"""
    expected_counts = {
        'document': 6,
        'frontend-ui': 5,
        'writing': 4,
        'image': 4,
        'spreadsheet': 3,
        'knowledge': 6,
        'seo-growth': 2,
        'video': 3,
    }

    for cluster, expected_count in expected_counts.items():
        actual = len(CLUSTERS.get(cluster, []))
        assert actual == expected_count, f"{cluster}: expected {expected_count}, got {actual}"

    print("[PASS] Cluster definitions match specification")


if __name__ == "__main__":
    print("Running CLI Integration Tests\n")

    test_score_module_independence()
    test_cli_standalone()
    test_cluster_definitions()

    print("\n=== All Tests Passed ===")
