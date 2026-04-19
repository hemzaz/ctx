"""
test_golden_graph.py -- Automated regression against the deterministic
graph built from tests/fixtures/.

The golden was captured once (Phase 3, commit b527fd0) and re-captured
after the Phase-5 ctx.py wrapper (commit ce88243). Any drift here flags
a change in catalog / graph build semantics.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_REPO_ROOT = _PROJECT_ROOT.parent  # src/../
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_GOLDEN = _REPO_ROOT / "tests" / "golden" / "graph-fixture.json"


@pytest.fixture()
def ctx_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point cfg at the fixture corpus + a throwaway CTX_HOME."""
    ctx_home = tmp_path / "ctx"
    ctx_home.mkdir()
    # cfg._USER_CONFIG is computed at module load as ~/.claude/skill-system-config.json
    # so we must place our override there under the redirected HOME.
    home_claude = tmp_path / ".claude"
    home_claude.mkdir()
    (home_claude / "skill-system-config.json").write_text(
        json.dumps(
            {
                "paths": {
                    "skills_dir": str(_FIXTURES / "skills"),
                    "agents_dir": str(_FIXTURES / "agents"),
                }
            }
        ),
        encoding="utf-8",
    )
    # CTX_HOME wins over config for ctx_home attr; point at tmp_path.
    monkeypatch.setenv("CTX_HOME", str(ctx_home))
    # HOME redirect so cfg._USER_CONFIG resolves to our override.
    monkeypatch.setenv("HOME", str(tmp_path))
    # cfg is a module-level singleton; reload so env/config take effect.
    import ctx_config
    importlib.reload(ctx_config)
    import wiki_graphify
    importlib.reload(wiki_graphify)
    return ctx_home, wiki_graphify


def test_graph_build_matches_golden(ctx_env) -> None:
    """Building the graph from tests/fixtures/ must produce the committed
    golden graph byte-for-byte. This protects the determinism contract
    (plan.md §Testing sandbox)."""
    ctx_home, wiki_graphify = ctx_env

    assert _GOLDEN.exists(), f"golden fixture missing: {_GOLDEN}"

    graph = wiki_graphify.build_graph()
    out_path = ctx_home / "graph.json"
    wiki_graphify.write_graph(graph, out_path)

    produced = json.loads(out_path.read_text(encoding="utf-8"))
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))

    assert produced == golden, (
        "graph build drifted from golden. Set membership or edge weights changed. "
        "If intentional, re-capture via: "
        "python src/ctx.py refresh && cp $CTX_HOME/graph.json "
        f"{_GOLDEN}"
    )


def test_graph_shape_expected(ctx_env) -> None:
    """Sanity: 8 skills + 2 agents = 10 nodes; known edges exist."""
    _, wiki_graphify = ctx_env
    G = wiki_graphify.build_graph()
    skills = sum(1 for _, d in G.nodes(data=True) if d.get("type") == "skill")
    agents = sum(1 for _, d in G.nodes(data=True) if d.get("type") == "agent")
    assert skills == 8
    assert agents == 2
    # docker-expert shares {docker, devops} with kubernetes-ops → weight 2
    assert G.has_edge("skill:docker-expert", "skill:kubernetes-ops")
    assert G["skill:docker-expert"]["skill:kubernetes-ops"]["weight"] == 2
    # react-ui / next-expert share {react, typescript, frontend} → weight 3
    assert G.has_edge("skill:react-ui", "skill:next-expert")
    assert G["skill:react-ui"]["skill:next-expert"]["weight"] == 3
