# Golden samples

Frozen outputs of the recommendation engine at the `minimal` branchpoint,
captured before Phase 1 pruning. These are the reference baseline the plan
mandates (plan.md §"Testing sandbox").

## Files

| File | Generator | Seeds |
|---|---|---|
| `stack-fastapi.json` | `scan_repo.py` | fixture: `/tmp/ctx-sandbox/test-projects/fastapi-app` (pyproject + FastAPI + Dockerfile) |
| `stack-next.json` | `scan_repo.py` | fixture: Next.js + React + TS + Tailwind |
| `stack-go-k8s.json` | `scan_repo.py` | fixture: Go module + k8s client-go + Dockerfile |
| `graph-fastapi.json` | `resolve_graph.py` | tags: `python,api,fastapi` |
| `graph-next.json` | `resolve_graph.py` | tags: `react,typescript,frontend` |
| `graph-go-k8s.json` | `resolve_graph.py` | tags: `kubernetes,docker,go` |

Captured on branch `minimal` at HEAD commit `fix(compat): explicit edges=...`
against networkx 3.6.1 + the pre-built `graph/wiki-graph.tar.gz`.

## Re-capture

```bash
# In repo root, with .venv activated
export HOME=/tmp/ctx-sandbox  # sandbox with graph.json symlinked
python src/scan_repo.py --repo $HOME/test-projects/fastapi-app --output tests/golden/stack-fastapi.json
python src/resolve_graph.py --tags python,api,fastapi --top 10 --json > tests/golden/graph-fastapi.json
# ...etc
```

## Phase-gate diffs

Per plan.md:

- End of Phase 3 (`graph-from-source`): re-run generators, `diff` against
  these goldens. Top-10 set should match modulo tie-break ordering. Large
  drift = stop condition.
- End of Phase 5 (`ctx-cli`): re-run via `ctx recommend` CLI wrapper,
  same diff.

Acceptable drift: score ties may reorder. Set membership in top-10 must
match exactly.
