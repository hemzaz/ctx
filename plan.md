# ctx-minimal — Distillation Plan

Goal: extract the skill/agent recommendation engine from `ctx` into a minimal,
read-only-by-default tool with a single command surface and a one-directory
footprint under `~/.claude/ctx/`. Nothing touches user skills, user agents, or
`settings.json` without explicit opt-in.

Non-goal: the wiki-as-memory system, the toolbox/council system, the micro-skill
pipeline converter, the backup mirror, the memory anchor, skill health healing.
These are adjacent features that bloat install-time blast radius without making
recommendations sharper.

---

## 1. Current repo audit

The recommendation engine is ~2.3k LOC buried in ~13.7k LOC.

### Keep (9 files, ~2.3k LOC)

| File | LOC | Purpose |
|---|---|---|
| `src/scan_repo.py` | 518 | Stack detection from project files |
| `src/resolve_skills.py` | 429 | Score skills against stack |
| `src/resolve_graph.py` | 187 | Graph walk for related skills |
| `src/catalog_builder.py` | 227 | Scan skill dirs → catalog |
| `src/wiki_graphify.py` | 335 | Build graph.json from tags |
| `src/context_monitor.py` | 323 | PostToolUse hook — **opt-in, not default** |
| `src/skill_suggest.py` | 131 | Surface suggestions to Claude — **opt-in, not default** |
| `src/skill_loader.py` | 193 | On-approval loader |
| `src/ctx_config.py` + `src/wiki_utils.py` | 232 | Config + frontmatter parser |

### Delete (30+ files, ~11k LOC)

- Skill mutators (high blast radius): `batch_convert.py`, `skill_transformer`
  config section, `flatten_agents.py`, `skill_add.py`, `skill_add_detector.py`,
  `link_conversions.py`.
- Adjacent features (separate concerns): `memory_anchor.py`, `backup_mirror.py`,
  `skill_health.py`.
- Toolbox system: `council_runner.py`, `toolbox.py`, `toolbox_config.py`,
  `toolbox_hooks.py`, `toolbox_verdict.py`, `behavior_miner.py`,
  `intent_interview.py`.
- Wiki scaffolding (not needed for recommendations): `wiki_visualize.py`,
  `wiki_lint.py`, `wiki_query.py`, `wiki_orchestrator.py`,
  `wiki_batch_entities.py`, `wiki_sync.py`.
- Optional telemetry: `usage_tracker.py`, `skill_unload.py`, `skill_telemetry.py`.
- Repo-specific: `import_strix_skills.py`, `update_repo_stats.py`,
  `versions_catalog.py`, `embedding_backend.py`.

### Blast-radius audit of retained modules

| Module | Writes | Risk |
|---|---|---|
| `catalog_builder.py` | `~/.claude/skill-wiki/catalog.md` | Redirect to `~/.claude/ctx/catalog.json` |
| `wiki_graphify.py` | `~/.claude/skill-wiki/graphify-out/graph.json` | Redirect to `~/.claude/ctx/graph.json` |
| `context_monitor.py` | `~/.claude/intent-log.jsonl`, `pending-skills.json` | Redirect to `~/.claude/ctx/*` |
| `skill_suggest.py` | `~/.claude/.skill-suggest-shown` | Redirect to `~/.claude/ctx/.shown` |
| `skill_loader.py` | `~/.claude/skill-manifest.json` | Redirect to `~/.claude/ctx/manifest.json` |
| `inject_hooks.py` | `~/.claude/settings.json` | **Replace** with tagged-block + backup (see §3) |
| `resolve_skills.py` | — | Drop wiki override path; use catalog only |
| `scan_repo.py` | stack-profile tmp | Redirect to `~/.claude/ctx/stack-profile.json` |

**Verdict:** every retained module can be sandboxed. Nothing in the kept
set writes under `~/.claude/skills/` or `~/.claude/agents/`.

---

## 2. Target structure

