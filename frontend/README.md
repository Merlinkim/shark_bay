# Shark Bay React Operations Console (v0.4.4)

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

- `src/layouts/ConsoleLayout.tsx`: shell with collapsible sidebar and top status bar.
- `src/pages/*`: operational pages and placeholders.
- `src/hooks/useOperationsPolling.ts`: polling loop (10s) for `/health` and `/ingestion/status`.
- `src/services/api.ts`: typed API client with `VITE_API_BASE_URL`.
- `src/components/*`: shared cards and status indicators.

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
