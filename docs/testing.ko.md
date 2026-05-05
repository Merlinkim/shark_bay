# 테스트 및 검증 가이드

이 문서는 Shark Bay에서 현재 사용할 수 있는 런타임 점검 및 테스트 명령을 정리합니다.

> 범위: Docker 서비스와 API 엔드포인트의 운영 검증 명령, 그리고 이 저장소에 현재 존재하는 Python 테스트 명령.

## 1) 컨테이너 상태 점검

- **목적**: 모든 예상 서비스가 정상 실행 중인지 확인하고, 재시작/크래시 루프를 빠르게 식별합니다.
- **명령**:
  ```bash
  docker compose ps
  ```
- **예상 결과**: `db`, `ingestor`, `api`, `research-ui`, `prometheus`, `grafana`, `cadvisor`가 `Up` 상태로 표시됩니다(정의된 경우 health 상태도 healthy).
- **실패 시 보통 의미**: 하나 이상의 서비스 시작 실패, 반복 재시작, 또는 의존성/헬스체크 실패로 인한 대기 상태.

## 2) API health 점검

- **목적**: API 프로세스 접근 가능 여부와 readiness 의존성 충족 여부를 확인합니다.
- **명령**:
  ```bash
  curl -sS http://localhost:8000/health
  curl -sS http://localhost:8000/health/live
  curl -sS http://localhost:8000/health/ready
  ```
- **예상 결과**: healthy/liveness OK를 나타내는 JSON 응답, readiness는 DB 연결 가능 시 성공 응답.
- **실패 시 보통 의미**: API 컨테이너 다운, 시작 미완료, 또는 DB 연결/readiness 의존성 실패.

## 3) ingestion status 점검

- **목적**: ingestor heartbeat와 ingestion 파이프라인 최신성을 확인합니다.
- **명령**:
  ```bash
  curl -sS http://localhost:8000/ingestion/status
  ```
- **예상 결과**: 최근 heartbeat/업데이트 시각과 상태를 포함한 구조화된 JSON(지속 에러 신호 없음).
- **실패 시 보통 의미**: ingestor 정지/크래시, 소스 데이터 수집 실패, 또는 PostgreSQL 쓰기 실패.

## 4) candle 개수 조회 쿼리

- **목적**: candle 데이터가 실제로 PostgreSQL에 저장되고 있는지 검증합니다.
- **명령**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, interval, COUNT(*) AS candle_count FROM candles_1m GROUP BY symbol, interval ORDER BY symbol, interval;"
  ```
- **예상 결과**: 예상 symbol/interval에 대해 `candle_count`가 0보다 큰 행이 1개 이상 반환됩니다.
- **실패 시 보통 의미**: ingestion 저장 실패, 스키마 초기화 실패, 또는 잘못된 DB/테이블 조회.

## 5) 갭 탐지 쿼리

- **목적**: 저장된 candle 시계열에서 1분 간격 누락(gap)을 탐지합니다.
- **명령**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "WITH ordered AS (SELECT symbol, interval, open_time, LAG(open_time) OVER (PARTITION BY symbol, interval ORDER BY open_time) AS prev_open_time FROM candles_1m) SELECT symbol, interval, prev_open_time, open_time, (EXTRACT(EPOCH FROM (open_time - prev_open_time))/60)::int AS gap_minutes FROM ordered WHERE prev_open_time IS NOT NULL AND open_time - prev_open_time > INTERVAL '1 minute' ORDER BY open_time DESC LIMIT 50;"
  ```
- **예상 결과**: 이상적으로 0행(또는 알려진/허용 가능한 드문 갭만 존재).
- **실패 시 보통 의미**: ingestion 중단, 소스 다운타임, 시계 오차, 또는 미채워진 과거 데이터 구간.

## 6) backfill 검증

- **목적**: 최신 소수 candle뿐 아니라 목표 기간의 과거 데이터가 존재하는지 확인합니다.
- **명령**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, interval, MIN(open_time) AS first_candle, MAX(open_time) AS latest_candle, COUNT(*) AS total_rows FROM candles_1m GROUP BY symbol, interval ORDER BY symbol, interval;"
  ```
- **예상 결과**: `first_candle`이 분석에 필요한 기간만큼 충분히 과거이며, `total_rows`가 경과 시간 대비 합리적입니다.
- **실패 시 보통 의미**: backfill 미실행, ingestion 최근 시작, 또는 보존 정책/리셋으로 과거 행 삭제.

## 7) Prometheus targets 점검

- **목적**: 관측 대상 scrape 상태를 검증합니다.
- **명령**:
  ```bash
  curl -sS http://localhost:9090/api/v1/targets
  ```
- **예상 결과**: active targets에서 `api`, `ingestor`, `cadvisor`가 `up`으로 표시됩니다.
- **실패 시 보통 의미**: 대상 엔드포인트 접근 불가, metrics path/port 오설정, Docker Compose 내부 DNS/네트워크 문제, 또는 서비스 미실행.

## 8) Grafana 점검

- **목적**: 대시보드 스택 접근성과 Prometheus 데이터 연동 상태를 확인합니다.
- **명령**:
  ```bash
  open http://localhost:3000
  ```
  (Linux 대안: `xdg-open http://localhost:3000` 또는 브라우저에서 수동 접속)
