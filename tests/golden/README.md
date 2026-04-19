# Golden samples

Reference outputs of the recommendation engine, frozen for regression
detection across distillation phases.

## Fixture corpus

After Phase 3 (`graph-from-source`), goldens are captured against the
deterministic fixture under `tests/fixtures/`:

```
tests/fixtures/skills/
  fastapi-expert/SKILL.md     tags: [python, fastapi, api, async]
  pytest-master/SKILL.md      tags: [python, testing]
  docker-expert/SKILL.md      tags: [docker, containers, devops]
  kubernetes-ops/SKILL.md     tags: [kubernetes, docker, devops, yaml]
  helm-charts/SKILL.md        tags: [kubernetes, helm, yaml, devops]
  react-ui/SKILL.md           tags: [react, typescript, frontend]
  next-expert/SKILL.md        tags: [nextjs, react, typescript, frontend]
  go-concurrency/SKILL.md     tags: [go, concurrency, performance]
tests/fixtures/agents/
  code-reviewer.md            tags: [testing, security, review]
  architect.md                tags: [architecture, design]
```

The pre-Phase-3 tarball-backed goldens (141 MB `graph.json` with ~20k
nodes) are retired because Phase 3 deletes the tarball. Going forward,
goldens are a function of this local fixture only.

## Files

| File | Generator | Inputs |
|---|---|---|
| `stack-fastapi.json` | `scan_repo.py` | `/tmp/ctx-sandbox/test-projects/fastapi-app` |
| `stack-next.json` | `scan_repo.py` | Next.js + React + TS + Tailwind fixture |
| `stack-go-k8s.json` | `scan_repo.py` | Go + k8s client-go fixture |
| `graph-fixture.json` | `wiki_graphify.py` | full graph (10 nodes, 6 edges) |
| `graph-fixture-python.json` | `resolve_graph.py` | tags `python,fastapi,api` |
| `graph-fixture-devops.json` | `resolve_graph.py` | tags `kubernetes,docker,devops` |
| `graph-fixture-frontend.json` | `resolve_graph.py` | tags `react,typescript,frontend` |
| `graph-fixture-seed-docker.json` | `resolve_graph.py` | seed `docker-expert` |

## Re-capture

```bash
# Point config at fixtures (via a tmp user config override) and run graphify
export CTX_HOME=$(mktemp -d)/ctx
mkdir -p "$CTX_HOME"
cat > ~/.claude/skill-system-config.json <<JSON
{"paths":{"skills_dir":"$PWD/tests/fixtures/skills","agents_dir":"$PWD/tests/fixtures/agents"}}
JSON

python src/wiki_graphify.py

python src/resolve_graph.py --tags python,fastapi,api --top 10 --json \
  > tests/golden/graph-fixture-python.json
# ...repeat for other seeds
```

## Phase-gate diffs

- **Phase 5 (`ctx-cli`)**: re-run via `ctx recommend` CLI wrapper, `diff`
  against these goldens. Drift outside score-tie reordering = stop condition.

Acceptable drift: score ties may reorder. **Set membership in top-10 must
match exactly.**