```
ctx-minimal/
├── src/
│   ├── ctx_config.py        # trimmed config (no transformer, no babysitter)
│   ├── config.json          # trimmed defaults
│   ├── wiki_utils.py        # parse_frontmatter, validate_skill_name
│   ├── scan_repo.py         # stack detection
│   ├── catalog_builder.py   # → ~/.claude/ctx/catalog.json
│   ├── wiki_graphify.py     # → ~/.claude/ctx/graph.json (reads SKILL.md tags direct)
│   ├── resolve_skills.py    # scoring (wiki-override path stripped)
│   ├── resolve_graph.py     # graph walk
│   ├── context_monitor.py   # hook (optional, read-only to skills)
│   ├── skill_suggest.py     # hook output to Claude
│   ├── skill_loader.py      # on user approval
│   └── ctx.py               # NEW: single CLI entrypoint
├── skills/
│   └── skill-router/        # the router agent definition
├── install.sh               # phased, --dry-run, --yes, --no-hooks
├── uninstall.sh             # atomic removal
├── README.md                # rewritten to match minimal surface
└── plan.md
```

State layout after install:

```
~/.claude/ctx/
├── catalog.json              # filesystem index of all skills/agents
├── graph.json                # tag-cooccurrence graph
├── stack-profile.json        # last scan result
├── manifest.json             # loaded-this-session state (replaces skill-manifest.json)
├── pending.json              # current suggestion (replaces pending-skills.json)
├── intent-log.jsonl          # hook telemetry
└── .shown                    # per-session de-dup flag
```

`settings.json.pre-ctx.bak` lives alongside `~/.claude/settings.json` only if
hooks were installed.

---

## 3. Structural changes

### 3.1 Single state directory

Every path in `config.json` moves under `~/.claude/ctx/`. Uninstall becomes
`rm -rf ~/.claude/ctx/` + optional settings restore. Nothing scattered.

### 3.2 Graph builder reads SKILL.md directly

Current `wiki_graphify.py` depends on the entity-page pipeline
(`wiki_batch_entities.py` writes `~/.claude/skill-wiki/entities/skills/*.md`,
then `wiki_graphify.py` reads them). Change it to walk `~/.claude/skills/**/SKILL.md`
and `~/.claude/agents/**.md`, extract tags from frontmatter, build the graph
in one pass. Eliminates:

- The 8.9 MB pre-built tarball (`graph/wiki-graph.tar.gz`).
- The 159 MB expanded wiki.
- Two install phases (entity generation, graph build).
- A whole class of drift (entity pages going stale vs. SKILL.md source).

### 3.3 Hook installation is opt-in, not default

**Default install does not touch `~/.claude/settings.json` at all.** The primary
user-facing surface is the `/ctx` slash command (see §3.5) invoked on demand.
Live mid-session monitoring (`context_monitor.py` + `skill_suggest.py`) is an
optional power-user feature, installed only when the user explicitly runs
`ctx install-hook`.

Replace `inject_hooks.py` with three CLI subcommands:

- `ctx print-hook` — emits the JSON block to stdout. Never writes. Default
  advice in README is to paste it yourself.
- `ctx install-hook` — opt-in mutator. Performs the surgical edit described in
  §3.7 against `~/.claude/settings.json`. Makes a one-time
  `settings.json.pre-ctx.bak`. Idempotent: re-running is a no-op.
- `ctx uninstall-hook` — strips exactly the entries `install-hook` added
  (identified by three-layer markers: `_ctx: true` + command path prefix +
  shell-comment suffix).

See §3.7 for the mutation recipe.

### 3.4 Read-only enforcement

Add `"read_only": true` to `config.json`. When set:

- `catalog_builder.py`, `wiki_graphify.py`, `scan_repo.py` — unaffected
  (they only read skills/agents).
- `skill_loader.py` — still writes, but only to `~/.claude/ctx/manifest.json`.
- Any future mutator path guards on this flag.

Grep-enforced contract: **no writer may open a file under
`~/.claude/skills/**` or `~/.claude/agents/**`**. CI check on the fork
greps for these paths in `open(`, `write_text`, `replace(` calls.

### 3.5 Primary entry: `/ctx` slash command + CLI

User-facing surface is a slash command `/ctx` (shipped as a Claude Code
slash-command file at `~/.claude/commands/ctx.md` or equivalent), which under
the hood invokes `ctx recommend --project $PWD`. This makes suggestions
**on-demand** rather than hook-driven: the user types `/ctx` when they want
recommendations, and nothing runs otherwise.

Under the slash command sits `src/ctx.py` with argparse subcommands:

