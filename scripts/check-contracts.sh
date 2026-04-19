#!/usr/bin/env bash
# check-contracts.sh — enforce ctx-minimal's write-scope contract.
#
# Hard constraint (plan.md §Hard constraints #1):
#   No code path in src/ may open a file under ~/.claude/skills/** or
#   ~/.claude/agents/** for writing.
#
# This script greps the src/ tree for any pattern that could write to those
# locations and exits non-zero on the first hit. Wire into CI + pre-commit
# hook in Phase 6.
#
# Exit codes:
#   0 — clean
#   1 — contract violation found

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Patterns that indicate a write sink combined with a skills/agents path.
# We grep for open(..., 'w'), .write_text(, shutil.copy, os.replace(...)
# where either the path string literal mentions .claude/skills or .claude/agents.
#
# A cleaner enforcement is two-pronged: grep for path strings and grep for
# write sinks; a violation is co-occurrence in the same file. We do the
# path-pattern grep first (path strings are rarer) and then narrow to
# writer lines.

# Allow-list of paths that legitimately reference these dirs (read-only).
# These files are read-scoped by inspection; if any starts writing, this
# allow-list must be pruned.
ALLOW_GREP_TARGETS=(
  "src/catalog_builder.py"   # scans SKILL.md files (reads only)
  "src/wiki_graphify.py"     # scans SKILL.md files (reads only)
  "src/scan_repo.py"         # scans caller's project, not ~/.claude
  "src/resolve_skills.py"    # scans SKILL.md metadata (reads only)
  "src/skill_loader.py"      # READS SKILL.md to return its path to Claude
  "src/ctx_config.py"        # stores paths as Path objects
  "src/hook_installer.py"    # writes settings.json only, never skills/agents
)

VIOLATIONS=0

# Step 1: every file mentioning .claude/skills or .claude/agents must be in
# the allow-list (it's then manually audited to be read-only) OR must not
# contain a write sink on the same line or within a small window.

# Exclude src/tests/ — test fixtures legitimately reference these paths as
# setup strings; what matters is that no production module writes there.
matches=$(grep -rnE "\.claude/(skills|agents)" src/ --include="*.py" --exclude-dir="tests" || true)

if [[ -n "$matches" ]]; then
  while IFS= read -r line; do
    file="${line%%:*}"
    rest="${line#*:}"
    # Skip if file is on the allow-list
    allowed=0
    for a in "${ALLOW_GREP_TARGETS[@]}"; do
      if [[ "$file" == "$a" ]]; then allowed=1; break; fi
    done
    if [[ "$allowed" == 1 ]]; then continue; fi

    # File is NOT allow-listed → any mention of these paths is suspect.
    echo "VIOLATION: $line"
    VIOLATIONS=$((VIOLATIONS + 1))
  done <<< "$matches"
fi

# Step 2: within allow-listed files, grep for writer patterns directly
# adjacent to the skills/agents path. These are strong signals of a write.
WRITE_PATTERNS='(open\([^)]*["'\''][^"'\'']*\.claude/(skills|agents)[^"'\'']*["'\''][^)]*["'\'']w["'\'']|write_text\([^)]*\.claude/(skills|agents)|shutil\.(copy|copyfile|move)\([^)]*\.claude/(skills|agents)|os\.replace\([^)]*,[^)]*\.claude/(skills|agents))'
writer_hits=$(grep -rnE "$WRITE_PATTERNS" src/ --include="*.py" --exclude-dir="tests" || true)
if [[ -n "$writer_hits" ]]; then
  echo ""
  echo "WRITER VIOLATIONS:"
  echo "$writer_hits"
  VIOLATIONS=$((VIOLATIONS + 1))
fi

if [[ "$VIOLATIONS" -gt 0 ]]; then
  echo ""
  echo "contract check: FAIL ($VIOLATIONS violation(s))"
  exit 1
fi

echo "contract check: PASS (no writes under ~/.claude/skills or ~/.claude/agents)"
exit 0
