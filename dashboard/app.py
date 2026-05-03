import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
DEFAULT_LIMIT = int(os.getenv("BACKTEST_LIST_LIMIT", "100"))

st.set_page_config(page_title="Backtest Research UI", layout="wide")
st.title("Backtest Research UI")


@st.cache_data(ttl=5)
def fetch_json(path: str):
    resp = requests.get(f"{API_BASE_URL}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def post_json(path: str, payload: dict):
    resp = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


page = st.sidebar.radio("Page", ["Run Backtest", "Backtest Explorer"])

if page == "Run Backtest":
    st.subheader("Run Backtest")
    try:
        strategies = fetch_json("/strategies").get("strategies", {})
    except Exception as exc:
        st.error(f"Failed to load strategy registry: {exc}")
        st.stop()

    strategy_name = st.selectbox("Strategy", list(strategies.keys()))
    strategy_meta = strategies.get(strategy_name, {})
    strategy_params = {}
    for param_name, spec in strategy_meta.get("params", {}).items():
        if spec.get("type") == "int":
            strategy_params[param_name] = st.number_input(
                param_name,
                min_value=int(spec.get("min", 1)),
                max_value=int(spec.get("max", 10000)),
                value=int(spec.get("default", 1)),
                step=1,
            )

    symbol = st.text_input("Symbol", value="BTCUSDT")
    interval = st.selectbox("Interval", ["1m"])
    start_time = st.text_input("Start Time (ISO8601, optional)", value="")
    end_time = st.text_input("End Time (ISO8601, optional)", value="")
    save_results = st.checkbox("Save results", value=True)

    if st.button("Run"):
        payload = {
            "strategy_name": strategy_name,
            "strategy_params": strategy_params,
            "symbol": symbol,
            "interval": interval,
            "start_time": start_time or None,
            "end_time": end_time or None,
            "save_results": save_results,
        }
        try:
            result = post_json("/backtests/run", payload)
            run_id = result["run_id"]
            st.success(f"Backtest completed. run_id={run_id}")
        except requests.HTTPError as exc:
            st.error(f"Run failed: {exc.response.status_code} {exc.response.text}")
            st.stop()
        except requests.RequestException as exc:
            st.error(f"Run failed: {exc}")
            st.stop()

        run_detail = fetch_json(f"/backtests/{run_id}")
        fills = fetch_json(f"/backtests/{run_id}/fills")
        equity_curve = fetch_json(f"/backtests/{run_id}/equity-curve")

        st.subheader("Summary Metrics")
        metric_cols = st.columns(6)
        metric_cols[0].metric("Total Return", f"{(run_detail.get('total_return') or 0):.4f}")
        metric_cols[1].metric("Final Equity", f"{(run_detail.get('final_equity') or 0):.2f}")
        metric_cols[2].metric("Max Drawdown", f"{(run_detail.get('max_drawdown') or 0):.4f}")
        metric_cols[3].metric("Profit Factor", f"{(run_detail.get('profit_factor') or 0):.4f}")
        metric_cols[4].metric("Trade Count", str(run_detail.get("trade_count") or 0))
        metric_cols[5].metric("Win Rate", f"{(run_detail.get('win_rate') or 0):.2%}")

        st.text_input("Config Hash", value=run_detail.get("config_hash", ""), disabled=True)
        st.text_input("Dataset Fingerprint", value=run_detail.get("dataset_fingerprint", ""), disabled=True)

        if equity_curve:
            equity_df = pd.DataFrame(equity_curve)
            equity_df["open_time"] = pd.to_datetime(equity_df["open_time"], errors="coerce")
            fig = px.line(equity_df, x="open_time", y="equity", title="Equity Over Time")
            st.plotly_chart(fig, use_container_width=True)
        if fills:
            st.dataframe(pd.DataFrame(fills), use_container_width=True, hide_index=True)

else:
    st.caption("Read-only explorer for persisted backtest runs and results.")
    with st.sidebar:
        st.subheader("Options")
        auto_refresh = st.checkbox("Auto-refresh", value=False)
        refresh_seconds = st.slider("Refresh interval (seconds)", min_value=5, max_value=120, value=15, step=5)
        run_limit = st.number_input("Run list limit", min_value=1, max_value=500, value=DEFAULT_LIMIT, step=1)

    if auto_refresh:
        st.query_params["_ts"] = datetime.now(timezone.utc).isoformat()
        st.markdown(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", unsafe_allow_html=True)

    try:
        runs = fetch_json(f"/backtests?limit={int(run_limit)}")
    except Exception as exc:
        st.error(f"Failed to load backtest runs: {exc}")
        st.stop()

    if not runs:
        st.info("No backtest runs found.")
        st.stop()

    runs_df = pd.DataFrame(runs)
    run_details = []
    for run_id in runs_df["run_id"].tolist():
        try:
            run_details.append(fetch_json(f"/backtests/{run_id}"))
        except requests.RequestException:
            continue
    if run_details:
        runs_df = pd.DataFrame(run_details)

    st.dataframe(runs_df, use_container_width=True, hide_index=True)
