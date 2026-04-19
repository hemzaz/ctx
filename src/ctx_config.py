"""
ctx_config.py -- Central configuration loader for ctx-minimal.

Loads from (in priority order):
  1. CTX_HOME env var                         (overrides ctx_home only)
  2. ~/.claude/skill-system-config.json       (user overrides, deep-merged)
  3. <script_dir>/config.json                 (repo default)

All runtime state lives under ``ctx_home`` (default ``~/.claude/ctx``) and
all state-file paths are derived from it. Only ``skills_dir``, ``agents_dir``,
and ``claude_dir`` point outside ``ctx_home`` — those are read-only sources
this tool never writes to.

Usage::

    from ctx_config import cfg

    manifest = cfg.manifest_path
    max_skills = cfg.max_skills
"""

import json
import os
import sys
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_CONFIG = _SCRIPT_DIR / "config.json"
_USER_CONFIG = Path(os.path.expanduser("~/.claude/skill-system-config.json"))


def _load_raw() -> dict[str, Any]:
    """Load and merge default + user config."""
    raw: dict[str, Any] = {}

    if _DEFAULT_CONFIG.exists():
        try:
            raw = json.loads(_DEFAULT_CONFIG.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: failed to load default config: {exc}", file=sys.stderr)

    if _USER_CONFIG.exists():
        try:
            user = json.loads(_USER_CONFIG.read_text(encoding="utf-8"))
            _deep_merge(raw, user)
        except Exception as exc:
            print(f"Warning: failed to load user config: {exc}", file=sys.stderr)

    return raw


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place (recursive for nested dicts)."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _expand(value: str) -> str:
    """Expand ~ and env vars in path strings."""
    return os.path.expandvars(os.path.expanduser(value))


def _resolve_ctx_home(paths: dict[str, Any]) -> Path:
    """CTX_HOME env var wins over config; fallback to ~/.claude/ctx."""
    env = os.environ.get("CTX_HOME")
    if env:
        return Path(_expand(env))
    return Path(_expand(paths.get("ctx_home", "~/.claude/ctx")))


class Config:
    """Typed access to configuration values."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        paths = raw.get("paths", {})
        resolver = raw.get("resolver", {})
        monitor = raw.get("context_monitor", {})
        tracker = raw.get("usage_tracker", {})

        # ── Read-only source directories ──────────────────────────────────
        self.claude_dir = Path(_expand(paths.get("claude_dir", "~/.claude")))
        self.skills_dir = Path(_expand(paths.get("skills_dir", "~/.claude/skills")))
        self.agents_dir = Path(_expand(paths.get("agents_dir", "~/.claude/agents")))

        # ── ctx_home: single root for all runtime state ───────────────────
        self.ctx_home = _resolve_ctx_home(paths)

        # ── Derived state paths (always under ctx_home) ───────────────────
        self.manifest_path = self.ctx_home / "manifest.json"
        self.intent_log = self.ctx_home / "intent-log.jsonl"
        self.pending_skills = self.ctx_home / "pending.json"
        self.pending_unload = self.ctx_home / "pending-unload.json"
        self.shown_flag = self.ctx_home / ".shown"
        self.stack_profile = self.ctx_home / "stack-profile.json"
        self.catalog_path = self.ctx_home / "catalog.json"
        self.graph_path = self.ctx_home / "graph.json"
        self.skill_registry = self.ctx_home / "registry.json"

        # ── Legacy alias preserved during Phase 2 for wiki_graphify only.
        # Removed in Phase 3 when wiki_graphify is rewritten.
        self.skill_manifest = self.manifest_path

        # ── Resolver ──────────────────────────────────────────────────────
        self.max_skills: int = resolver.get("max_skills", 15)
        self.intent_boost_per_signal: int = resolver.get("intent_boost_per_signal", 5)
        self.intent_boost_max: int = resolver.get("intent_boost_max", 15)
        self.staleness_penalty: int = resolver.get("staleness_penalty", -8)
        self.meta_skills: list[str] = resolver.get("meta_skills", ["skill-router", "file-reading"])

        # ── Context Monitor ───────────────────────────────────────────────
        self.unmatched_signal_threshold: int = monitor.get("unmatched_signal_threshold", 3)
        self.manifest_stale_minutes: int = monitor.get("manifest_stale_minutes", 60)

        # ── Usage Tracker ─────────────────────────────────────────────────
        self.stale_threshold_sessions: int = tracker.get("stale_threshold_sessions", 30)
        self.keep_log_days: int = tracker.get("keep_log_days", 5)

        # ── Catalog ───────────────────────────────────────────────────────
        self.line_threshold: int = int(raw.get("line_threshold", 180))

        # ── Safety flags ──────────────────────────────────────────────────
        # read_only: when True (default), no writer may mutate files under
        # ~/.claude/skills or ~/.claude/agents. Contract is grep-enforced
        # (see scripts/check-contracts.sh).
        self.read_only: bool = bool(raw.get("read_only", True))
        # enable_live_suggestions: when False (default), context_monitor
        # and skill_suggest are no-ops even if the PostToolUse hook fires.
        # Set to True only for power users who opt into mid-session
        # monitoring via `ctx install-hook`.
        self.enable_live_suggestions: bool = bool(
            raw.get("enable_live_suggestions", False)
        )

        # ── Extra Skill Dirs ──────────────────────────────────────────────
        self.extra_skill_dirs: list[Path] = [
            Path(_expand(d)) for d in raw.get("extra_skill_dirs", [])
        ]

        # ── Tag Taxonomy ──────────────────────────────────────────────────
        self.all_tags: list[str] = raw.get("tags", [
            "python", "javascript", "typescript", "rust", "go", "java", "ruby", "swift", "kotlin",
            "react", "vue", "angular", "nextjs", "fastapi", "django", "express", "flask",
            "docker", "kubernetes", "terraform", "ci-cd", "aws", "gcp", "azure",
            "sql", "nosql", "redis", "kafka", "spark", "dbt", "airflow",
            "llm", "agents", "mcp", "langchain", "embeddings", "fine-tuning", "rag",
            "testing", "linting", "typing", "security", "performance",
            "documentation", "api-spec", "markdown", "diagrams",
            "comparison", "decision", "pattern", "troubleshooting",
            "marketplace", "registry", "versioning", "compatibility",
        ])

    def get(self, key: str, default: Any = None) -> Any:
        """Raw key access (dot-separated: 'paths.ctx_home')."""
        parts = key.split(".")
        node: Any = self._raw
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return default
        return node

    def all_skill_dirs(self) -> list[Path]:
        """Return all skill directories (primary + extra)."""
        dirs = [self.skills_dir, self.agents_dir] + self.extra_skill_dirs
        return [d for d in dirs if d.exists()]


# Singleton instance — import this
cfg = Config(_load_raw())


def reload() -> None:
    """Reload config from disk (useful if config changed during session)."""
    global cfg
    cfg = Config(_load_raw())
