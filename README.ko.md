# Shark Bay — 아키텍처 및 운영 가이드

이 저장소는 다음으로 구성된 소규모 마켓 데이터 플랫폼을 실행합니다.

- **PostgreSQL** 데이터 저장소
- 1분 봉(candle) 데이터를 수집하고 upsert하는 **ingestor** 서비스
- 상태/헬스/데이터 엔드포인트를 제공하는 **FastAPI** 서비스
- 메트릭 수집용 **Prometheus**
- 대시보드용 **Grafana**

---

## Docker Compose 아키텍처

`docker-compose.yml`은 7개 서비스와 2개의 영속 볼륨을 정의합니다.

- `db` (PostgreSQL 16)
- `ingestor` (`./app`에서 빌드한 커스텀 Python 앱 이미지)
- `api` (`./app`에서 빌드한 커스텀 Python 앱 이미지)
- `research-ui` (Streamlit backtest 리서치 대시보드)
- `prometheus` (Prometheus v2.54.1)
- `grafana` (Grafana 11.2.2)
- `cadvisor` (컨테이너 리소스 exporter)
- 볼륨:
  - Postgres 데이터 영속성을 위한 `pgdata`
  - Grafana 상태 저장을 위한 `grafana-data`

### 런타임 흐름(상위 수준)

1. `db`가 시작되고 헬스체크(`pg_isready`)를 통과해야 합니다.
2. `ingestor`와 `api`는 모두 `db`가 healthy 상태가 될 때까지 대기합니다.
3. `ingestor`는 스키마를 초기화하고 Binance klines를 가져와 `candles_1m`에 upsert하며 heartbeat를 기록하고 메트릭을 내보냅니다.
4. `api`는 health/readiness, candle 조회, ingestion status, `/metrics`를 노출합니다.
5. `prometheus`는 다음을 scrape합니다.
   - `api:8000/metrics`
   - `ingestor:9100`
   - `cadvisor:8080/metrics`
6. `research-ui`는 기존 FastAPI backtest 엔드포인트만 사용하는 로컬 읽기 전용 대시보드를 제공합니다.
7. `grafana`는 Prometheus(및 프로비저닝된 datasource 설정)를 읽어 `db`, `ingestor`, `api`, `prometheus`, `grafana`의 컨테이너 리소스 패널을 포함한 운영 대시보드를 표시합니다.

---

## 서비스 설명

### 1) `db` — PostgreSQL

- 목적: 마켓 candle 데이터와 운영 heartbeat/status 테이블의 영구 저장소
- Compose 환경 변수/자격 증명 사용:
  - `POSTGRES_USER=postgres`
  - `POSTGRES_PASSWORD=postgres`
  - `POSTGRES_DB=market_data`
- 다운스트림 서비스의 헬스체크 게이트 역할

### 2) `ingestor` — Candle 수집/upsert

- 주기(`POLL_SECONDS`, 기본 10초)로 Binance REST klines 엔드포인트(`/api/v3/klines`)를 폴링합니다.
- candle을 파싱하여 `candles_1m`에 upsert합니다(`ON CONFLICT` 업데이트 경로).
- 수집기 heartbeat 및 누락 candle 이벤트 로직(placeholder)을 추적합니다.
- `METRICS_PORT`(기본 `9100`)에서 `start_http_server`를 통해 Prometheus 메트릭을 노출합니다.
- graceful stop을 위해 SIGTERM/SIGINT를 처리합니다.

### 3) `api` — FastAPI 데이터 + 헬스 + 메트릭

- 주요 엔드포인트:
  - `GET /health`
  - `GET /health/live`
  - `GET /health/ready` (DB 체크 포함)
  - `GET /candles?symbol=BTCUSDT&interval=1m&limit=100`
  - `GET /ingestion/status`
  - `GET /metrics`
- 미들웨어에서 API 요청 수 및 지연시간 메트릭을 기록합니다.

### 4) `research-ui` — Streamlit backtest 리서치 대시보드

- 목적: 저장된 backtest 실행 결과와 결정론적 backtest 출력을 탐색하는 읽기 전용 도구
- **FastAPI 엔드포인트만** 사용:
  - `GET /backtests`
  - `GET /backtests/{run_id}`
  - `GET /backtests/{run_id}/fills`
  - `GET /backtests/{run_id}/equity-curve`
- 기능:
  - 최근 실행 목록(핵심 메타데이터와 요약 메트릭)
  - 선택 가능한 실행 상세 정보
  - equity curve 차트
  - fills/trades 테이블
  - 결정론 메타데이터 카드/필드
  - 로딩/에러 상태 및 선택적 자동 새로고침