| Command | Behavior |
|---|---|
| `ctx recommend [--project P] [--top N] [--json]` | scan → catalog-check → resolve → graph-walk → print top N |
| `ctx refresh` | rebuild catalog.json + graph.json |
| `ctx show-pending` | dump `pending.json` |
| `ctx load <name>[,<name>...]` | user-approved load (what `skill_loader.py` does) |
| `ctx install-hook` | **opt-in** surgical edit to settings.json (see §3.7) |
| `ctx uninstall-hook` | strip tagged block |
| `ctx print-hook` | emit snippet to stdout; don't touch settings.json |
| `ctx doctor` | report state dir contents, graph node count, last refresh |

Eliminates the multi-command dance in today's README. No hooks required for
the default flow.

### 3.6 Install script is phased and confirmed

```
./install.sh                 # interactive: each phase asks y/N
./install.sh --yes           # non-interactive, no hooks
./install.sh --dry-run       # print every write that would happen
./install.sh --with-hooks    # opt-in: run install-hook in the final phase
./uninstall.sh               # atomic: rm -rf ~/.claude/ctx/ + strip hook block if present
```

Default install touches: `~/.claude/ctx/` (new dir),
`~/.claude/agents/skill-router.md` (one file), `~/.claude/commands/ctx.md` (one
slash-command file). That's it. `settings.json` is untouched unless
`--with-hooks` is passed.

Phases:
1. `mkdir -p ~/.claude/ctx` — ask.
2. `python3 src/ctx.py refresh` — builds `catalog.json` + `graph.json`. No
   side effects outside `~/.claude/ctx/`.
3. Copy `skills/skill-router/SKILL.md` → `~/.claude/agents/skill-router.md`
   (single file). Ask.
4. Write `/ctx` slash command file to `~/.claude/commands/ctx.md`. Ask.
5. (Only if `--with-hooks`) `python3 src/ctx.py install-hook`. Ask y/N even
   so.
6. Print uninstall instructions + backup path.

### 3.7 Surgical settings.json mutation recipe

This is the only write to `~/.claude/settings.json` the tool ever performs,
and only when the user explicitly asks for it. Design requirements:

- **Lossless to unrelated keys**: only touch the `hooks` key; leave
  everything else byte-identical where possible.
- **Idempotent**: re-running must be a no-op, not a double-insert.
- **Reversible**: uninstall must strip exactly what install added, nothing
  more.
- **Atomic**: a crash mid-write leaves the file intact.
- **Refuse on ambiguity**: if the file doesn't parse, or if existing tagged
  entries don't match expected shape, refuse and point at the backup.

#### Three-layer marker

Every entry inserted carries three independent markers so it can be
identified even after users manually edit the file:

1. **JSON key**: `"_ctx": true` on the entry dict.
2. **Command path prefix**: every command starts with
   `$CTX_HOME/src/` (resolved to the install dir).
3. **Shell-comment suffix**: every command string ends with ` # @ctx-minimal`
   (valid shell, survives JSON round-trips through other editors).

Stripping matches if *any* of the three is present, so one accidentally
deleted marker still leaves identifiable entries.

#### Write protocol

```python
# Pseudocode — actual implementation in src/hook_installer.py
def install_hook(settings_path: Path, entries: list[dict]) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Advisory lock the target (prevents races with other hook tools)
    with open(settings_path, "a+") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)

        # 2. Read current contents
        original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
        try:
            settings = json.loads(original) if original.strip() else {}
        except json.JSONDecodeError as e:
            sys.exit(f"refusing to write: {settings_path} is invalid JSON ({e})")

        if not isinstance(settings, dict):
            sys.exit("refusing to write: settings.json is not a JSON object")

        # 3. One-time backup (never overwrite)
        backup = settings_path.with_suffix(settings_path.suffix + ".pre-ctx.bak")
        if not backup.exists() and original:
            backup.write_text(original, encoding="utf-8")

        # 4. Ensure hooks dict
        hooks = settings.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            sys.exit("refusing to write: settings.hooks is not a JSON object")

        # 5. For each event: strip existing ctx entries, append fresh tagged ones
        for event, new_entries in entries_by_event(entries).items():
            existing = hooks.get(event, [])
            if not isinstance(existing, list):
                sys.exit(f"refusing to write: settings.hooks.{event} is not a list")

            pruned = [e for e in existing if not _is_ctx_entry(e)]
            tagged = [_apply_markers(e) for e in new_entries]
            hooks[event] = pruned + tagged

        # 6. Re-serialize and validate round-trip
        new_text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
        try:
            json.loads(new_text)
        except json.JSONDecodeError:
            sys.exit(f"ctx produced invalid JSON; backup at {backup}")

        # 7. Atomic write via tempfile + os.replace
        fd, tmp = tempfile.mkstemp(
            prefix=settings_path.name + ".",
            suffix=".tmp",
            dir=str(settings_path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp, settings_path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise


def _is_ctx_entry(entry: object) -> bool:
    """Match any of the three markers."""
    if not isinstance(entry, dict):
        return False
    if entry.get("_ctx") is True:
        return True
    for cmd in _all_commands(entry):
        if "# @ctx-minimal" in cmd:
            return True
        if cmd.lstrip().startswith(f"python3 \"{CTX_HOME}/src/"):
            return True
    return False


def _apply_markers(entry: dict) -> dict:
    e = dict(entry)
    e["_ctx"] = True
    # append shell comment to every command string in the entry
    ...
    return e
```

