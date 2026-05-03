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
st.caption("Read-only explorer for persisted backtest runs and results.")

with st.sidebar:
    st.subheader("Options")
    auto_refresh = st.checkbox("Auto-refresh", value=False)
    refresh_seconds = st.slider("Refresh interval (seconds)", min_value=5, max_value=120, value=15, step=5)
    run_limit = st.number_input("Run list limit", min_value=1, max_value=500, value=DEFAULT_LIMIT, step=1)

if auto_refresh:
    st.query_params["_ts"] = datetime.now(timezone.utc).isoformat()
    st.markdown(
        f"<meta http-equiv='refresh' content='{refresh_seconds}'>",
        unsafe_allow_html=True,
    )

@st.cache_data(ttl=5)
def fetch_json(path: str):
    resp = requests.get(f"{API_BASE_URL}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()

try:
    with st.spinner("Loading backtest runs..."):
        runs = fetch_json(f"/backtests?limit={int(run_limit)}")
except requests.HTTPError as exc:
    st.error(f"Failed to load backtest runs: {exc.response.status_code} {exc.response.text}")
    st.stop()
except requests.RequestException as exc:
    st.error(f"Failed to connect to API: {exc}")
    st.stop()

if not runs:
    st.info("No backtest runs found.")
    st.stop()

runs_df = pd.DataFrame(runs)
runs_df["created_at"] = pd.to_datetime(runs_df["created_at"], errors="coerce")

# Enrich list rows with summary metrics from run detail endpoint only
run_details = []
for run_id in runs_df["run_id"].tolist():
    try:
        run_details.append(fetch_json(f"/backtests/{run_id}"))
    except requests.RequestException:
        continue
if run_details:
    runs_df = pd.DataFrame(run_details)

summary_cols = [
    "run_id",
    "symbol",
    "interval",
    "config_hash",
    "dataset_fingerprint",
    "total_return",
    "final_equity",
    "max_drawdown",
    "profit_factor",
    "trade_count",
    "win_rate",
]

runs_display_df = runs_df.copy()
for col in ["total_return", "final_equity", "max_drawdown", "profit_factor", "win_rate"]:
    if col not in runs_display_df.columns:
        runs_display_df[col] = None

st.subheader("Recent Backtest Runs")
st.dataframe(
    runs_display_df[summary_cols],
    use_container_width=True,
    hide_index=True,
)

run_options = runs_df["run_id"].tolist()
selected_run = st.selectbox("Select run", run_options, index=0)

try:
    with st.spinner("Loading run details..."):
        run_detail = fetch_json(f"/backtests/{selected_run}")
        fills = fetch_json(f"/backtests/{selected_run}/fills")
        equity_curve = fetch_json(f"/backtests/{selected_run}/equity-curve")
except requests.HTTPError as exc:
    st.error(f"Failed to load run data: {exc.response.status_code} {exc.response.text}")
    st.stop()
except requests.RequestException as exc:
    st.error(f"Failed to connect to API for run data: {exc}")
    st.stop()

st.subheader("Summary Metrics")
metric_cols = st.columns(6)
metric_cols[0].metric("Total Return", f"{(run_detail.get('total_return') or 0):.4f}")
metric_cols[1].metric("Final Equity", f"{(run_detail.get('final_equity') or 0):.2f}")
metric_cols[2].metric("Max Drawdown", f"{(run_detail.get('max_drawdown') or 0):.4f}")
metric_cols[3].metric("Profit Factor", f"{(run_detail.get('profit_factor') or 0):.4f}")
metric_cols[4].metric("Trade Count", str(run_detail.get("trade_count") or 0))
metric_cols[5].metric("Win Rate", f"{(run_detail.get('win_rate') or 0):.2%}")

st.subheader("Deterministic Metadata")
meta_cols = st.columns(4)
meta_cols[0].text_input("Config Hash", value=run_detail.get("config_hash", ""), disabled=True)
meta_cols[1].text_input("Dataset Fingerprint", value=run_detail.get("dataset_fingerprint", ""), disabled=True)
meta_cols[2].text_input("Status", value=run_detail.get("status", ""), disabled=True)
meta_cols[3].text_input(
    "Deterministic Summary Timestamp",
    value=run_detail.get("deterministic_summary_timestamp") or "",
    disabled=True,
)

st.subheader("Equity Curve")
if equity_curve:
    equity_df = pd.DataFrame(equity_curve)
    equity_df["open_time"] = pd.to_datetime(equity_df["open_time"], errors="coerce")
    fig = px.line(equity_df, x="open_time", y="equity", title="Equity Over Time")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No equity curve points available for this run.")

st.subheader("Fills / Trades")
if fills:
    fills_df = pd.DataFrame(fills)
    st.dataframe(fills_df, use_container_width=True, hide_index=True)
else:
    st.info("No fills/trades available for this run.")
