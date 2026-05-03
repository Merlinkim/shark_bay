import os
from datetime import date, datetime, time, timezone

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


def _to_iso8601_utc(day: date | None, hhmm: time | None) -> str | None:
    if not day or not hhmm:
        return None
    dt = datetime.combine(day, hhmm).replace(tzinfo=timezone.utc)
    return dt.isoformat()


page = st.sidebar.radio("Page", ["Run Backtest", "Backtest Explorer"])

if page == "Run Backtest":
    st.subheader("Run Backtest")
    strategies = fetch_json("/strategies").get("strategies", {})
    strategy_name = st.selectbox("Strategy", list(strategies.keys()))
    strategy_meta = strategies.get(strategy_name, {})

    strategy_params = {}
    for param_name, spec in strategy_meta.get("params", {}).items():
        if spec.get("type") == "int":
            strategy_params[param_name] = int(
                st.number_input(
                    param_name,
                    min_value=int(spec.get("min", 1)),
                    max_value=int(spec.get("max", 10000)),
                    value=int(spec.get("default", 1)),
                    step=1,
                )
            )

    symbol = st.text_input("Symbol", value="BTCUSDT").upper()
    interval = st.selectbox("Interval", ["1m"])
    start_col, end_col = st.columns(2)
    with start_col:
        start_date = st.date_input("Start date", value=None)
        start_clock = st.time_input("Start time (UTC)", value=time(0, 0))
    with end_col:
        end_date = st.date_input("End date", value=None)
        end_clock = st.time_input("End time (UTC)", value=time(23, 59))

    save_results = st.checkbox("Save results", value=True)

    if st.button("Run"):
        payload = {
            "strategy_name": strategy_name,
            "strategy_params": strategy_params,
            "symbol": symbol,
            "interval": interval,
            "start_time": _to_iso8601_utc(start_date, start_clock),
            "end_time": _to_iso8601_utc(end_date, end_clock),
            "save_results": save_results,
        }
        result = post_json("/backtests/run", payload)

        st.subheader("Summary Metrics")
        sm = result.get("summary_metrics", {})
        metric_cols = st.columns(6)
        metric_cols[0].metric("Total Return", f"{sm.get('total_return', 0):.4f}")
        metric_cols[1].metric("Final Equity", f"{sm.get('final_equity', 0):.2f}")
        metric_cols[2].metric("Max Drawdown", f"{sm.get('max_drawdown', 0):.4f}")
        metric_cols[3].metric("Profit Factor", f"{sm.get('profit_factor', 0):.4f}")
        metric_cols[4].metric("Trade Count", str(sm.get("trade_count", 0)))
        metric_cols[5].metric("Win Rate", f"{sm.get('win_rate', 0):.2f}%")

        st.text_input("Config Hash", value=result.get("config_hash", ""), disabled=True)
        st.text_input("Dataset Fingerprint", value=result.get("dataset_fingerprint", ""), disabled=True)

        run_id = result.get("run_id")
        if run_id:
            st.success(f"Backtest completed and saved. run_id={run_id}")
            run_detail = fetch_json(f"/backtests/{run_id}")
            fills = fetch_json(f"/backtests/{run_id}/fills")
            equity_curve = fetch_json(f"/backtests/{run_id}/equity-curve")

            if equity_curve:
                equity_df = pd.DataFrame(equity_curve)
                equity_df["open_time"] = pd.to_datetime(equity_df["open_time"], errors="coerce")
                fig = px.line(equity_df, x="open_time", y="equity", title="Equity Over Time")
                st.plotly_chart(fig, use_container_width=True)
            if fills:
                st.subheader("Fills / Trades")
                st.dataframe(pd.DataFrame(fills), use_container_width=True, hide_index=True)
            st.caption(f"Status: {run_detail.get('status')}")
        else:
            st.info("Backtest completed without persistence (save_results=false).")

else:
    st.subheader("Backtest Explorer")
    runs = fetch_json(f"/backtests?limit={DEFAULT_LIMIT}")
    if not runs:
        st.info("No backtest runs found.")
        st.stop()

    runs_df = pd.DataFrame(runs)
    run_ids = runs_df["run_id"].tolist()
    selected_run_id = st.selectbox("Select run", run_ids)

    details = {rid: fetch_json(f"/backtests/{rid}") for rid in run_ids}
    selected = details[selected_run_id]
    st.json({
        "run_id": selected["run_id"],
        "strategy_name": "sma_cross",
        "config_hash": selected["config_hash"],
        "dataset_fingerprint": selected["dataset_fingerprint"],
        "summary": {
            "total_return": selected.get("total_return"),
            "final_equity": selected.get("final_equity"),
            "max_drawdown": selected.get("max_drawdown"),
            "profit_factor": selected.get("profit_factor"),
            "trade_count": selected.get("trade_count"),
            "win_rate": selected.get("win_rate"),
        },
    })

    eq = fetch_json(f"/backtests/{selected_run_id}/equity-curve")
    fills = fetch_json(f"/backtests/{selected_run_id}/fills")
    if eq:
        eq_df = pd.DataFrame(eq)
        eq_df["open_time"] = pd.to_datetime(eq_df["open_time"], errors="coerce")
        st.plotly_chart(px.line(eq_df, x="open_time", y="equity", title="Equity Curve"), use_container_width=True)
    if fills:
        st.dataframe(pd.DataFrame(fills), use_container_width=True, hide_index=True)

    compare_ids = st.multiselect("Compare saved runs", options=run_ids, default=run_ids[: min(3, len(run_ids))])
    if compare_ids:
        rows = []
        for rid in compare_ids:
            d = details[rid]
            rows.append({
                "run_id": rid,
                "strategy_name": "sma_cross",
                "config_hash": d.get("config_hash"),
                "dataset_fingerprint": d.get("dataset_fingerprint"),
                "total_return": d.get("total_return"),
                "final_equity": d.get("final_equity"),
                "max_drawdown": d.get("max_drawdown"),
                "profit_factor": d.get("profit_factor"),
                "trade_count": d.get("trade_count"),
                "win_rate": d.get("win_rate"),
            })
        st.subheader("Run Comparison")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