- 이 UI에는 전략 실행, 비동기 워커, paper/live 거래, 포트폴리오 액션이 구현되어 있지 않습니다.

### 5) `prometheus` — 메트릭 스크레이퍼

- scrape interval / evaluation interval: `10s`
- `observability/prometheus/prometheus.yml`에 설정된 API, ingestor, cAdvisor 대상을 scrape합니다.

### 6) `cadvisor` — 컨테이너 리소스 exporter

- 실행 중인 컨테이너의 CPU, 메모리, 재시작, 네트워크, 파일시스템 I/O 메트릭을 노출합니다.
- 읽기 전용 호스트 경로 마운트를 통해 cAdvisor가 Docker 런타임/컨테이너 통계를 관찰합니다.
- Prometheus가 `cadvisor:8080`에서 scrape합니다.

### 7) `grafana` — 시각화

- `observability/grafana/provisioning/...`의 프로비저닝된 datasource/dashboard로 시작합니다.
- Compose 기본 로그인 정보:
  - 사용자명: `admin`
  - 비밀번호: `admin`

---

## 포트

Compose의 호스트 매핑 포트:

- `3000` → Grafana UI (`http://localhost:3000`)
- `5432` → PostgreSQL
- `8000` → API (`http://localhost:8000`)
- `8501` → Backtest Research UI (`http://localhost:8501`)
- `9090` → Prometheus UI (`http://localhost:9090`)
- `8080` → cAdvisor UI/metrics (`http://localhost:8080`)
- `9100` → Ingestor metrics exporter (Compose 네트워크 대상은 `ingestor:9100`; Prometheus scrape에 호스트 매핑은 필수 아님)

---

## 메트릭

구현된 메트릭(`app/metrics.py` 기준):

- `candle_insert_total` (Counter)
- `duplicate_candle_total` (Counter)
- `ingest_error_total` (Counter)
- `websocket_reconnect_total` (Counter)
- `latest_candle_timestamp` (Gauge)
- `db_connection_status{service="..."}` (Gauge)
- `api_request_total{method,path,status_code}` (Counter)
- `api_request_latency_seconds{method,path}` (Histogram)

### 메트릭 노출 위치

- API 메트릭 엔드포인트: `http://localhost:8000/metrics`
- Ingestor 메트릭 엔드포인트(컨테이너): `http://ingestor:9100/` (Prometheus가 scrape)

---

## 시작 / 종료 명령

Make 타깃 사용:

```bash
make up
```

- 실행 명령: `docker compose up --build -d`

```bash
make down
```

- 실행 명령: `docker compose down`

유용한 로그 tail:

```bash
make logs-api
make logs-ingestor
```

---

## 검증 명령

시작 후 각 레이어를 확인합니다.

### 컨테이너/서비스 상태

```bash
docker compose ps
```

### API health/readiness/liveness

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready
```

### candle 조회

```bash
curl -sS "http://localhost:8000/candles?symbol=BTCUSDT&interval=1m&limit=5"
```

### Backtest research UI

```bash
open http://localhost:8501
```

Streamlit 대시보드는 읽기 전용이며 FastAPI backtest 엔드포인트만 사용합니다.

### Backtest 결과 API(읽기 전용)

```bash
curl -sS "http://localhost:8000/backtests"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>/fills"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>/equity-curve"
```

### Ingestion status

```bash
curl -sS http://localhost:8000/ingestion/status
```

### 메트릭 점검

```bash
curl -sS http://localhost:8000/metrics | head
curl -sS http://localhost:8080/metrics | head
curl -sS http://localhost:9090/api/v1/targets
```

### cAdvisor 대상 검증(Prometheus UI)

1. `http://localhost:9090/targets`를 엽니다.
2. `cadvisor` 대상이 **UP**인지 확인합니다.
3. Prometheus expression browser에서 다음을 실행합니다.
   - `container_memory_usage_bytes`
   - `rate(container_cpu_usage_seconds_total[1m])`

선택적 CLI 점검:

```bash
curl -sS http://localhost:9090/api/v1/targets | rg cadvisor
```

Grafana(`http://localhost:3000`)에서 **Shark Bay Operational Monitoring**을 열고 다음 패널이 `db`, `ingestor`, `api`, `prometheus`, `grafana` 시계열을 표시하는지 확인합니다.

- Container CPU usage (cores)
- Container memory usage (bytes)
- Container restart count
- Container network RX/TX (bytes/s)
- Container disk I/O (bytes/s)

