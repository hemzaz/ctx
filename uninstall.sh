#!/usr/bin/env bash
# uninstall.sh — reverse a ctx-minimal install.
#
# Removes:
#   1. $CTX_HOME or ~/.claude/ctx/             (state dir; atomic rm -rf)
#   2. ~/.claude/agents/skill-router.md        (router agent file)
#   3. ~/.claude/commands/ctx.md               (/ctx slash command)
#   4. Tagged hook block in ~/.claude/settings.json (only if present)
#
# Never touches:
#   - ~/.claude/skills/** or ~/.claude/agents/** (other than the router file)
#   - settings.json.pre-ctx.bak (left for your audit)
#   - Any user-installed skill or agent
#
# Usage:
#   ./uninstall.sh              # interactive y/N per step
#   ./uninstall.sh --yes        # non-interactive
#   ./uninstall.sh --dry-run    # print what would be removed

set -euo pipefail

DRY_RUN=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=1 ;;
    --yes|-y)   ASSUME_YES=1 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX_DIR="$SCRIPT_DIR"
SRC_DIR="$CTX_DIR/src"

CLAUDE_DIR="$HOME/.claude"
AGENTS_DIR="$CLAUDE_DIR/agents"
COMMANDS_DIR="$CLAUDE_DIR/commands"
CTX_STATE_DIR="${CTX_HOME:-$CLAUDE_DIR/ctx}"
SETTINGS="$CLAUDE_DIR/settings.json"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON="python"
fi

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

echo "ctx-minimal uninstall"
echo "  state dir:  $CTX_STATE_DIR"
echo "  router:     $AGENTS_DIR/skill-router.md"
echo "  slash cmd:  $COMMANDS_DIR/ctx.md"
echo "  settings:   $SETTINGS"
echo "  mode:       dry-run=$DRY_RUN, assume-y=$ASSUME_YES"
echo

# ── Step 1: state dir ────────────────────────────────────────────────────────
if [[ -d "$CTX_STATE_DIR" ]]; then
  echo "Contents of $CTX_STATE_DIR:"
  find "$CTX_STATE_DIR" -maxdepth 2 -type f 2>/dev/null | sed 's/^/  /' || true
  if confirm "Remove $CTX_STATE_DIR?"; then
    act "rm -rf '$CTX_STATE_DIR'"
    echo "  removed"
  else
    echo "  skipped"
  fi
else
  echo "No state dir at $CTX_STATE_DIR"
fi

# ── Step 2: skill-router agent file ──────────────────────────────────────────
ROUTER="$AGENTS_DIR/skill-router.md"
if [[ -f "$ROUTER" ]]; then
  if confirm "Remove $ROUTER?"; then
    act "rm -f '$ROUTER'"
    echo "  removed"
  else
    echo "  skipped"
  fi
else
  echo "No router at $ROUTER"
fi

# ── Step 3: /ctx slash command ───────────────────────────────────────────────
SLASH="$COMMANDS_DIR/ctx.md"
if [[ -f "$SLASH" ]]; then
  if confirm "Remove $SLASH?"; then
    act "rm -f '$SLASH'"
    echo "  removed"
  else
    echo "  skipped"
  fi
else
  echo "No slash command at $SLASH"
fi

# ── Step 4: hook block in settings.json ──────────────────────────────────────
if [[ -f "$SETTINGS" ]] && [[ -f "$SRC_DIR/hook_installer.py" ]]; then
  # Detect whether any ctx-tagged entries are present before prompting.
  if grep -q '"_ctx": true\|@ctx-minimal' "$SETTINGS" 2>/dev/null; then
    if confirm "Strip ctx-tagged hook entries from $SETTINGS?"; then
      if [[ "$DRY_RUN" == 1 ]]; then
        echo "  [dry-run] would run: $PYTHON $SRC_DIR/ctx.py uninstall-hook"
      else
        "$PYTHON" "$SRC_DIR/ctx.py" uninstall-hook
      fi
    else
      echo "  skipped (tagged entries remain in settings.json)"
    fi
  else
    echo "No ctx-tagged hook entries in $SETTINGS"
  fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────
BACKUP="$SETTINGS.pre-ctx.bak"
echo
if [[ -f "$BACKUP" ]]; then
  echo "Note: $BACKUP was left in place for your audit."
  echo "      Delete it manually once you've verified settings.json."
fi
echo "Uninstall complete."
