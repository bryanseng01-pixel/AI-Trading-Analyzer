from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from analysis_pipeline import select_active_fvgs
from dashboard import (
    render_authority_summary,
    render_chart_workspace,
    render_confluence_panel,
    render_current_setup,
    render_diagnostics,
    render_setup_timeline,
    render_top_bar,
)
from data import get_market_data
from instrument_pipeline import AnalysisSettings, TIMEFRAMES, build_instrument_analysis
from instruments import INSTRUMENT_REGISTRY
from workstation_view import build_trading_workstation_view


st.set_page_config(
    page_title="AI Trading Workstation",
    page_icon="📈",
    layout="wide",
)

st.title("📈 AI Trading Workstation")
instrument_column, timeframe_column, refresh_column = st.columns((1, 1.4, 0.6))
with instrument_column:
    instrument_key = st.radio(
        "Instrument",
        options=INSTRUMENT_REGISTRY.keys,
        horizontal=True,
    )
instrument = INSTRUMENT_REGISTRY.resolve(instrument_key)
with timeframe_column:
    selected = st.selectbox("Chart Timeframe", list(TIMEFRAMES))
with refresh_column:
    st.caption("Market Data")
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

with st.sidebar:
    st.header("Workstation Settings")
    st.caption(f"Selected instrument: {instrument.display_name}")
    minimum_fvg_size = st.number_input(
        "Minimum FVG Size (points)",
        min_value=instrument.tick_size,
        max_value=100.0,
        value=instrument.strategy_defaults.minimum_fvg_size_points,
        step=instrument.tick_size,
    )
    maximum_fvgs = st.slider(
        "Maximum Active FVGs",
        min_value=1,
        max_value=10,
        value=instrument.strategy_defaults.maximum_active_fvgs,
    )
    st.caption(
        "The chart timeframe is display-only. Instrument selection rebuilds "
        "the complete strategy bundle."
    )

market_frames = {
    info["interval"]: get_market_data(instrument.key, info["interval"])
    for info in TIMEFRAMES.values()
}
bundle = build_instrument_analysis(
    instrument,
    market_frames,
    AnalysisSettings(
        minimum_fvg_size=minimum_fvg_size,
        maximum_fvgs=maximum_fvgs,
    ),
)
selected_analysis = bundle.timeframe_analyses[selected]
refreshed_at = pd.Timestamp(datetime.now(ZoneInfo(instrument.display_timezone)))
view = build_trading_workstation_view(
    bundle,
    selected_chart_timeframe=selected,
    refreshed_at=refreshed_at,
)

render_top_bar(view)
render_authority_summary(view)
render_current_setup(view)
render_chart_workspace(
    view,
    selected_analysis,
    setup_overlay=bundle.setup_overlay,
)
render_setup_timeline(view)
render_confluence_panel(view)

chart_active_fvgs = select_active_fvgs(
    selected_analysis,
    minimum_size=minimum_fvg_size,
    maximum_count=maximum_fvgs,
)
render_diagnostics(
    bundle,
    selected_analysis,
    displayed_active_fvgs=len(chart_active_fvgs),
)
