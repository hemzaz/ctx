#!/usr/bin/env bash
# install.sh — ctx-minimal installer (phased, confirmed, reversible).
#
# Default install writes exactly three things:
#   1. $CTX_HOME or ~/.claude/ctx/                  (catalog.json + graph.json)
#   2. ~/.claude/agents/skill-router.md             (router agent, single file)
#   3. ~/.claude/commands/ctx.md                    (/ctx slash command)
#
# Hooks are NOT installed by default. Pass --with-hooks to additionally
# invoke `ctx install-hook`, which writes a tagged block into
# ~/.claude/settings.json with a one-time .pre-ctx.bak backup.
#
# Usage:
#   ./install.sh                    # interactive y/N per step
#   ./install.sh --yes              # non-interactive, no hooks
#   ./install.sh --dry-run          # print what would happen
#   ./install.sh --with-hooks       # also install live-suggestion hooks
#   ./install.sh --yes --with-hooks # non-interactive including hooks
#   ./install.sh --ctx-dir PATH     # install from a non-default checkout

set -euo pipefail

# ── Flags ────────────────────────────────────────────────────────────────────
DRY_RUN=0
ASSUME_YES=0
WITH_HOOKS=0
CTX_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=1; shift ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    --with-hooks)  WITH_HOOKS=1; shift ;;
    --ctx-dir)     CTX_DIR="$2"; shift 2 ;;
    -h|--help)     sed -n '2,25p' "$0"; exit 0 ;;
    *)             echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX_DIR="${CTX_DIR:-$SCRIPT_DIR}"
SRC_DIR="$CTX_DIR/src"

CLAUDE_DIR="$HOME/.claude"
AGENTS_DIR="$CLAUDE_DIR/agents"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SKILLS_DIR="$CLAUDE_DIR/skills"
CTX_STATE_DIR="${CTX_HOME:-$CLAUDE_DIR/ctx}"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON="python"
fi

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { echo "[install] $*"; }
ok()   { echo "[install] ✓ $*"; }
warn() { echo "[install] ⚠ $*"; }

confirm() {
  local prompt="$1"
  [[ "$ASSUME_YES" == 1 ]] && return 0
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

act() {
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "  [dry-run] $*"
  else
    eval "$*"
  fi
}

# ── Preflight ────────────────────────────────────────────────────────────────
echo "ctx-minimal install"
echo "  source:    $CTX_DIR"
echo "  state:     $CTX_STATE_DIR"
echo "  router:    $AGENTS_DIR/skill-router.md"
echo "  slash cmd: $COMMANDS_DIR/ctx.md"
echo "  hooks:     $([[ "$WITH_HOOKS" == 1 ]] && echo "opt-in: will ask" || echo "SKIPPED (use --with-hooks)")"
echo "  mode:      dry-run=$DRY_RUN, assume-y=$ASSUME_YES"
echo

if [[ ! -d "$SRC_DIR" ]]; then
  echo "error: $SRC_DIR does not exist" >&2
  exit 1
fi

# ── Step 1: Create ctx state dir ─────────────────────────────────────────────
log "Step 1: Create state dir $CTX_STATE_DIR"
if confirm "Create $CTX_STATE_DIR?"; then
  act "mkdir -p '$CTX_STATE_DIR'"
  ok "State dir ready"
else
  warn "Skipped — aborting (state dir is required)"
  exit 1
fi

# ── Step 2: Build catalog ────────────────────────────────────────────────────
log "Step 2: Build $CTX_STATE_DIR/catalog.json"
if confirm "Scan ~/.claude/skills and ~/.claude/agents into catalog.json?"; then
  act "CTX_HOME='$CTX_STATE_DIR' '$PYTHON' '$SRC_DIR/catalog_builder.py'"
  ok "Catalog built"
else
  warn "Skipped catalog build"
fi

# ── Step 3: Build graph ──────────────────────────────────────────────────────
log "Step 3: Build $CTX_STATE_DIR/graph.json"
if confirm "Build knowledge graph from skill/agent tag frontmatter?"; then
  act "CTX_HOME='$CTX_STATE_DIR' '$PYTHON' '$SRC_DIR/wiki_graphify.py'"
  ok "Graph built"
else
  warn "Skipped graph build"
fi

# ── Step 4: Deploy skill-router agent ────────────────────────────────────────
ROUTER_SRC="$CTX_DIR/skills/skill-router/SKILL.md"
ROUTER_DST="$AGENTS_DIR/skill-router.md"
log "Step 4: Deploy skill-router to $ROUTER_DST"
if [[ ! -f "$ROUTER_SRC" ]]; then
  warn "$ROUTER_SRC not found — skipping router deploy"
elif confirm "Copy skill-router.md to $AGENTS_DIR?"; then
  act "mkdir -p '$AGENTS_DIR'"
  act "cp '$ROUTER_SRC' '$ROUTER_DST'"
  ok "skill-router deployed"
else
  warn "Skipped router deploy"
fi

# ── Step 5: Install /ctx slash command ───────────────────────────────────────
SLASH_SRC="$CTX_DIR/commands/ctx.md"
SLASH_DST="$COMMANDS_DIR/ctx.md"
log "Step 5: Install /ctx slash command to $SLASH_DST"
if [[ ! -f "$SLASH_SRC" ]]; then
  warn "$SLASH_SRC not found — skipping slash command"
elif confirm "Copy /ctx slash command to $COMMANDS_DIR?"; then
  act "mkdir -p '$COMMANDS_DIR'"
  act "cp '$SLASH_SRC' '$SLASH_DST'"
  ok "/ctx installed"
else
  warn "Skipped slash command"
fi

# ── Step 6 (optional): Install hooks ─────────────────────────────────────────
if [[ "$WITH_HOOKS" == 1 ]]; then
  log "Step 6: Install PostToolUse hooks into $CLAUDE_DIR/settings.json"
  echo "  This writes a tagged block with _ctx:true + # @ctx-minimal markers."
  echo "  A one-time backup goes to settings.json.pre-ctx.bak."
  echo "  Hooks are no-ops until you set enable_live_suggestions: true"
  echo "  in ~/.claude/skill-system-config.json."
  if confirm "Proceed with hook install?"; then
    act "'$PYTHON' '$SRC_DIR/ctx.py' install-hook"
    ok "Hooks installed"
  else
    warn "Skipped hook install"
  fi
else
  log "Step 6: Skipping hook install (default; pass --with-hooks to enable)"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════"
echo " ctx-minimal installed"
echo "═══════════════════════════════════════════════════════"
echo " State dir:    $CTX_STATE_DIR"
echo " Router:       $ROUTER_DST"
echo " Slash cmd:    $SLASH_DST"
echo
echo " Try it:"
echo "   $PYTHON $SRC_DIR/ctx.py recommend --project . --top 10"
echo "   $PYTHON $SRC_DIR/ctx.py doctor"
echo
echo " In a Claude Code session:"
echo "   /ctx"
echo
echo " Uninstall:"
echo "   $CTX_DIR/uninstall.sh"
echo
