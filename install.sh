#!/usr/bin/env bash
# install.sh -- Phase-3-scope installer for ctx-minimal.
#
# What this does:
#   1. Creates the ctx state directory (~/.claude/ctx or $CTX_HOME)
#   2. Builds catalog.json from ~/.claude/skills + ~/.claude/agents
#   3. Builds graph.json from the same (SKILL.md tag frontmatter)
#   4. Deploys skill-router markdown to ~/.claude/agents/skill-router.md
#
# What this does NOT do (Phase 6 will extend):
#   - Does not write ~/.claude/settings.json (hook installation is opt-in
#     in Phase 4+ via `ctx install-hook`)
#   - Does not rewrite any existing skill or agent files
#   - Does not initialize a wiki (the wiki subsystem was removed)
#
# Usage:
#   bash install.sh [--ctx-dir /path/to/ctx]

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
CLAUDE_DIR="$HOME/.claude"
AGENTS_DIR="$CLAUDE_DIR/agents"
SKILLS_DIR="$CLAUDE_DIR/skills"
CTX_STATE_DIR="${CTX_HOME:-$CLAUDE_DIR/ctx}"

# Resolve ctx/ dir. Accepts: no args, `--ctx-dir PATH`, or positional PATH.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--ctx-dir" && -n "${2:-}" ]]; then
  CTX_DIR="$2"
elif [[ -n "${1:-}" && "${1:-}" != --* ]]; then
  CTX_DIR="$1"
else
  CTX_DIR="$SCRIPT_DIR"
fi
SRC_DIR="$CTX_DIR/src"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON="python"
fi

log() { echo "[install] $*"; }
ok()  { echo "[install] ✓ $*"; }
warn(){ echo "[install] ⚠ $*"; }

# ── Step 1: Create ctx state dir ─────────────────────────────────────────────
log "Step 1: Creating state dir $CTX_STATE_DIR"
mkdir -p "$CTX_STATE_DIR"
ok "State dir ready"

# ── Step 2: Build catalog ────────────────────────────────────────────────────
log "Step 2: Building catalog → $CTX_STATE_DIR/catalog.json"
"$PYTHON" "$SRC_DIR/catalog_builder.py" \
  --skills-dir "$SKILLS_DIR" \
  --agents-dir "$AGENTS_DIR"
ok "Catalog built"

# ── Step 3: Build knowledge graph ────────────────────────────────────────────
log "Step 3: Building graph → $CTX_STATE_DIR/graph.json"
"$PYTHON" "$SRC_DIR/wiki_graphify.py"
ok "Graph built"

# ── Step 4: Deploy skill-router agent ────────────────────────────────────────
ROUTER_SRC="$CTX_DIR/skills/skill-router"
if [[ -d "$ROUTER_SRC" && -f "$ROUTER_SRC/SKILL.md" ]]; then
  log "Step 4: Deploying skill-router to $AGENTS_DIR/skill-router.md"
  mkdir -p "$AGENTS_DIR"
  cp "$ROUTER_SRC/SKILL.md" "$AGENTS_DIR/skill-router.md"
  ok "skill-router deployed (single file, no directory sprawl)"
else
  warn "skills/skill-router/SKILL.md not found in $CTX_DIR — skipping router deploy"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo " ctx-minimal installed (Phase 3 scope)"
echo "═══════════════════════════════════════════════════════"
echo " State dir:    $CTX_STATE_DIR"
echo " Router agent: $AGENTS_DIR/skill-router.md"
echo " Source:       $SRC_DIR"
echo ""
echo " Hooks are NOT installed. They are opt-in from Phase 4 via:"
echo "   $PYTHON $SRC_DIR/ctx.py install-hook   # (Phase 5+)"
echo ""
echo " Refresh graph + catalog after adding skills:"
echo "   $PYTHON $SRC_DIR/catalog_builder.py"
echo "   $PYTHON $SRC_DIR/wiki_graphify.py"
echo ""
echo " Recommend skills for the current project:"
echo "   $PYTHON $SRC_DIR/scan_repo.py --repo . --output $CTX_STATE_DIR/stack-profile.json"
echo "   $PYTHON $SRC_DIR/resolve_graph.py --tags python,api --top 10"
echo ""
echo " Uninstall:"
echo "   $CTX_DIR/uninstall.sh"
echo ""
