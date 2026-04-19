#!/usr/bin/env bash
# uninstall.sh — reverse a ctx-minimal install.
#
# Default install layout (after Phase 2):
#   ~/.claude/ctx/                      — all runtime state (graph, catalog,
#                                         manifest, stack-profile, pending,
#                                         intent-log, .shown)
#   ~/.claude/agents/skill-router.md    — router agent (Phase 6)
#   ~/.claude/commands/ctx.md           — /ctx slash command (Phase 6)
#   ~/.claude/settings.json             — NOT touched by default install
#                                         (only when --with-hooks was passed;
#                                         a .pre-ctx.bak exists if so)
#
# This Phase-2 uninstall handles the ctx_home state dir. Phase 6 extends it
# with router/slash-command removal and tagged-hook-block stripping.
#
# Usage:
#   ./uninstall.sh              # interactive: ask y/N per step
#   ./uninstall.sh --yes        # non-interactive
#   ./uninstall.sh --dry-run    # print what would be removed, don't touch

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

CTX_HOME="${CTX_HOME:-$HOME/.claude/ctx}"

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
echo "  CTX_HOME:  $CTX_HOME"
echo "  dry-run:   $DRY_RUN"
echo "  assume-y:  $ASSUME_YES"
echo

if [[ ! -d "$CTX_HOME" ]]; then
  echo "Nothing to remove: $CTX_HOME does not exist."
  exit 0
fi

echo "Contents of $CTX_HOME:"
find "$CTX_HOME" -maxdepth 2 -type f | sed 's/^/  /'
echo

if confirm "Remove $CTX_HOME and all its contents?"; then
  act "rm -rf '$CTX_HOME'"
  echo "Removed: $CTX_HOME"
else
  echo "Skipped $CTX_HOME"
fi

# Phase 6 will add:
#   - remove ~/.claude/agents/skill-router.md
#   - remove ~/.claude/commands/ctx.md
#   - if settings.json.pre-ctx.bak exists and hook block present,
#     strip tagged entries (leaves .pre-ctx.bak for user to inspect/delete)
