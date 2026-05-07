# Shark Bay React Operations Console (v0.4.4)

A premium, dark-mode, high-density operations UI for local-only quant research and monitoring.

## Local startup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Build verification

```bash
npm run build
```

## Architecture overview

- `src/layouts/ConsoleLayout.tsx`: responsive app shell with collapsible desktop nav + mobile drawer.
- `src/pages/*`: dashboard, market data view, and future-work placeholders.
- `src/hooks/useOperationsPolling.ts`: 10-second polling loop for `/health` and `/ingestion/status`.
- `src/services/api.ts`: typed API client using `VITE_API_BASE_URL`.
- `src/components/*`: reusable UI primitives for status and metrics.

## Folder structure

```text
frontend/
  src/
    components/
    hooks/
    layouts/
    pages/
    services/
    styles/
    types/
```
