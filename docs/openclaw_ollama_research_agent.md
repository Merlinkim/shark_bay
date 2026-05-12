# OpenClaw + Ollama + Gemma4 Research Agent Integration v0

This document defines a **documentation-only** integration pattern for using a local OpenClaw/Ollama/Gemma4 runtime as an external reasoning layer for Shark Bay research workflows.

## Scope and architecture

- Shark Bay remains the deterministic research engine and source of truth.
- OpenClaw + Gemma4 is an external research reasoning layer only.
- This integration is limited to research orchestration and analysis.

### Explicit non-goals

- No live trading.
- No paper trading.
- No order execution.
- No autonomous code modification.
- No direct exchange access by agents.

## 1) Install Ollama locally

Install Ollama using the official instructions for your OS:

- https://ollama.com/download

After install, verify Ollama is running and reachable:

```bash
curl http://localhost:11434/api/tags
```

## 2) Pull and run Gemma4 with Ollama

Recommended default model:

```bash
ollama pull gemma4
```

If your local tag differs, inspect installed models and run available variant:

```bash
ollama list
ollama run gemma4
```

> Ollama lists Gemma4-family models for reasoning, agentic workflows, coding, and multimodal-oriented use cases. Use the locally available Gemma4 tag that best matches your machine capacity.

## 3) OpenClaw provider configuration (native Ollama)

Configure OpenClaw to use the **native Ollama provider** with:

```yaml
provider: ollama
baseUrl: "http://localhost:11434"
model: "gemma4"
```

Important:

- Use `http://localhost:11434` (no `/v1`) for OpenClaw native Ollama provider mode.
- Do **not** set `baseUrl` to `http://localhost:11434/v1` in native Ollama mode.

## 4) Shark Bay read-only research API surface for agents

Expose only deterministic, read-only research endpoints to OpenClaw:

- `GET /symbols/active`
- `GET /ingestion/telemetry`
- `GET /research/features`
- `GET /strategies/registry`
- `GET /research/analytics`
- `GET /research/dataset/splits`
- `GET /research/walk-forward/run`
- `GET /research/agent/recommendations`
- `GET /research/experiments/latest`

All decisions and recommendations must be grounded in these deterministic responses.

## 5) Safety boundaries

The research agent must operate under strict safety rules:

1. Research-only analysis; never execute trades.
2. Never enable live trading or paper trading features.
3. Never place orders or access exchange credentials.
4. Never modify Shark Bay source code autonomously.
5. Treat Shark Bay deterministic endpoints and outputs as source of truth.
6. Respect hidden holdout boundaries and avoid leakage in experiment recommendations.

## 6) Suggested local health checks

Use these commands to verify local model and API availability:

```bash
curl http://localhost:11434/api/tags
curl "http://localhost:8000/research/agent/recommendations?symbol=BTCUSDT&interval=1m"
```

## 7) Task examples for OpenClaw research workflows

- Analyze failed walk-forward result for `ema_cross_v1` and summarize likely failure modes.
- Recommend deterministic parameter mutation candidates for next experiment cycle.
- Compare BTCUSDT vs ETHUSDT suitability for a strategy under current deterministic telemetry.
- Identify high overfitting risk signals from recent experiment and walk-forward outputs.
- Suggest next deterministic experiments with clear rationale and expected learning value.
