# ctx-minimal

A minimal, read-only-by-default skill and agent **recommendation engine**
for Claude Code. Distilled from [stevesolun/ctx](https://github.com/stevesolun/ctx)
into ~3k LOC that does one thing: given your installed skills and agents
plus a project directory, tell you which ones to load.

## Why

Claude Code skills and agents scale poorly. With hundreds installed, you
can't know which ones apply to the project in front of you. ctx-minimal
builds a graph over `~/.claude/skills/` and `~/.claude/agents/` from their
tag frontmatter, then walks it from signals detected in your repo.

No wiki. No micro-skill converter. No auto-loading. No hook mutation by
default. You ask `/ctx`, it recommends, you choose.

## Hard contracts

1. **No writes under `~/.claude/skills/` or `~/.claude/agents/`**, ever.
   Enforced by `scripts/check-contracts.sh`.
2. **No writes to `~/.claude/settings.json` except through the tagged-block
   installer.** The installer makes a one-time backup and is fully
   reversible via matching `uninstall-hook`.
3. **All runtime state under one directory**: `~/.claude/ctx/` (or
   `$CTX_HOME`). Uninstall is `rm -rf`.

## Quickstart

```bash
git clone https://github.com/hemzaz/ctx && cd ctx
./install.sh
```

The installer touches only three locations:

| Path | Contents |
|---|---|
| `~/.claude/ctx/` | `catalog.json`, `graph.json`, per-session state |
| `~/.claude/agents/skill-router.md` | router agent definition |
| `~/.claude/commands/ctx.md` | `/ctx` slash command |

It does **not** touch `settings.json` unless you pass `--with-hooks`.

## Using it

In a Claude Code session:

```
/ctx
```

The slash command runs `ctx recommend --project .` and prints a ranked
list of skills/agents from your installed library. You choose which (if
any) to load; the tool never loads anything without your approval.

From the shell:

```bash
python src/ctx.py recommend --project . --top 10
python src/ctx.py refresh           # rebuild catalog + graph
python src/ctx.py doctor            # state dir health report
python src/ctx.py print-hook        # show the hook snippet (no write)
python src/ctx.py install-hook      # opt-in: tagged block into settings.json
python src/ctx.py uninstall-hook    # remove tagged block
```

## Config

Defaults in `src/config.json`. Override per-user at
`~/.claude/skill-system-config.json` (deep-merged) or via `$CTX_HOME`
env var (wins over config for state root).

| Key | Default | Effect |
|---|---|---|
| `paths.ctx_home` | `~/.claude/ctx` | where state lives |
| `paths.skills_dir` | `~/.claude/skills` | where skills are read from |
| `paths.agents_dir` | `~/.claude/agents` | where agents are read from |
| `read_only` | `true` | contract marker (grep-checked) |
| `enable_live_suggestions` | `false` | gate for PostToolUse monitoring |
| `resolver.max_skills` | `15` | per-session load cap |
| `line_threshold` | `180` | informational flag in catalog |

## Repository layout

```
src/
  ctx.py               # CLI entrypoint (recommend/refresh/doctor/install-hook)
  scan_repo.py         # project → stack profile
  resolve_skills.py    # stack profile → scored skill manifest
  resolve_graph.py     # graph walk from matched seeds or tags
  catalog_builder.py   # SKILL.md/agents/*.md → catalog.json
  wiki_graphify.py     # tag frontmatter → graph.json
  context_monitor.py   # PostToolUse hook (no-op unless live_suggestions)
  skill_suggest.py     # PostToolUse surface to Claude (same gate)
  skill_loader.py      # on user approval, load skill into manifest
  hook_installer.py    # surgical settings.json tagged-block install/uninstall
  ctx_config.py        # config singleton (honors CTX_HOME)
  wiki_utils.py        # frontmatter parser
  tests/               # pytest suite (170+ tests)
commands/
  ctx.md               # /ctx slash command template
skills/
  skill-router/        # router agent shipped with the tool
scripts/
  check-contracts.sh   # grep-enforced no-write-to-skills/agents contract
tests/
  fixtures/            # deterministic skill/agent corpus
  golden/              # frozen outputs for phase-gate diffs
install.sh             # phased installer (--dry-run, --yes, --with-hooks)
uninstall.sh           # atomic teardown
plan.md                # the distillation plan this repo implements
```

## How `settings.json` is edited (when you opt in)

When you run `ctx install-hook` (or `./install.sh --with-hooks`):

1. `fcntl.flock` serializes the mutation.
2. `settings.json.pre-ctx.bak` is written **once** and never overwritten.
3. Every inserted entry carries three markers — `"_ctx": true`, a
   path-prefix (`<ctx-src>/`), and a shell-comment suffix
   (` # @ctx-minimal`). Any one marker is sufficient for `uninstall-hook`
   to identify and strip it.
4. The new JSON is round-trip validated before writing.
5. Write goes to a tempfile in the same directory, then `os.replace`.
6. On parse failure, non-object settings, or non-dict hooks → refuses
   and points you at the backup.

`ctx uninstall-hook` runs the same sequence in reverse: lock, read,
filter tagged entries, drop empty dicts, round-trip validate, atomic
write. Leaves `.pre-ctx.bak` for your audit.

## Uninstall

```bash
./uninstall.sh        # interactive
./uninstall.sh --yes  # non-interactive
```

Removes `~/.claude/ctx/`, the router file, the slash command, and
(if present) the tagged hook block. **Leaves** `settings.json.pre-ctx.bak`
so you can diff before deleting it manually.

## License

MIT. See [LICENSE](LICENSE).

## Differences from upstream

This fork removes: the wiki/memory subsystem, the skill-transformer
(`batch_convert.py`), the toolbox/council system, the backup mirror, the
memory anchor, skill-health auto-healing, `flatten_agents`, and several
thousand lines of other adjacent scaffolding. What remains is the graph
+ scoring engine plus a reversible installer. See [`plan.md`](plan.md)
for the phase-by-phase distillation plan.
