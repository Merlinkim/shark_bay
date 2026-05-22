# Missing Research API Analysis (Research-Only Scope)

## Scope Guardrails
This analysis excludes trading, exchange order routing, portfolio management, and execution APIs. Focus is strictly research/experiments/analytics/lineage/validation/auditability.

## Agent Usage Analysis
### Arthur
- Heavy APIs: `/ingestion/status`, `/ingestion/telemetry`, `/research/backfill/rest`, `/ops/*`, `/metrics`.
- Pattern: diagnose lag/gaps, run bounded backfills, verify recovery.
- Dangerous pattern: repeated wide-range backfill without dry-run.
- Safeguard: require `dry_run=true` first and enforce max window policy.

### Merlin
- Heavy APIs: `/research/features`, `/research/analytics`, `/research/agent/recommendations`, `/research/experiments/latest`.
- Pattern: hypothesis generation + strategy proposal refinement.
- Dangerous pattern: overfitting on tiny lookbacks.
- Safeguard: minimum sample-size validation endpoint.

### Galahad
- Heavy APIs: `/research/experiments/run`, `/research/walk-forward/run`, `/research/dataset/splits`, backtest endpoints.
- Pattern: validate robustness across regimes/windows.
- Dangerous pattern: parameter mining without lineage trace.
- Safeguard: immutable mutation-trace API.

### Lancelot
- Heavy APIs: `/strategies/registry`, `/research/experiments/*`, `/research/analytics`.
- Pattern: governance/review of research candidates.
- Dangerous pattern: approving based on single metric.
- Safeguard: checklist + audit report API requirements.

## Missing APIs

1) **Experiment Comparison API** (Priority: High, Complexity: Medium)
- Why: direct side-by-side comparison is central for research selection.
- Workflow: submit N experiment IDs, receive normalized metric table + deltas.
- Proposed: `POST /research/experiments/compare`.
- Scaling: compare fanout may require materialized summary cache.

2) **Experiment Lineage API** (High, Medium)
- Why: track parent/child derivations and parameter evolution.
- Workflow: fetch lineage graph for experiment ID.
- Proposed: `GET /research/experiments/{id}/lineage`.
- Scaling: graph depth and branching require indexed edge table.

3) **Mutation Tracking API** (High, Medium)
- Why: reproducibility needs explicit mutation logs.
- Workflow: append mutation event when params/features/split change.
- Proposed: `POST /research/experiments/{id}/mutations`, `GET .../mutations`.
- Scaling: append-only event volume; partition by date.

4) **Regime Summary API** (Medium, Low)
- Why: strategy suitability by regime is a core quant workflow.
- Proposed: `GET /research/analytics/regimes?symbol=&interval=&window=`.

5) **Drawdown Profile API** (High, Medium)
- Why: max DD alone hides pain duration/recovery.
- Proposed: `GET /research/experiments/{id}/drawdown-profile`.

6) **Feature Correlation / Drift API** (High, High)
- Why: identify unstable predictors and leakage.
- Proposed: `GET /research/features/correlation` + `GET /research/features/drift`.
- Scaling: compute heavy; likely async job + cached artifacts.

7) **Walk-Forward Summary Index API** (Medium, Low)
- Why: compare many WFA runs quickly.
- Proposed: `GET /research/walk-forward/summaries?strategy=&symbol=&limit=`.

8) **Deterministic Snapshot API** (High, High)
- Why: freeze exact dataset/hash/config for reruns.
- Proposed: `POST /research/snapshots`, `GET /research/snapshots/{id}`.

9) **Audit Report API** (High, Medium)
- Why: formal research gatekeeping and traceability.
- Proposed: `POST /research/audits/generate`, `GET /research/audits/{id}`.

10) **Strategy Review Lifecycle API** (Medium, Medium)
- Why: move from idea -> validated -> approved research states.
- Proposed: `POST /research/strategy-reviews`, `PATCH /research/strategy-reviews/{id}`.

11) **Research Proposal Store API** (Medium, Low)
- Why: preserve hypotheses before experiments to reduce hindsight bias.
- Proposed: `POST /research/proposals`, `GET /research/proposals`.

12) **Experiment Tagging/Search API** (Medium, Medium)
- Why: discoverability across growing experiment corpus.
- Proposed: `GET /research/experiments/search?q=&tags=&author=&date_from=`.

## Ingestion Scaling Analysis

### Current risks
- Combined websocket stream creates shared reconnect blast radius.
- Single ingestor process can accumulate symbol-level lag under bursts.
- Direct DB writes can pressure transaction throughput as symbol count rises.
- Docker single-replica model has limited fault isolation.

### Future architectures
A) **Single combined stream**
- simplest ops; worst blast radius.

B) **Grouped symbol shards**
- split symbols into K combined streams; reduces blast radius.

C) **One ingestor per symbol group (multi-service)**
- better isolation, clearer SLOs, horizontal scaling via Compose/K8s replicas.

D) **Queue-based ingestion**
- strongest decoupling (ingest->queue->writers), best for large scale, highest complexity.

### Recommended safest next step
**Step B -> C progression**:
1. introduce grouped symbol sharding inside current ingestor logic,
2. then deploy per-group ingestor services (same code, different symbol env sets),
3. keep idempotent upserts and per-group lag metrics.

This yields meaningful risk reduction before queue infrastructure complexity.

## Module Reference
- See codebase whitepaper sectioning for architecture map; key modules and responsibilities are explicitly documented for:
  - `app/main.py`, `app/api.py`, `app/backtest.py`, `app/walk_forward.py`, `app/experiments.py`,
  - `app/features.py`, `app/research_agent.py`, `app/research_analytics.py`, `app/dataset_splits.py`,
  - `app/strategy_registry.py`, `app/import_binance_klines.py`, `frontend/`, and `docker-compose.yml`.