### Prometheus / Grafana 웹 UI

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

---

## 문제 해결

### 1) API readiness 실패 (`/health/ready`가 503 반환)

점검:

```bash
docker compose ps
docker compose logs --tail=200 db
docker compose logs --tail=200 api
```

가능한 원인:

- DB가 아직 healthy가 아님
- `DATABASE_URL` 잘못 설정
- DB 시작 타이밍의 일시적 문제

### 2) `/ingestion/status`에 최신 candle이 없음

점검:

```bash
docker compose logs --tail=200 ingestor
curl -sS http://localhost:8000/ingestion/status
```

가능한 원인:

- Binance 엔드포인트로의 네트워크 접근 문제
- DB 쓰기 오류
- ingestor 크래시/재시작 루프

### 3) Prometheus 대상이 down 상태

점검:

```bash
curl -sS http://localhost:9090/api/v1/targets
docker compose logs --tail=200 prometheus
docker compose logs --tail=200 api
docker compose logs --tail=200 ingestor
```

가능한 원인:

- scrape 대상 비가용
- 잘못된 metrics path/port
- Compose 네트워크에서 서비스 미실행

### 4) Grafana에 데이터가 없음

점검:

```bash
docker compose logs --tail=200 grafana
curl -sS http://localhost:9090/api/v1/query?query=up
```

가능한 원인:

- Prometheus datasource 프로비저닝 문제
- Prometheus가 대상을 scrape하지 못함
- 대시보드 변수/시간 범위 불일치

### 5) 클린 리셋 필요

```bash
make down
docker volume rm shark_bay_pgdata shark_bay_grafana-data  # 선택적 파괴적 리셋
make up
```

> 영속 DB와 Grafana 상태를 의도적으로 삭제하려는 경우에만 볼륨을 제거하세요.

## 재현 가능한 Backtest

고정된 데이터셋 구간으로 backtest CLI를 실행해 리플레이에 사용되는 candle 집합을 고정할 수 있습니다.

```bash
python -m app.backtest \
  --symbol BTCUSDT \
  --interval 1m \
  --short-window 5 \
  --long-window 20 \
  --start-time 2026-05-01T00:00:00+00:00 \
  --end-time 2026-05-01T12:00:00+00:00
```

선택적으로 고정 구간과 `--limit`를 함께 사용할 수 있습니다.

각 실행은 이제 `summary.json` 및 터미널 출력에 데이터셋 메타데이터를 기록합니다.

- `dataset_fingerprint`
- `dataset_row_count`
- `dataset_min_open_time`
- `dataset_max_open_time`

### 동일 구간에서 두 실행이 동일한지 검증

```bash
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
```

출력 요약 비교:

```bash
jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run1>/summary.json
jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run2>/summary.json
```

동일한 구간/전략 설정에서는 `config_hash`와 `dataset_fingerprint`가 같아야 하며, 결정론 메트릭도 동일해야 합니다.

---

## Strategy Plugin + Indicator 레이어

전략은 이제 `app/backtest.py`의 strategy registry를 통해 탐지되는 plugin 스타일 클래스입니다.

### 새 전략 만들기

1. 필수 메타데이터가 있는 전략 클래스를 추가합니다.
   - `strategy_name`
   - `description`
   - `parameter_schema`
   - `default_parameters`
2. `on_candle(self, candle) -> int`를 구현하고 로직을 결정론적이며 부작용 없이 유지합니다.
3. 수학 로직을 중복 구현하지 말고 `IndicatorLibrary`(`sma`, `ema`, `rsi`, `atr`, `bollinger_bands`)를 재사용합니다.

### 전략 등록

전역 registry에 등록:

```python
strategy_registry.register(MyNewStrategy)
```

### UI/API에 파라미터 노출

- API `/strategies` 엔드포인트는 registry의 전략 메타데이터를 반환합니다.
- Streamlit UI는 `parameter_schema` + `default_parameters`로 전략 파라미터 컨트롤을 자동 생성합니다.
- API `/backtests/run`은 실행 전에 strategy registry를 사용해 `strategy_name`과 `strategy_params`를 검증합니다.

### 전략 템플릿 예시

```python
class MyNewStrategy:
    strategy_name = "my_new_strategy"
    description = "전략 동작 설명"
    parameter_schema = {
        "lookback": {"type": "int", "min": 2, "max": 200},
    }
    default_parameters = {"lookback": 20}

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def on_candle(self, candle: Candle) -> int:
        return 0
```

