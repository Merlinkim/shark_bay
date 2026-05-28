# Shark Bay Agent Guide (API-first)

This guide is a practical runbook for agents that call Shark Bay APIs for research, validation, and operations.

## Scope and Boundaries

- Shark Bay is research-only (no live order routing).
- Primary bar interval is `1m`.
- Agent outputs should be reproducible with explicit symbols, ranges, and strategy params.

## Agent Roles

### Merlin (Research and Strategy)
- Runs experiments and backtests.
- Produces recommendations from deterministic metrics.

### Arthur (Implementation and Operations)
- Maintains infra and schema compatibility.
- Handles ingestion/backfill and queue-worker health.

### Lancelot (Risk and Review)
- Reviews drawdown/overfit risk.
- Issues approvals or rejection reasons for strategy promotion.

## Required API Workflows

### 1) Data readiness gate
1. `GET /health/ready`
2. `GET /ingestion/status`
3. `GET /symbols/active`
4. If gaps detected, `POST /research/backfill/rest` with bounded window.

### 2) Research execution gate
1. `GET /research/dataset/splits` to lock evaluation windows.
2. `GET /research/experiments/run` for deterministic experiment payload.
3. `GET /research/analytics` and `GET /research/agent/recommendations`.
4. Optional replay: `POST /backtests/run` with same params.

### 3) Review and lifecycle gate
1. `POST /research/reviews` for risk verdict.
2. `POST /research/strategies/proposals` for proposal creation.
3. `PATCH /research/strategies/{strategy_id}/status` for lifecycle transition.
4. `GET /research/strategies/{strategy_id}/history` for audit trail.

## Async Backtest Jobs (for heavy runs)

1. Submit: `POST /research/jobs/backtest`
2. Poll: `GET /research/jobs/{job_id}`
3. Result fetch: `GET /research/jobs/{job_id}/result`
4. Cancel if needed: `POST /research/jobs/{job_id}/cancel`

## Prompt Template (Agent Task)

Use this template when assigning API-driven research tasks:

```text
Goal:
- Validate strategy {strategy_id} on {symbol} {interval} with deterministic windows.

Inputs:
- symbol={symbol}
- interval=1m
- start={iso8601}
- end={iso8601}
- params={json}

Required API sequence:
1) /health/ready -> /ingestion/status -> /symbols/active
2) /research/dataset/splits -> /research/experiments/run
3) /research/analytics -> /research/agent/recommendations
4) /research/reviews (risk verdict and reasons)

Output contract:
- Include dataset boundary, config hash/fingerprint (if available), key metrics, risk verdict, and next action.
```

## MCP Filesystem Setup

If agents need direct repository context, configure MCP with the workspace path:

```json
"shark-bay-code": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/merlin/code/shark_bay"]
}
```

## Related Docs

- `docs/project_structure_graph.md`
- `docs/research_api_reference.md`
- `docs/codebase_whitepaper.md`
- `docs/agent_debugging.md`
