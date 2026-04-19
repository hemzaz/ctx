#!/usr/bin/env python3
"""
hook_installer.py -- Surgical, reversible installer for ctx hook entries
in ``~/.claude/settings.json``.

Three-layer marker on every inserted entry so uninstall can always find
what install wrote:
  1. JSON key           : ``"_ctx": true`` on the entry dict
  2. Path prefix        : every command line starts with ``<ctx_src>/``
  3. Shell-comment tag  : every command line ends with ``# @ctx-minimal``

Any ONE of these identifies an entry. Stripping matches if at least one
marker is present, so a manual edit that wipes the JSON key still leaves
us identifiable by the shell-comment suffix.

Write safety:
  - fcntl.flock on the target for the duration of the mutation
  - one-time backup at ``settings.json.pre-ctx.bak`` (never overwritten)
  - round-trip JSON validation before write
  - atomic tempfile + ``os.replace`` within the same directory
  - refuses on JSON parse failure, non-object settings, non-dict hooks

See plan.md §3.7 for the design.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from ctx_config import cfg  # noqa: E402


_MARKER_KEY = "_ctx"
_SHELL_MARKER = "# @ctx-minimal"


# ── Entry definition ────────────────────────────────────────────────────────


def default_entries(ctx_src_dir: Path) -> dict[str, list[dict]]:
    """Hook block this tool installs.

    PostToolUse runs context_monitor (intent signal extraction) and
    skill_suggest (surface to Claude). Both modules are no-ops unless
    ``cfg.enable_live_suggestions`` is True.
    """
    monitor_cmd = (
        f'python3 "{ctx_src_dir}/context_monitor.py" '
        f'--tool "$CLAUDE_TOOL_NAME" --input "$CLAUDE_TOOL_INPUT" '
        f'2>/dev/null || true {_SHELL_MARKER}'
    )
    suggest_cmd = (
        f'python3 "{ctx_src_dir}/skill_suggest.py" '
        f'2>/dev/null || true {_SHELL_MARKER}'
    )
    return {
        "PostToolUse": [
            {
                _MARKER_KEY: True,
                "matcher": ".*",
                "hooks": [
                    {"type": "command", "command": monitor_cmd},
                    {"type": "command", "command": suggest_cmd},
                ],
            }
        ],
    }


# ── Marker detection ────────────────────────────────────────────────────────


def _iter_commands(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if isinstance(entry.get("command"), str):
        out.append(entry["command"])
    for sub in entry.get("hooks", []) or []:
        if isinstance(sub, dict) and isinstance(sub.get("command"), str):
            out.append(sub["command"])
    return out


def _is_ctx_entry(entry: object, ctx_src_dir: Path | None = None) -> bool:
    """True if any of the three markers identifies this entry as ours."""
    if not isinstance(entry, dict):
        return False
    if entry.get(_MARKER_KEY) is True:
        return True
    prefix = f"{ctx_src_dir}/" if ctx_src_dir else None
    for cmd in _iter_commands(entry):
        if _SHELL_MARKER in cmd:
            return True
        if prefix and prefix in cmd:
            return True
    return False


# ── I/O helpers ─────────────────────────────────────────────────────────────


def _load_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    text = settings_path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"refusing to write: {settings_path} is invalid JSON ({exc}). "
            "Fix the file by hand and retry."
        ) from exc
    if not isinstance(data, dict):
        raise SystemExit(
            f"refusing to write: {settings_path} is not a JSON object"
        )
    return data


def _backup_once(settings_path: Path) -> Path:
    """Snapshot settings.json to .pre-ctx.bak; never overwrite."""
    backup = settings_path.with_suffix(settings_path.suffix + ".pre-ctx.bak")
    if not backup.exists() and settings_path.exists():
        backup.write_text(
            settings_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return backup


def _atomic_write(settings_path: Path, data: dict[str, Any]) -> None:
    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    # round-trip sanity check — refuse if we produced something unparseable
    try:
        json.loads(new_text)
    except json.JSONDecodeError as exc:  # pragma: no cover — defensive
        raise SystemExit(f"refusing: ctx produced invalid JSON ({exc})") from exc

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=settings_path.name + ".",
        suffix=".tmp",
        dir=str(settings_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp_name, settings_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ── Public API ──────────────────────────────────────────────────────────────


def install(settings_path: Path, ctx_src_dir: Path) -> dict[str, str]:
    """Insert tagged hook block into settings.json. Idempotent.

    Re-running: strips any existing ctx-tagged entries and re-inserts
    fresh copies. Non-ctx entries are untouched.
    """
    new_hooks = default_entries(ctx_src_dir)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Use the settings file itself as the lock target (creates if missing).
    with open(settings_path, "a+") as lockfile:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
        try:
            backup = _backup_once(settings_path)
            settings = _load_settings(settings_path)

            hooks_root = settings.setdefault("hooks", {})
            if not isinstance(hooks_root, dict):
                raise SystemExit(
                    "refusing to write: settings.hooks is not a JSON object"
                )

            for event, entries in new_hooks.items():
                existing = hooks_root.get(event, [])
                if not isinstance(existing, list):
                    raise SystemExit(
                        f"refusing to write: settings.hooks.{event} is not a list"
                    )
                pruned = [
                    e for e in existing if not _is_ctx_entry(e, ctx_src_dir)
                ]
                hooks_root[event] = pruned + entries

            _atomic_write(settings_path, settings)
        finally:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)

    return {"settings": str(settings_path), "backup": str(backup)}


def uninstall(
    settings_path: Path, ctx_src_dir: Path | None = None
) -> dict[str, Any]:
    """Strip ctx-tagged entries. Leaves backup alone so user can audit."""
    if not settings_path.exists():
        return {"status": "no-op", "reason": "no settings.json", "removed": 0}

    with open(settings_path, "a+") as lockfile:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
        try:
            settings = _load_settings(settings_path)
            hooks_root = settings.get("hooks", {})
            if not isinstance(hooks_root, dict):
                return {
                    "status": "no-op",
                    "reason": "hooks is not a dict",
                    "removed": 0,
                }

            removed = 0
            for event, entries in list(hooks_root.items()):
                if not isinstance(entries, list):
                    continue
                pruned = [
                    e for e in entries if not _is_ctx_entry(e, ctx_src_dir)
                ]
                removed += len(entries) - len(pruned)
                if pruned:
                    hooks_root[event] = pruned
                else:
                    del hooks_root[event]

            if not hooks_root:
                settings.pop("hooks", None)

            _atomic_write(settings_path, settings)
        finally:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)

    return {"status": "ok", "removed": removed}


def print_hook(ctx_src_dir: Path) -> str:
    """Return the JSON snippet for the user to paste; never touches disk."""
    return json.dumps(default_entries(ctx_src_dir), indent=2)


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ctx hook installer (install / uninstall / print)",
    )
    parser.add_argument(
        "action",
        choices=("install", "uninstall", "print"),
        help="What to do",
    )
    parser.add_argument(
        "--settings",
        default=str(cfg.claude_dir / "settings.json"),
        help="Path to settings.json",
    )
    parser.add_argument(
        "--ctx-src",
        default=str(Path(__file__).parent),
        help="Path to the ctx src/ directory (used in command strings)",
    )
    args = parser.parse_args()

    settings_path = Path(args.settings).expanduser()
    ctx_src = Path(args.ctx_src).expanduser()

    if args.action == "install":
        result = install(settings_path, ctx_src)
        print(f"Installed. Settings: {result['settings']}")
        print(f"Backup (first run only): {result['backup']}")
    elif args.action == "uninstall":
        result = uninstall(settings_path, ctx_src)
        print(
            f"Uninstall: {result['status']} "
            f"(removed {result.get('removed', 0)} entries)"
        )
    else:  # print
        print(print_hook(ctx_src))


if __name__ == "__main__":
    main()
