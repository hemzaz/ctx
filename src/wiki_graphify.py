#!/usr/bin/env python3
"""
wiki_graphify.py -- Build a knowledge graph of skills and agents from their
SKILL.md / agent-md frontmatter tags. Writes a single ``graph.json`` at
``cfg.graph_path``.

Single-pass filesystem scan. No entity-page pipeline. No community
detection. No concept pages. No wiki writes. Just a graph.

Graph shape:
  - Node ID  : ``skill:<name>`` or ``agent:<name>``
  - Node data: ``{label, type, tags}``
  - Edge     : two nodes share at least one tag
  - Weight   : number of shared tags (shared-tag-count scheme, plan §7 #3)
  - Edge data: ``{weight, shared_tags}`` (shared_tags sorted for determinism)

Usage::

    python wiki_graphify.py                       # default output (cfg.graph_path)
    python wiki_graphify.py --output /path.json   # explicit output
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

sys.path.insert(0, str(Path(__file__).parent))
from wiki_utils import parse_frontmatter as _parse_fm  # noqa: E402
from ctx_config import cfg  # noqa: E402


# ── Frontmatter helpers ──────────────────────────────────────────────────────


def _normalize_tags(value: Any) -> list[str]:
    """Accept list | csv-string | None; return a cleaned tag list."""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


def _read_tags(md_path: Path) -> list[str]:
    try:
        fm = _parse_fm(md_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not parse {md_path}: {exc}", file=sys.stderr)
        return []
    return _normalize_tags(fm.get("tags", []))


# ── Directory scanners ──────────────────────────────────────────────────────


def _scan_skills(skills_dir: Path) -> list[tuple[str, list[str]]]:
    """Every ``<skill>/SKILL.md`` under ``skills_dir`` → (name, tags)."""
    out: list[tuple[str, list[str]]] = []
    if not skills_dir.is_dir():
        return out
    for skill_md in skills_dir.rglob("SKILL.md"):
        out.append((skill_md.parent.name, _read_tags(skill_md)))
    return out


def _scan_agents(agents_dir: Path) -> list[tuple[str, list[str]]]:
    """Every ``*.md`` under ``agents_dir`` (excluding SKILL.md) → (name, tags)."""
    out: list[tuple[str, list[str]]] = []
    if not agents_dir.is_dir():
        return out
    for md in agents_dir.rglob("*.md"):
        if md.name == "SKILL.md":
            continue
        out.append((md.stem, _read_tags(md)))
    return out


# ── Graph construction ──────────────────────────────────────────────────────


def build_graph() -> nx.Graph:
    """Walk cfg.skills_dir / cfg.agents_dir / cfg.extra_skill_dirs and return graph."""
    G = nx.Graph()

    def _add(nid: str, label: str, node_type: str, tags: list[str]) -> None:
        if nid in G:
            return
        G.add_node(nid, label=label, type=node_type, tags=tags)

    for name, tags in _scan_skills(cfg.skills_dir):
        _add(f"skill:{name}", name, "skill", tags)
    for name, tags in _scan_agents(cfg.agents_dir):
        _add(f"agent:{name}", name, "agent", tags)
    for extra in cfg.extra_skill_dirs:
        if not extra.is_dir():
            continue
        for name, tags in _scan_skills(extra):
            _add(f"skill:{name}", name, "skill", tags)
        for name, tags in _scan_agents(extra):
            _add(f"agent:{name}", name, "agent", tags)

    # Tag → nodes index for pairwise edge creation.
    tag_index: dict[str, list[str]] = defaultdict(list)
    for nid, data in G.nodes(data=True):
        for tag in data.get("tags", []):
            if tag and tag != "uncategorized":
                tag_index[tag].append(nid)

    # Shared-tag-count weighted edges (plan §7 answer #3).
    for tag, nodes in tag_index.items():
        for i, n1 in enumerate(nodes):
            for n2 in nodes[i + 1:]:
                if G.has_edge(n1, n2):
                    G[n1][n2]["weight"] += 1
                    G[n1][n2]["shared_tags"].append(tag)
                else:
                    G.add_edge(n1, n2, weight=1, shared_tags=[tag])

    return G


# ── Serialization ───────────────────────────────────────────────────────────


def write_graph(G: nx.Graph, path: Path) -> None:
    """Emit node_link JSON with deterministic ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)

    data = json_graph.node_link_data(G, edges="edges")
    # Stable node ordering, stable edge ordering, sorted shared_tags.
    data["nodes"] = sorted(data["nodes"], key=lambda n: str(n.get("id", "")))
    edges_key = "edges" if "edges" in data else "links"
    edges = data.get(edges_key, [])
    for e in edges:
        if "shared_tags" in e:
            e["shared_tags"] = sorted(e["shared_tags"])
    data[edges_key] = sorted(
        edges,
        key=lambda e: (str(e.get("source", "")), str(e.get("target", ""))),
    )

    path.write_text(
        json.dumps(data, indent=2, default=str, sort_keys=True),
        encoding="utf-8",
    )


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build skill/agent knowledge graph from frontmatter tags",
    )
    parser.add_argument(
        "--output",
        default=str(cfg.graph_path),
        help=f"Output graph.json path (default: {cfg.graph_path})",
    )
    args = parser.parse_args()

    G = build_graph()
    write_graph(G, Path(args.output))

    skills = sum(1 for _, d in G.nodes(data=True) if d.get("type") == "skill")
    agents = sum(1 for _, d in G.nodes(data=True) if d.get("type") == "agent")
    print(
        f"Graph: {G.number_of_nodes()} nodes "
        f"({skills} skills, {agents} agents), "
        f"{G.number_of_edges()} edges"
    )
    print(f"Written to: {args.output}")


if __name__ == "__main__":
    main()