#### Uninstall protocol

Symmetric: load settings, filter `hooks[event]` to drop any `_is_ctx_entry`,
drop empty `hooks[event]` lists, drop empty `hooks` dict. Re-serialize,
validate, atomic-write. Leaves `settings.json.pre-ctx.bak` in place — user
chooses whether to `rm` it.

#### What could still go wrong

| Failure | Mitigation |
|---|---|
| User edits `settings.json` between install and uninstall, breaks JSON | Uninstall refuses, points at backup |
| User installs a different tool's hooks that also use `_ctx` | Very low probability; path-prefix and shell-comment markers still identify ours |
| Claude Code adds a new `hooks[event]` entry shape we don't recognize | We never touch non-ctx entries, so unknown shapes pass through |
| `os.replace` fails across filesystems | Tempfile is created in the same directory as target — same filesystem guaranteed |
| Concurrent hook installers race | `fcntl.flock` serializes; Windows fallback is a `.lock` sentinel file |
| User's `settings.json` has trailing bytes / BOM | `json.loads` will tolerate or error cleanly; no silent corruption |

This recipe is the entirety of `settings.json` manipulation in the tool.
No other code path writes to it.

---

## 4. Work plan (branches, in order)

Each phase is a PR-sized branch. Every branch must end green (engine still
runs end-to-end) before merging into the fork's `main`.

### Phase 1 — `minimal`: prune
- Delete the 30+ files in §1 "Delete".
- Trim `ctx_config.py`: drop `skill_transformer`, `skill_router`, `babysitter`
  sections.
- Trim `config.json` accordingly.
- Remove dead imports. Grep for orphan references.
- Verify: `scan_repo.py` + `catalog_builder.py` + `wiki_graphify.py` +
  `resolve_skills.py` + `resolve_graph.py` all still run on a sample skills
  dir.

Exit criteria: repo is ~3k LOC, nothing broken.

### Phase 2 — `ctx-sandbox`: relocate state
- Update `config.json` paths to `~/.claude/ctx/*`.
- Update `ctx_config.py` defaults.
- Touch every hardcoded path in the 9 retained modules.
- `uninstall.sh` works: `rm -rf ~/.claude/ctx/`.

Exit criteria: running the engine leaves no trace outside `~/.claude/ctx/`.

### Phase 3 — `graph-from-source`: drop entity-page dependency
- Rewrite `wiki_graphify.py` to walk SKILL.md files directly.
- Delete the pre-built `graph/wiki-graph.tar.gz` from the repo.
- Verify graph topology roughly matches the old one on a test skills dir.

Exit criteria: `ctx refresh` builds `graph.json` in one step from source of
truth; no more pre-built tarball in version control.

### Phase 4 — `readonly-default`: enforce + hooks-are-opt-in
- Add `read_only` flag (default true) to `config.json`.
- Add `enable_live_suggestions: false` flag; `context_monitor.py` and
  `skill_suggest.py` are no-ops when false.
- Add a CI/local check: grep the source for writes under `~/.claude/skills/`
  or `~/.claude/agents/`. Must return zero hits.
- Rework `inject_hooks.py` into `install-hook` / `uninstall-hook` /
  `print-hook` per §3.3 + §3.7 surgical recipe. Three-layer marker
  (`_ctx: true` + path prefix + shell comment). One-time backup. Atomic
  write. Advisory lock.
