#!/usr/bin/env python3
"""
ctx.py -- Single CLI entrypoint for ctx-minimal.

Primary user surface: ``/ctx`` slash command invokes this module to
produce recommendations on demand. No hooks required.

Subcommands::

    ctx recommend [--project P] [--top N] [--json]
    ctx refresh
    ctx show-pending
    ctx load NAME[,NAME...]
    ctx install-hook
    ctx uninstall-hook
    ctx print-hook
    ctx doctor
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ctx_config import cfg  # noqa: E402

_SRC_DIR = Path(__file__).parent


# ── helpers ─────────────────────────────────────────────────────────────────


def _run(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess, inheriting env so CTX_HOME propagates."""
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=capture,
    )


def _python() -> str:
    """Use the same interpreter ctx.py is running under."""
    return sys.executable or "python3"


def _scan_repo(project: Path, output: Path) -> None:
    _run(
        [
            _python(),
            str(_SRC_DIR / "scan_repo.py"),
            "--repo",
            str(project),
            "--output",
            str(output),
        ]
    )


def _resolve_skills(
    profile: Path, wiki: Path, skills_dir: Path, output: Path
) -> None:
    _run(
        [
            _python(),
            str(_SRC_DIR / "resolve_skills.py"),
            "--profile",
            str(profile),
            "--wiki",
            str(wiki),
            "--available-skills",
            str(skills_dir),
            "--output",
            str(output),
        ]
    )


def _resolve_graph_tags(
    tags: list[str], top: int, as_json: bool
) -> str:
    args = [
        _python(),
        str(_SRC_DIR / "resolve_graph.py"),
        "--tags",
        ",".join(tags),
        "--top",
        str(top),
    ]
    if as_json:
        args.append("--json")
    result = _run(args, capture=True)
    return result.stdout


