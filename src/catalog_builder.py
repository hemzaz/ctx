#!/usr/bin/env python3
"""
catalog_builder.py -- Index all installed skills and agents into a single
JSON catalog at ``cfg.catalog_path``.

One record per skill/agent with name, type, path, line count, tags, and an
``over_threshold`` flag (informational: skills longer than
``cfg.line_threshold`` may be candidates for splitting at author time, but
the tool never rewrites them).

Usage::

    python catalog_builder.py                        # default dirs from cfg
    python catalog_builder.py --skills-dir /path     # override
    python catalog_builder.py --extra-dirs /a /b
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ctx_config import cfg  # noqa: E402
from wiki_utils import parse_frontmatter as _parse_fm  # noqa: E402


def _normalize_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


def _record(md_path: Path, name: str, node_type: str) -> dict:
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not read {md_path}: {exc}", file=sys.stderr)
        text = ""
    fm = _parse_fm(text) if text else {}
    lines = len(text.splitlines())
    return {
        "name": name,
        "type": node_type,
        "path": str(md_path),
        "lines": lines,
        "tags": _normalize_tags(fm.get("tags", [])),
        "over_threshold": lines > cfg.line_threshold,
    }


def scan_skills_dir(skills_dir: Path) -> list[dict]:
    """Every ``<skill>/SKILL.md`` under ``skills_dir``."""
    results: list[dict] = []
    if not skills_dir.is_dir():
        return results
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        results.append(_record(skill_md, skill_md.parent.name, "skill"))
    return results


def scan_agents_dir(agents_dir: Path) -> list[dict]:
    """Every ``*.md`` under ``agents_dir`` (excluding ``SKILL.md``)."""
    results: list[dict] = []
    if not agents_dir.is_dir():
        return results
    for md in sorted(agents_dir.rglob("*.md")):
        if md.name == "SKILL.md":
            continue
        results.append(_record(md, md.stem, "agent"))
    return results


def build_catalog(
    skills_dir: Path,
    agents_dir: Path,
    extra_dirs: list[Path],
) -> dict:
    items: list[dict] = []
    items.extend(scan_skills_dir(skills_dir))
    items.extend(scan_agents_dir(agents_dir))
    for extra in extra_dirs:
        if not extra.is_dir():
            continue
        sub_skills = scan_skills_dir(extra)
        if sub_skills:
            items.extend(sub_skills)
        else:
            items.extend(scan_agents_dir(extra))

    # Deduplicate by (type, name) keeping first occurrence
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for it in items:
        key = (it["type"], it["name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    skills = sum(1 for i in deduped if i["type"] == "skill")
    agents = sum(1 for i in deduped if i["type"] == "agent")
    over_threshold = sum(1 for i in deduped if i["over_threshold"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(deduped),
        "skills": skills,
        "agents": agents,
        "over_threshold": over_threshold,
        "line_threshold": cfg.line_threshold,
        "items": deduped,
    }


def write_catalog(catalog: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build skill/agent catalog JSON at cfg.catalog_path",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(cfg.skills_dir),
        help=f"Skills directory (default: {cfg.skills_dir})",
    )
    parser.add_argument(
        "--agents-dir",
        default=str(cfg.agents_dir),
        help=f"Agents directory (default: {cfg.agents_dir})",
    )
    parser.add_argument(
        "--extra-dirs",
        nargs="*",
        default=[str(p) for p in cfg.extra_skill_dirs],
        help="Additional skill/agent source directories",
    )
    parser.add_argument(
        "--output",
        default=str(cfg.catalog_path),
        help=f"Output catalog path (default: {cfg.catalog_path})",
    )
    args = parser.parse_args()

    catalog = build_catalog(
        skills_dir=Path(args.skills_dir),
        agents_dir=Path(args.agents_dir),
        extra_dirs=[Path(d) for d in args.extra_dirs],
    )
    write_catalog(catalog, Path(args.output))

    print(
        f"Catalog: {catalog['total']} items "
        f"({catalog['skills']} skills, {catalog['agents']} agents), "
        f"{catalog['over_threshold']} over {catalog['line_threshold']} lines"
    )
    print(f"Written to: {args.output}")


if __name__ == "__main__":
    main()
