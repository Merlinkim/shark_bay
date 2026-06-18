# 코드베이스 그래프 (Shark Bay)

아래 그래프는 현재 레포의 주요 실행 컴포넌트와 코드 모듈 간의 관계를 요약합니다.

```mermaid
flowchart LR
  subgraph Runtime[Runtime Services]
    DB[(PostgreSQL\n`db`)]
    ING[Ingestor\n`app/main.py`]
    API[FastAPI\n`app/api.py`]
    FE[Frontend\nReact/Vite + Nginx]
    RUI[Research UI\n`dashboard/app.py`]
    PROM[Prometheus]
    GRAF[Grafana]
    CAD[cAdvisor]
  end

  subgraph IngestorModules[Ingestor 내부 모듈]
    M_MAIN[`app/main.py`]
    M_MET[`app/metrics.py`]
    M_OBS[`app/observability.py`]
    M_DQ[`app/data_quality.py`]
    M_RB[`app/rest_backfill.py`]
    M_HI[`app/historical_import.py`]
  end

  subgraph ResearchBacktest[리서치/백테스트 모듈]
    M_BT[`app/backtest.py`]
    M_WF[`app/walk_forward.py`]
    M_EXP[`app/experiments.py`]
    M_RA[`app/research_analytics.py`]
    M_REG[`app/strategy_registry.py`]
    M_RS[`app/research_agent.py`]
    M_FEAT[`app/features.py`]
    M_SPLIT[`app/dataset_splits.py`]
  end

  subgraph FrontendCode[프론트엔드 코드]
    F_APP[`frontend/src/App.tsx`]
    F_API[`frontend/src/services/api.ts`]
    F_PAGES[`frontend/src/pages/*`]
    F_HOOKS[`frontend/src/hooks/*`]
    F_COMP[`frontend/src/components/*`]
  end

  ING -->|upsert candles_1m| DB
  API -->|read status/candles/backtests| DB
  FE -->|/api proxy| API
  RUI -->|REST 호출| API
  PROM -->|scrape :8000/metrics| API
  PROM -->|scrape :9100| ING
  PROM -->|scrape :8080/metrics| CAD
  GRAF -->|query| PROM

  M_MAIN --> M_MET
  M_MAIN --> M_OBS
  M_MAIN --> M_DQ
  M_MAIN --> M_RB
  M_MAIN --> M_HI

  API --> M_BT
  API --> M_WF
  API --> M_EXP
  API --> M_RA
  API --> M_REG
  API --> M_RS
  API --> M_FEAT
  API --> M_SPLIT

  F_APP --> F_PAGES
  F_PAGES --> F_API
  F_PAGES --> F_HOOKS
  F_PAGES --> F_COMP
```

## 빠른 읽기
- **수집 경로**: Binance(외부) → `ingestor`(`app/main.py`) → PostgreSQL.
- **조회 경로**: Frontend/Research UI → FastAPI(`app/api.py`) → PostgreSQL.
- **관측 경로**: API/ingestor/cAdvisor → Prometheus → Grafana.
- **분석 경로**: FastAPI가 백테스트/실험/전략/리서치 모듈을 조합해 결과를 API로 노출.


## 보는 방법 (PC/모바일)
- **GitHub 웹/앱에서 바로 보기**: `docs/code_graph.md`를 열면 Mermaid 블록이 지원되는 뷰어에서 그래프로 렌더링됩니다.
- **모바일 가능 여부**: 네, 가능합니다. 다만 화면이 좁아 노드가 작게 보일 수 있으니 **가로 모드** 또는 **핀치 줌**을 권장합니다.
- **렌더링이 안 보일 때**: Mermaid 미지원 뷰어에서는 코드 블록으로 보일 수 있습니다. 이 경우 GitHub 웹 브라우저(데스크톱 모드)에서 열거나, Mermaid Live Editor에 본문을 붙여넣어 확인하세요.
- **빠른 대안**: 하단의 `빠른 읽기` 섹션만 봐도 전체 데이터/서비스 흐름을 텍스트로 파악할 수 있습니다.