def _extract_tags(stack_profile: Path) -> list[str]:
    """Pull signal tags out of scan_repo's stack profile.

    scan_repo emits per-category lists of ``{name, confidence, evidence, ...}``
    dicts under keys like ``frameworks``, ``infrastructure``, ``data_stores``,
    ``testing``, ``ai_tooling``, ``build_system``, ``languages``, ``docs``.
    We flatten the ``name`` field of each entry into the tag set, then add
    ``project_type`` if present and any string entries under ``custom_signals``.
    """
    data = json.loads(stack_profile.read_text(encoding="utf-8"))
    tags: set[str] = set()

    category_keys = (
        "languages",
        "frameworks",
        "infrastructure",
        "data_stores",
        "testing",
        "ai_tooling",
        "build_system",
        "docs",
    )
    for key in category_keys:
        entries = data.get(key, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name:
                    tags.add(name.lower())
            elif isinstance(entry, str) and entry:
                tags.add(entry.lower())

    project_type = data.get("project_type")
    if isinstance(project_type, str) and project_type:
        tags.add(project_type.lower())

    custom = data.get("custom_signals", {})
    if isinstance(custom, dict):
        for v in custom.values():
            if isinstance(v, str):
                tags.add(v.lower())
            elif isinstance(v, list):
                for s in v:
                    if isinstance(s, str):
                        tags.add(s.lower())

    return sorted(tags)


# ── subcommands ─────────────────────────────────────────────────────────────


def cmd_recommend(args: argparse.Namespace) -> int:
    project = Path(args.project or os.getcwd()).resolve()
    cfg.ctx_home.mkdir(parents=True, exist_ok=True)

    print(f"[ctx] scanning {project}", file=sys.stderr)
    _scan_repo(project, cfg.stack_profile)

    tags = _extract_tags(cfg.stack_profile)
    if not tags:
        print("[ctx] no stack signals detected. Try --tags or enrich project.", file=sys.stderr)
        return 1

    print(f"[ctx] detected: {', '.join(tags[:10])}", file=sys.stderr)

    if not cfg.graph_path.exists():
        print(
            f"[ctx] graph not found at {cfg.graph_path}. Run: ctx refresh",
            file=sys.stderr,
        )
        return 2

    output = _resolve_graph_tags(tags, args.top, as_json=args.json)
    sys.stdout.write(output)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    cfg.ctx_home.mkdir(parents=True, exist_ok=True)
    print(f"[ctx] rebuilding catalog → {cfg.catalog_path}", file=sys.stderr)
    _run([_python(), str(_SRC_DIR / "catalog_builder.py")])
    print(f"[ctx] rebuilding graph → {cfg.graph_path}", file=sys.stderr)
    _run([_python(), str(_SRC_DIR / "wiki_graphify.py")])
    return 0


def cmd_show_pending(args: argparse.Namespace) -> int:
    if not cfg.pending_skills.exists():
        print("No pending suggestions.")
        return 0
    text = cfg.pending_skills.read_text(encoding="utf-8")
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    cmd = [_python(), str(_SRC_DIR / "skill_loader.py"), "--names", args.names]
    return subprocess.run(cmd).returncode


def cmd_install_hook(args: argparse.Namespace) -> int:
    cmd = [
        _python(),
        str(_SRC_DIR / "hook_installer.py"),
        "install",
        "--settings",
        str(cfg.claude_dir / "settings.json"),
        "--ctx-src",
        str(_SRC_DIR),
    ]
    return subprocess.run(cmd).returncode


def cmd_uninstall_hook(args: argparse.Namespace) -> int:
    cmd = [
        _python(),
        str(_SRC_DIR / "hook_installer.py"),
        "uninstall",
        "--settings",
        str(cfg.claude_dir / "settings.json"),
        "--ctx-src",
        str(_SRC_DIR),
    ]
    return subprocess.run(cmd).returncode


def cmd_print_hook(args: argparse.Namespace) -> int:
    cmd = [
        _python(),
        str(_SRC_DIR / "hook_installer.py"),
        "print",
        "--ctx-src",
        str(_SRC_DIR),
    ]
    return subprocess.run(cmd).returncode


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"ctx_home:         {cfg.ctx_home}")
    print(f"  exists:         {cfg.ctx_home.exists()}")
    print(f"skills_dir:       {cfg.skills_dir}  (exists={cfg.skills_dir.exists()})")
    print(f"agents_dir:       {cfg.agents_dir}  (exists={cfg.agents_dir.exists()})")
    print(f"read_only:        {cfg.read_only}")
    print(f"live_suggestions: {cfg.enable_live_suggestions}")
    print(f"line_threshold:   {cfg.line_threshold}")
    print()

    for label, path in (
        ("catalog", cfg.catalog_path),
        ("graph",   cfg.graph_path),
        ("manifest", cfg.manifest_path),
        ("pending", cfg.pending_skills),
        ("stack_profile", cfg.stack_profile),
    ):
        if path.exists():
            mtime = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(path.stat().st_mtime),
            )
            size = path.stat().st_size
            print(f"  {label:15s} {path}  ({size} B, {mtime})")
        else:
            print(f"  {label:15s} {path}  (missing)")

    print()
    if cfg.graph_path.exists():
        try:
            g = json.loads(cfg.graph_path.read_text(encoding="utf-8"))
            print(
                f"graph: {len(g.get('nodes', []))} nodes, "
                f"{len(g.get('edges', g.get('links', [])))} edges"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"graph: unreadable ({exc})")
    return 0


# ── CLI plumbing ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctx",
        description="ctx-minimal: skill + agent recommendation engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("recommend", help="Scan project and suggest top-N skills/agents")
    p.add_argument("--project", default=None, help="Project root (default: cwd)")
    p.add_argument("--top", type=int, default=10, help="Number of suggestions (default 10)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    p.set_defaults(func=cmd_recommend)

    p = sub.add_parser("refresh", help="Rebuild catalog.json and graph.json")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("show-pending", help="Show current pending suggestions")
    p.set_defaults(func=cmd_show_pending)

    p = sub.add_parser("load", help="Load a skill or agent into the session manifest")
    p.add_argument("names", help="Comma-separated skill/agent names")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("install-hook", help="Opt-in: install PostToolUse hook into settings.json")
    p.set_defaults(func=cmd_install_hook)

    p = sub.add_parser("uninstall-hook", help="Strip tagged hook entries from settings.json")
    p.set_defaults(func=cmd_uninstall_hook)

    p = sub.add_parser("print-hook", help="Print hook JSON snippet to stdout (never writes)")
    p.set_defaults(func=cmd_print_hook)

    p = sub.add_parser("doctor", help="Show state dir / graph / catalog status")
    p.set_defaults(func=cmd_doctor)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
