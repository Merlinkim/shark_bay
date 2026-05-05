import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

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


LIVE_WINDOWS = {
    "1h": 60,
    "6h": 360,
    "24h": 1440,
    "7d": 10080,
}

page = st.sidebar.radio("Page", ["Run Backtest", "Backtest Explorer", "Live Market Chart"])

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
    st.caption(strategy_meta.get("description", "No strategy description available."))

    param_specs = dict(strategy_meta.get("parameter_schema", {}))
    defaults = dict(strategy_meta.get("default_parameters", {}))

    for param_name, spec in param_specs.items():
        if spec.get("type") == "int":
            strategy_params[param_name] = st.number_input(
                param_name,
                min_value=int(spec.get("min", 1)),
                max_value=int(spec.get("max", 10000)),
                value=int(defaults.get(param_name, spec.get("default", 1))),
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

elif page == "Backtest Explorer":
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

    st.subheader("Compare Saved Runs")
    run_options = runs_df["run_id"].astype(str).tolist() if "run_id" in runs_df.columns else []
    selected_run_ids = st.multiselect(
        "Select runs to compare",
        options=run_options,
        default=run_options[: min(2, len(run_options))],
    )

    if selected_run_ids:
        selected_df = runs_df[runs_df["run_id"].astype(str).isin(selected_run_ids)].copy()
        comparison_columns = [
            "run_id",
            "strategy_name",
            "config_hash",
            "dataset_fingerprint",
            "total_return",
            "final_equity",
            "max_drawdown",
            "profit_factor",
            "trade_count",
            "win_rate",
        ]
        for col in comparison_columns:
            if col not in selected_df.columns:
                selected_df[col] = None
        st.table(selected_df[comparison_columns].sort_values("run_id"))

        focus_run_id = selected_run_ids[0]
        st.subheader(f"Run Details: {focus_run_id}")
        try:
            run_detail = fetch_json(f"/backtests/{focus_run_id}")
            fills = fetch_json(f"/backtests/{focus_run_id}/fills")
            equity_curve = fetch_json(f"/backtests/{focus_run_id}/equity-curve")
        except requests.RequestException as exc:
            st.error(f"Failed to load selected run details: {exc}")
        else:
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
    st.subheader("Live Market Chart")
    st.caption("Read-only live BTCUSDT 1m market data view.")

    with st.sidebar:
        st.subheader("Live Chart Options")
        selected_window = st.selectbox("Recent Window", options=list(LIVE_WINDOWS.keys()), index=1)
        refresh_seconds = st.slider("Refresh interval (seconds)", min_value=3, max_value=60, value=5, step=1)
        auto_refresh = st.checkbox("Auto-refresh", value=True)

    if auto_refresh:
        st.query_params["_market_ts"] = datetime.now(timezone.utc).isoformat()
        st.markdown(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", unsafe_allow_html=True)

    limit = LIVE_WINDOWS[selected_window]
    try:
        payload = fetch_json(f"/candles?symbol=BTCUSDT&interval=1m&limit={limit}")
    except Exception as exc:
        st.error(f"Failed to load candles: {exc}")
        st.stop()

    candles = payload.get("candles", [])
    if not candles:
        st.info("No candle data available yet.")
        st.stop()

    df = pd.DataFrame(candles)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("open_time").dropna(subset=["open_time", "open", "high", "low", "close", "volume"])
    if df.empty:
        st.warning("Candle data is malformed or empty after parsing.")
        st.stop()

    latest_candle_ts = df["open_time"].iloc[-1]
    lag_seconds = max((datetime.now(timezone.utc) - latest_candle_ts.to_pydatetime()).total_seconds(), 0)

    metric_cols = st.columns(3)
    metric_cols[0].metric("Latest Candle (UTC)", latest_candle_ts.strftime("%Y-%m-%d %H:%M:%S"))
    metric_cols[1].metric("Candles in Window", f"{len(df)}")
    metric_cols[2].metric("Data Lag", f"{lag_seconds:.1f}s")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.75, 0.25])
    fig.add_trace(
        go.Candlestick(
            x=df["open_time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="BTCUSDT 1m",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df["open_time"],
            y=df["volume"],
            name="Volume",
            marker_color="#4C78A8",
            opacity=0.8,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"BTCUSDT 1m Candles ({selected_window})",
        xaxis_rangeslider_visible=False,
        legend_orientation="h",
        legend_y=1.02,
        margin=dict(l=20, r=20, t=60, b=20),
        height=700,
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)