- Write fixture tests in `tests/test_hook_installer.py`: install → verify
  backup created, install again → no double-insert, uninstall → clean
  diff vs backup.

Exit criteria: engine provably cannot mutate user skills or agents. Default
install does not touch `settings.json`. `install-hook`/`uninstall-hook`
round-trip is clean on a fixture.

### Phase 5 — `ctx-cli`: unify command surface
- Add `src/ctx.py` with the subcommands in §3.5.
- Deprecate direct module invocation in the README.
- Keep modules importable for advanced users.

Exit criteria: one command does the thing.

### Phase 6 — `minimal-install`: dry-run and confirmations
- Rewrite `install.sh` with `--dry-run`, `--yes`, `--with-hooks`.
  Default does not touch `settings.json`.
- Write `/ctx` slash command file to `~/.claude/commands/ctx.md` during
  install (it shells out to `python3 $CTX_HOME/src/ctx.py recommend
  --project $CLAUDE_PROJECT_DIR`).
- Write `uninstall.sh`: atomic `rm -rf ~/.claude/ctx/`, remove
  `~/.claude/agents/skill-router.md` and `~/.claude/commands/ctx.md`, and
  only strip hook block if present. Leaves `.pre-ctx.bak` for user.
- Rewrite README against the new surface: `/ctx` first, CLI second, hooks
  last (opt-in).

Exit criteria: install is reversible, auditable, and phased. Default install
is hook-free.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `settings.json` write corrupts user config | Atomic tempfile + `os.replace`, pre-write backup, tagged block only, refuse on JSON parse failure. Default to `print-hook` (no write). |
| `networkx` dependency (~30 MB) | Document in README. No lighter library gives the same graph-walk API. |
| Stale graph after user adds a skill | `ctx refresh` is cheap (one filesystem walk). Optional PostToolUse hook enqueues a rebuild on Write-to-SKILL.md. |
| Tag taxonomy drift | `catalog_builder.py` collects observed tags; `resolve_graph.py` accepts any tag present in the graph. No hardcoded taxonomy gate. |
| Skill-router agent expects full wiki | Router is a markdown agent definition — update its prompts to call `ctx recommend` instead of the old multi-step flow. |

---

## 6. Success criteria

- **Default install touches only three files/dirs**: `~/.claude/ctx/` (new
  dir), `~/.claude/agents/skill-router.md` (one file),
  `~/.claude/commands/ctx.md` (one file).
- **`settings.json` is not written by default.** Only written when user runs
  `install.sh --with-hooks` or `ctx install-hook` explicitly, and then only
  via the §3.7 surgical recipe with backup.
- Uninstall is one command.
- No SKILL.md or agent .md in `~/.claude/` is modified, ever, by any code
  path in this repo.
- `/ctx` slash command works from any project and returns sensible top-10 in
  < 2 seconds.
- `ctx recommend` CLI has feature parity with the slash command.
- `ctx install-hook` → `ctx uninstall-hook` round-trip leaves `settings.json`
  byte-identical to the pre-install state (modulo JSON re-serialization
  whitespace).
- Repo is ≤ 3.5k LOC excluding the router agent markdown.

---

## 7. Answered decisions (formerly open questions)

1. **Skill-router placement.** Single file at
   `~/.claude/agents/skill-router.md`. No directory, no dual-write. If the
   router needs references, inline them or have the router call `ctx`
   subcommands.
2. **Hooks vs on-demand.** On-demand is the default. `/ctx` slash command is
   the primary surface; it invokes `ctx recommend --project $PWD`. Live
   mid-session monitoring (PostToolUse hook) is opt-in behind both
   `enable_live_suggestions: false` config flag **and** explicit
   `ctx install-hook` / `install.sh --with-hooks`. Default install never
   touches `settings.json`.
3. **Edge weighting.** Keep current **shared-tag-count** scheme (weight =
   |tags(a) ∩ tags(b)|). This is neither truly flat nor TF-IDF; it's the
   simplest scheme that still ranks by shared-tag count. TF-IDF/rarity
   weighting is a better recommendation signal but adds tag document
   frequency tracking and cold-start tuning — deferred to a post-v1 phase
   if recommendation quality is poor on real skill libraries.
