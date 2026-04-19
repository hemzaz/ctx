---
description: Scan the current project and recommend the most relevant skills and agents from your installed library.
---

Run ctx-minimal against the current project and return the top-10 most
relevant skill/agent recommendations.

Steps:

1. Invoke `ctx recommend --project "$CLAUDE_PROJECT_DIR"` via Bash. Prefer the
   installed shim at `$HOME/.claude/ctx/bin/ctx` if present; otherwise fall
   back to `python3 $HOME/.claude/ctx/src/ctx.py`.
2. Report the ranked list to the user verbatim (or summarise if long). Do NOT
   auto-load anything.
3. Ask the user which suggestions (if any) they want to load. Only after
   explicit approval, invoke `ctx load <name>[,<name>]` for the chosen items.
4. If `ctx recommend` reports "graph not found", run `ctx refresh` first and
   retry.

Arguments:

- `$ARGUMENTS` — optional extra tags or a project subpath. Pass through
  unchanged if present.

Non-goals:

- Do not install hooks, edit settings.json, or modify any files under
  `~/.claude/skills/` or `~/.claude/agents/`.
- Do not load suggestions without user approval.
