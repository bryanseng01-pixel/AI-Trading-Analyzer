from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from analysis_pipeline import analyze_timeframe, select_active_fvgs
from authority_market_story import build_authority_market_story
from confluence import evaluate_confluence
from dashboard import render_market_brief, render_setup_progress
from data import get_market_data
from decision_authority import DecisionAuthority
from fvg_lifecycle import evaluate_fvg_lifecycles
from ifvg_integration import build_ifvg_confluence_factor
from market_structure import interpret_bias_and_structure
from sessions import detect_session_levels
from setup_overlay import build_setup_overlay
from tradingview_chart import display_tradingview_chart


st.set_page_config(
    page_title="AI Trading Analyzer",
    page_icon="📈",
    layout="wide",
)
st.sidebar.title("⚙️ Chart Settings")
st.sidebar.subheader("FVG Settings")
minimum_fvg_size = st.sidebar.number_input(
    "Minimum FVG Size (points)",
    min_value=0.25,
    max_value=100.0,
    value=5.0,
    step=0.25,
)
maximum_fvgs = st.sidebar.slider(
    "Maximum Active FVGs",
    min_value=1,
    max_value=10,
    value=3,
)
if st.sidebar.button("🔄 Refresh Market Data"):
    st.cache_data.clear()
    st.rerun()

st.title("📈 AI Trading Analyzer")
last_updated = datetime.now(ZoneInfo("America/New_York"))
st.caption("Last refreshed: " + last_updated.strftime("%I:%M:%S %p ET"))

symbol = "NQ=F"
timeframes = {
    "4 Hour": {"interval": "4h", "role": "🧭 Context"},
    "1 Hour": {"interval": "1h", "role": "✅ Context"},
    "15 Minute": {"interval": "15m", "role": "📈 Setup"},
    "5 Minute": {"interval": "5m", "role": "🔍 Confirmation"},
    "1 Minute": {"interval": "1m", "role": "⚡ Trigger"},
}

st.write("Preliminary EMA Context Only")
st.caption(
    "4H/1H EMA establishes preliminary context; 5M/1M confirmation "
    "requires actual close-confirmed BOS/CHoCH."
)

timeframe_analyses = {}
bias_cols = st.columns(len(timeframes))
for index, (name, info) in enumerate(timeframes.items()):
    analysis = analyze_timeframe(
        get_market_data(symbol, info["interval"]),
        info["interval"],
    )
    timeframe_analyses[name] = analysis

    with bias_cols[index]:
        st.caption(info["role"])
        st.markdown(f"**{name}**")
        if "BULLISH" in analysis.trend:
            st.success(analysis.trend)
        elif "BEARISH" in analysis.trend:
            st.error(analysis.trend)
        else:
            st.warning(analysis.trend)

selected = st.selectbox("Chart Timeframe", list(timeframes))
selected_analysis = timeframe_analyses[selected]
context_analysis = timeframe_analyses["4 Hour"]
execution_analysis = timeframe_analyses["1 Minute"]

session_levels = (
    detect_session_levels(timeframe_analyses["5 Minute"].data) or {}
)
authority_decision = DecisionAuthority().evaluate(
    timeframe_analyses,
    session_levels,
    minimum_fvg_size=minimum_fvg_size,
    maximum_fvgs=maximum_fvgs,
)
fvg_lifecycle_result = evaluate_fvg_lifecycles(
    execution_analysis.data,
    execution_analysis.fvgs,
    timeframe="1m",
)
setup_overlay = build_setup_overlay(
    authority_decision,
    timeframe_analyses,
    session_levels,
    fvg_lifecycle_result=fvg_lifecycle_result,
    minimum_ifvg_size=minimum_fvg_size,
)
ifvg_confluence_factor = build_ifvg_confluence_factor(setup_overlay)
confluence_result = evaluate_confluence(
    authority_decision,
    setup_overlay,
    contributed_factors=(ifvg_confluence_factor,),
)
trade_plan = authority_decision.trade_plan
playbook = authority_decision.playbook
market_story = build_authority_market_story(authority_decision.roles)

