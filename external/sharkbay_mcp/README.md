# SharkBay MCP (Standalone OpenClaw Bridge)

This folder contains an independent Model Context Protocol (MCP) server that lets OpenClaw agents call the SharkBay FastAPI REST API through SharkBay's public OpenAPI schema.

The component intentionally lives inside the `shark_bay` repository for source-control and API-documentation proximity, but it is designed to be copied out and run beside OpenClaw on an agent server. It does **not** import the SharkBay FastAPI app, models, database code, settings, or deployment stack.

## What this MCP does

The MCP exposes four generic tools:

1. `health_check` — checks whether the configured remote SharkBay API is reachable.
2. `list_endpoints` — reads OpenAPI and returns available endpoints with `endpoint_id`, method, path, summary, tags, and required parameters.
3. `get_endpoint_schema` — returns schema details for a selected `endpoint_id`.
4. `call_endpoint` — calls one OpenAPI-listed endpoint using path params, query params, and an optional JSON body.

It does not create one MCP tool per REST endpoint. OpenClaw can inspect the schema first, choose an `endpoint_id`, and then invoke `call_endpoint`.

## Why it is isolated

This folder is self-contained so the MCP can run on an OpenClaw/agent server while SharkBay runs elsewhere. The runtime boundary is intentional:

- no imports from `app/` or other internal SharkBay modules;
- no database access;
- no local SharkBay settings dependency;
- no assumptions that the MCP and API are on the same host;
- no changes to existing SharkBay application code, routes, models, deployment, or CI/CD.

## How it reads OpenAPI

At startup/tool-call time, the MCP loads OpenAPI through `OpenAPIClient`:

1. Prefer `SHARKBAY_OPENAPI_URL` when set.
2. Otherwise use `${SHARKBAY_BASE_URL}/openapi.json`.
3. If the live OpenAPI request fails, load a local fallback JSON file in this folder. By default that file is `openapi.json`; override with `SHARKBAY_LOCAL_OPENAPI_FILE`.

The fallback is useful when running tests or when deploying the MCP to an agent server with a copied schema snapshot.

## Configuration

Copy `.env.example` and set values in the OpenClaw MCP environment or your process manager:

| Variable | Required | Description |
| --- | --- | --- |
| `SHARKBAY_BASE_URL` | Yes | Remote SharkBay API base URL, for example `https://your-sharkbay-api-server`. |
| `SHARKBAY_OPENAPI_URL` | No | Explicit OpenAPI URL. Defaults to `${SHARKBAY_BASE_URL}/openapi.json`. |
| `SHARKBAY_API_KEY` | No | Authorization header value. If SharkBay expects bearer auth, include the `Bearer ` prefix. |
| `SHARKBAY_TIMEOUT_SECONDS` | No | Request timeout. Defaults to `10`. |
| `SHARKBAY_MAX_RESPONSE_BYTES` | No | Maximum response bytes read/returned by `call_endpoint`. Defaults to `1048576`. |
| `SHARKBAY_LOCAL_OPENAPI_FILE` | No | Local fallback schema path. Defaults to `openapi.json` inside this folder. |

Do not commit real API keys. `.env.example` contains placeholders only.

## Install and run locally

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SHARKBAY_BASE_URL="https://your-sharkbay-api-server"
export SHARKBAY_API_KEY="Bearer optional-token"
python -m server
```

The server communicates over MCP stdio using the `mcp` Python package.

## Register with OpenClaw

Example registration:

```bash
openclaw mcp set sharkbay '{
  "command": "python",
  "args": ["-m", "server"],
  "cwd": "/path/to/shark_bay/external/sharkbay_mcp",
  "env": {
    "SHARKBAY_BASE_URL": "https://your-sharkbay-api-server",
    "SHARKBAY_API_KEY": "optional"
  }
}'
```

For an agent-server deployment, copy this directory to the agent server, install `requirements.txt`, and point `cwd` at the copied folder. Only `SHARKBAY_BASE_URL` needs to know where SharkBay is hosted.

## Example tool calls

List endpoints:

```json
{
  "tool": "list_endpoints",
  "arguments": {}
}
```

Inspect one endpoint:

```json
{
  "tool": "get_endpoint_schema",
  "arguments": {
    "endpoint_id": "read_backtest_job"
  }
}
```

Call an endpoint:

```json
{
  "tool": "call_endpoint",
  "arguments": {
    "endpoint_id": "read_backtest_job",
    "path_params": {"job_id": "example-job-id"},
    "query_params": {},
    "json_body": null,
    "return_raw": false
  }
}
```

Default `call_endpoint` output contains:

- `status_code`
- `success`
- `response_summary`
- `error_summary`
- `request_id`
- `truncated`

## Security limitations and protections

The MCP is a controlled REST bridge, not a general execution environment.

Implemented protections:

- no arbitrary shell command execution;
- no arbitrary URL calls;
- only endpoints present in OpenAPI can be called;
- endpoint paths resolve only under `SHARKBAY_BASE_URL`;
- authorization is read only from `SHARKBAY_API_KEY`;
- common secret fields and bearer tokens are redacted from returned summaries/errors;
- request timeout is always set;
- response bytes are capped by `SHARKBAY_MAX_RESPONSE_BYTES`;
- responses are not persisted.

Operational limitations:

- OpenAPI correctness controls what endpoints are callable.
- The MCP does not perform full JSON Schema validation for every request body; OpenClaw should use `get_endpoint_schema` before calling.
- If `return_raw` is true, payloads are less summarized, but secret redaction and response-size limits still apply.

## What it does NOT do

This MCP does not:

- modify SharkBay source code;
- modify API routes;
- modify database models;
- modify deployment files;
- modify CI/CD;
- import internal SharkBay modules;
- connect to the SharkBay database;
- require the SharkBay repository to be importable;
- assume local API hosting;
- write results to RAG, Wiki, or long-term memory;
- store or print API keys.

OpenClaw receives returned tool results and remains responsible for any memory/RAG/Wiki writes.

## Tests

Tests use mocked OpenAPI and mocked HTTP responses, so no live SharkBay server is required:

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
pytest
```
