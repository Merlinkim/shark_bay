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

## Python runtime compatibility

This MCP requires **Python 3.10 or newer** because `mcp>=1.9.0` does not support Python 3.9. Python **3.12 is recommended** for local development and agent-server deployment.

Compatibility is declared in `pyproject.toml` with `requires-python = ">=3.10"`, and `server.py` performs a startup check before importing the MCP runtime. If the interpreter is too old, startup exits cleanly with a message like:

```text
ERROR:
Python 3.10+ is required.

Detected:
Python 3.9.6

Recommended:
Python 3.12
```

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

## Quick start: install, run, and test

아래 순서대로 하면 됩니다. 이 MCP는 SharkBay 앱 서버에서 실행하는 것이 아니라 **OpenClaw/agent 서버에서 실행**하고, `SHARKBAY_BASE_URL`을 통해 원격 SharkBay API를 호출합니다.

### 1. Install / 설치

Python 3.12가 권장됩니다. 최소 지원 버전은 Python 3.10입니다.
## Install and run locally

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`python3.12` 명령이 없다면 Python 3.10 이상 인터프리터를 사용할 수 있습니다. 예를 들어:

```bash
python3.10 -m venv .venv
```

설치 확인:

```bash
python --version
python -m pip show mcp
```

### 2. Configure / 환경변수 설정

최소 설정은 `SHARKBAY_BASE_URL`입니다. 인증이 필요한 SharkBay API라면 `SHARKBAY_API_KEY`도 설정합니다.

```bash
export SHARKBAY_BASE_URL="https://your-sharkbay-api-server"
export SHARKBAY_API_KEY="Bearer optional-token"
```

OpenAPI URL을 직접 지정해야 하면 다음을 추가합니다. 지정하지 않으면 `${SHARKBAY_BASE_URL}/openapi.json`를 사용합니다.

```bash
export SHARKBAY_OPENAPI_URL="https://your-sharkbay-api-server/openapi.json"
```

### 3. Run / 실행

MCP 서버는 stdio 기반으로 실행됩니다. 보통은 OpenClaw가 실행하지만, 로컬에서 프로세스가 시작되는지 확인하려면 다음 명령을 사용할 수 있습니다.

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
. .venv/bin/activate
python -m server
```

정상 실행 시 프로세스가 MCP stdio 서버로 대기합니다. 터미널에서 직접 실행하면 일반 웹 서버처럼 URL을 출력하지 않을 수 있습니다. 실제 사용은 OpenClaw MCP 등록을 통해 호출하는 방식입니다.

### 4. Register with OpenClaw / OpenClaw에 등록
export SHARKBAY_BASE_URL="https://your-sharkbay-api-server"
export SHARKBAY_API_KEY="Bearer optional-token"
python -m server
```

The server communicates over MCP stdio using the `mcp` Python package. If `python3.12` is not available, use any Python 3.10+ interpreter; Python 3.12 remains preferred.

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

가상환경의 Python을 명시하고 싶으면 `command`를 `.venv/bin/python`의 절대경로로 바꿉니다.

```json
{
  "command": "/path/to/shark_bay/external/sharkbay_mcp/.venv/bin/python",
  "args": ["-m", "server"],
  "cwd": "/path/to/shark_bay/external/sharkbay_mcp"
}
```

### 5. Test / 테스트

단위 테스트는 live SharkBay 서버 없이 실행됩니다. mocked OpenAPI schema와 mocked HTTP response를 사용합니다.

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
. .venv/bin/activate
python -m pytest tests -q
```

레포 루트에서 실행하는 경우:

```bash
python -m pytest external/sharkbay_mcp/tests -q
```

문법/bytecode 확인:

```bash
python -m compileall -q openapi_client.py schema_registry.py safety.py python_version.py tests
```

레포 루트에서 실행하는 경우:

```bash
python -m compileall -q external/sharkbay_mcp/openapi_client.py external/sharkbay_mcp/schema_registry.py external/sharkbay_mcp/safety.py external/sharkbay_mcp/python_version.py external/sharkbay_mcp/tests
```

테스트가 검증하는 항목:

- `list_endpoints` OpenAPI endpoint 목록 생성
- `get_endpoint_schema` endpoint schema 조회
- `call_endpoint` 성공 호출
- 필수 path parameter 누락 처리
- 존재하지 않는 endpoint ID 거부
- secret redaction
- response truncation
- Python 3.10 미만 runtime error message

### 6. Copy to an agent server / agent 서버로 복사해서 실행

이 폴더만 복사해도 동작하도록 설계되어 있습니다. 예:

```bash
scp -r external/sharkbay_mcp openclaw-agent:/opt/sharkbay_mcp
ssh openclaw-agent
cd /opt/sharkbay_mcp
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

그 다음 OpenClaw 등록의 `cwd`를 `/opt/sharkbay_mcp`로 설정합니다.

The server communicates over MCP stdio using the `mcp` Python package. If `python3.12` is not available, use any Python 3.10+ interpreter; Python 3.12 remains preferred.
For an agent-server deployment, copy this directory to the agent server, create the virtual environment with Python 3.12 where possible, install `requirements.txt`, and point `cwd` at the copied folder. Only `SHARKBAY_BASE_URL` needs to know where SharkBay is hosted.

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

## Troubleshooting

### `pip install -r requirements.txt` fails on Python 3.9

If dependency installation fails with a message indicating that `mcp` requires Python 3.10 or newer, recreate the virtual environment with Python 3.12:

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
rm -rf .venv
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m server
```

If Python 3.12 is not installed on the agent server, install it through your operating system package manager, `pyenv`, or your standard server image build process. Python 3.10 and 3.11 are supported, but Python 3.12 is recommended.

### Startup prints `Python 3.10+ is required`

The MCP checks the interpreter version before importing `mcp`. This usually means OpenClaw is launching `python` from an older virtual environment. Update the OpenClaw MCP registration so `command` points to the Python 3.12 virtual-environment binary, or rebuild `.venv` with Python 3.12 and keep `command` as `python` while `cwd` points to this folder.

## Tests

Tests use mocked OpenAPI and mocked HTTP responses, so no live SharkBay server is required. The recommended commands are listed in [Quick start: install, run, and test](#quick-start-install-run-and-test). The shortest command from this directory is:

```bash
python -m pytest tests -q
Tests use mocked OpenAPI and mocked HTTP responses, so no live SharkBay server is required:

```bash
cd /path/to/shark_bay/external/sharkbay_mcp
pytest
```