render_market_brief(trade_plan, market_story, playbook)

st.subheader(f"📊 Displayed Chart — {selected}")
chart_active_fvgs = select_active_fvgs(
    selected_analysis,
    minimum_size=minimum_fvg_size,
    maximum_count=maximum_fvgs,
)
display_tradingview_chart(
    selected_analysis.data,
    setup_overlay=setup_overlay,
    height=700,
)

render_setup_progress(trade_plan)

st.subheader("▫️ 1M Execution FVG Context")
st.caption(
    "These active 1M zones feed the authority execution-zone gate; "
    "they are independent of the displayed chart timeframe."
)
fvg_col1, fvg_col2 = st.columns(2)
fvg_col1.metric(
    "Bullish Active 1M FVGs",
    sum(fvg["type"] == "bullish" for fvg in authority_decision.active_fvgs),
)
fvg_col2.metric(
    "Bearish Active 1M FVGs",
    sum(fvg["type"] == "bearish" for fvg in authority_decision.active_fvgs),
)

with st.expander("📊 Technical Diagnostics", expanded=False):
    st.write("### 4H Context Diagnostics")
    context_cols = st.columns(4)
    context_cols[0].metric("4H EMA Trend", context_analysis.trend)
    context_cols[1].metric("4H Structure", context_analysis.structure)
    context_cols[2].metric(
        "4H BOS",
        context_analysis.bos["direction"] if context_analysis.bos else "None",
    )
    context_cols[3].metric(
        "4H CHoCH",
        context_analysis.choch["direction"]
        if context_analysis.choch
        else "None",
    )
    st.write(
        f"4H equal highs/lows: {len(context_analysis.equal_highs)} / "
        f"{len(context_analysis.equal_lows)}"
    )
    st.write(
        f"4H swing highs/lows: {len(context_analysis.highs)} / "
        f"{len(context_analysis.lows)}"
    )

    st.write(f"### Displayed-Chart Diagnostics — {selected}")
    display_cols = st.columns(4)
    display_cols[0].metric("Displayed EMA Trend", selected_analysis.trend)
    display_cols[1].metric("Displayed Structure", selected_analysis.structure)
    display_cols[2].metric(
        "Displayed BOS",
        selected_analysis.bos["direction"] if selected_analysis.bos else "None",
    )
    display_cols[3].metric(
        "Displayed CHoCH",
        selected_analysis.choch["direction"]
        if selected_analysis.choch
        else "None",
    )
    st.write(
        "Displayed equal highs/lows: "
        f"{len(selected_analysis.equal_highs)} / "
        f"{len(selected_analysis.equal_lows)}"
    )
    st.write(f"Displayed active FVGs: {len(chart_active_fvgs)}")

with st.expander("🌍 Session Liquidity", expanded=False):
    session_columns = st.columns(3)
    for index, session_name in enumerate(["Asia", "London", "New York"]):
        with session_columns[index]:
            session = session_levels.get(session_name)
            if session is None:
                st.info(f"{session_name}: No data")
                continue

            high_status = "Swept" if session["high_swept"] else "Untouched"
            low_status = "Swept" if session["low_swept"] else "Untouched"
            st.metric(
                f"{session_name} High",
                f'{session["high"]:.2f}',
                delta=high_status,
            )
            st.metric(
                f"{session_name} Low",
                f'{session["low"]:.2f}',
                delta=low_status,
            )

with st.expander("🧪 Legacy Diagnostics", expanded=False):
    st.warning(
        "Non-authoritative legacy diagnostics. These values do not control "
        "status, confidence, setup progress, or recommendations."
    )
    st.write("**Legacy 4H market summary**")
    st.write(
        interpret_bias_and_structure(
            context_analysis.trend,
            context_analysis.structure,
        )
    )
    st.write("**Raw 4H market snapshot**")
    st.write(
        {
            "trend": context_analysis.trend,
            "structure": context_analysis.structure,
            "bos": context_analysis.bos,
            "choch": context_analysis.choch,
            "equal_highs": len(context_analysis.equal_highs),
            "equal_lows": len(context_analysis.equal_lows),
        }
    )