- **예상 결과**: Grafana 로그인 페이지 로드(기본 `admin` / `admin`, 변경되지 않은 경우), Shark Bay 대시보드 패널에 데이터 표시.
- **실패 시 보통 의미**: Grafana 컨테이너 미실행, 프로비저닝/datasource 문제, 또는 Prometheus에 유효 데이터 부재.

## 9) Streamlit research UI 점검

- **목적**: 읽기 전용 backtest 리서치 UI 접근성과 FastAPI backtest 엔드포인트 조회 가능 여부를 확인합니다.
- **명령**:
  ```bash
  open http://localhost:8501
  ```
  (Linux 대안: `xdg-open http://localhost:8501`)
- **예상 결과**: Streamlit 앱 로드, 최근 실행 목록(또는 정상 빈 상태) 표시, 실행 선택 시 상세/equity/fills 표시.
- **실패 시 보통 의미**: `research-ui` 컨테이너 비가용, API 엔드포인트 오류, 또는 조회 가능한 backtest 기록 없음.

## 10) backtest CLI 고정 윈도우 재현성 테스트

- **목적**: 동일 입력 구간/설정에서 결정론적 재실행 일관성(`dataset fingerprint`, `config hash`)을 확인합니다.
- **명령**:
  ```bash
  python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
  python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
  jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run1>/summary.json
  jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run2>/summary.json
  ```
- **예상 결과**: 두 실행의 `config hash` 일치, `dataset fingerprint` 일치, 결정론 요약 메트릭 동일.
- **실패 시 보통 의미**: 입력 구간 불일치, 파라미터/전략 기본값 변경, 비결정론 로직, 또는 다른 실행 폴더 비교.

## 11) backtest DB 영속성 검증

- **목적**: backtest 실행 결과가 저장되고 API(또는 DB)로 조회 가능한지 확인합니다.
- **명령**:
  ```bash
  curl -sS http://localhost:8000/backtests
  curl -sS "http://localhost:8000/backtests/<run_id>"
  curl -sS "http://localhost:8000/backtests/<run_id>/fills"
  curl -sS "http://localhost:8000/backtests/<run_id>/equity-curve"
  ```
- **예상 결과**: 목록 엔드포인트가 실행 기록을 반환하고, 유효한 `<run_id>`에 대해 상세/fills/equity 데이터가 반환됩니다.
- **실패 시 보통 의미**: 아직 저장된 실행 없음, 잘못된 run id, API/DB 스키마 불일치, 또는 backtest 실행 중 저장 실패.

## 12) strategy registry 점검

- **목적**: strategy registry 연결 상태와 등록 전략의 API 노출 여부를 확인합니다.
- **명령**:
  ```bash
  curl -sS http://localhost:8000/strategies
  ```
- **예상 결과**: 등록된 전략 메타데이터(`strategy_name`, 스키마/기본 파라미터 등)를 담은 JSON 리스트/객체.
- **실패 시 보통 의미**: registry 등록 누락, API 라우트 오류, import/runtime 오류, 또는 전략 메타데이터 비호환.

## 13) 현재 동작하는 pytest 명령

- **목적**: 이 저장소에 존재하는 단위/통합 테스트 모듈을 실행합니다.
- **명령**:
  ```bash
  pytest -q
  pytest tests/test_main.py -q
  pytest tests/test_api.py -q
  pytest tests/test_backtest.py -q
  ```
- **예상 결과**: Python 환경이 올바르게 준비된 경우 테스트가 실패 없이 통과합니다.
- **실패 시 보통 의미**: 의존성 누락, 환경 불일치, 테스트 대비 동작 변경, 또는 통합 성격 검증에 필요한 서비스 미실행.

---

## 참고

- 운영 점검 전 `make up` 실행을 권장하며, 디버깅 시 `make logs-api` / `make logs-ingestor`를 활용하세요.
- 파괴적 리셋이 필요하면 `make down` 후 볼륨을 제거하되, 데이터 손실을 허용할 때만 수행하세요.
