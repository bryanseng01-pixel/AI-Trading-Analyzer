import streamlit as st

from ict_playbook import evaluate_ict_liquidity_sweep_playbook
from dashboard import render_market_brief
from decision_engine import build_trade_plan
from sessions import detect_session_levels
from trade_checklist import generate_trade_checklist
from ai_market_coach import (
    generate_market_summary,
    build_market_story,
)
from fair_value_gap import detect_fair_value_gaps
from data import get_market_data
from indicators import calculate_ema, get_trend
from structure import find_swing_points
from market_structure import (
    label_highs,
    label_lows,
    determine_structure,
    interpret_bias_and_structure,
    detect_bos,
    detect_choch,
)
from liquidity import (
    find_equal_highs,
    find_equal_lows,
)
from tradingview_chart import display_tradingview_chart

from datetime import datetime
from zoneinfo import ZoneInfo

# Page settings
st.set_page_config(
    page_title="AI Trading Analyzer",
    page_icon="📈",
    layout="wide"
)
st.sidebar.title("⚙️ Chart Settings")

labels_to_show = st.sidebar.slider(
    "Swing Labels",
    min_value=2,
    max_value=20,
    value=6,
    step=1,
)

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
last_updated = datetime.now(
    ZoneInfo("America/New_York")
)

st.caption(
    "Last refreshed: "
    + last_updated.strftime("%I:%M:%S %p ET")
)

st.write("Multi-Timeframe Market Bias")


symbol = "NQ=F"


timeframes = {
    "4 Hour": {
        "interval": "4h",
        "role": "🧭 Context",
    },
    "1 Hour": {
        "interval": "1h",
        "role": "✅ Confirmation",
    },
    "15 Minute": {
        "interval": "15m",
        "role": "📈 Setup",
    },
    "5 Minute": {
        "interval": "5m",
        "role": "🔍 Confirmation",
    },
    "1 Minute": {
        "interval": "1m",
        "role": "⚡ Trigger",
    },
}

timeframe_results = {}

bias_cols = st.columns(len(timeframes))

for index, (name, info) in enumerate(timeframes.items()):

    timeframe = info["interval"]
    role = info["role"]

    bias_data = get_market_data(symbol, timeframe)
    bias_data = calculate_ema(bias_data)
    bias = get_trend(bias_data)

    timeframe_results[name] = {
        "timeframe": timeframe,
        "trend": bias,
        "data": bias_data,
        "role": role,
    }

    with bias_cols[index]:

        st.caption(role)
        st.markdown(f"**{name}**")

        if "BULLISH" in bias:
            st.success(bias)

        elif "BEARISH" in bias:
            st.error(bias)

        else:
            st.warning(bias)

market_story = build_market_story(timeframe_results)



# CHART SELECTOR
selected = st.selectbox(
    "Chart Timeframe",
    [
        "4 Hour",
        "1 Hour",
        "15 Minute",
        "5 Minute",
        "1 Minute",
    ],
)


 # Convert selected name into Yahoo timeframe

selected_timeframe = timeframes[selected]["interval"]

data = get_market_data(
    symbol,
    selected_timeframe,
)

data = calculate_ema(data)

trend = get_trend(data)

highs, lows = find_swing_points(data)

equal_highs = find_equal_highs(highs, tolerance=5.0)
equal_lows = find_equal_lows(lows, tolerance=5.0)

high_labels = label_highs(highs)
low_labels = label_lows(lows)

structure = determine_structure(
    high_labels,
    low_labels,
)
market_summary = interpret_bias_and_structure(
    trend,
    structure,
)
bos_status = detect_bos(
    data,
    high_labels,
    low_labels,
    structure,
)
choch_status = detect_choch(
    data,
    high_labels,
    low_labels,
    structure,
)

fvgs = detect_fair_value_gaps(data)
session_data = get_market_data(symbol, "5m")
session_levels = detect_session_levels(session_data) or {}

current_price = float(data["Close"].iloc[-1])

active_fvgs = [
    fvg
    for fvg in fvgs
    if not fvg["mitigated"]
    and (fvg["top"] - fvg["bottom"]) >= minimum_fvg_size
]

active_fvgs.sort(
    key=lambda fvg: abs(
        ((fvg["top"] + fvg["bottom"]) / 2) - current_price
    )
)

active_fvgs = active_fvgs[:maximum_fvgs]

bullish_active_fvgs = [
    fvg for fvg in active_fvgs
    if fvg["type"] == "bullish"
]

bearish_active_fvgs = [
    fvg for fvg in active_fvgs
    if fvg["type"] == "bearish"
]

ai_reasoning, ai_confidence, ai_score, ai_game_plan = (
    generate_market_summary(
        trend,
        structure,
        bos_status,
        choch_status,
        bullish_active_fvgs,
        bearish_active_fvgs,
        equal_highs,
        equal_lows,
    )
)
trade_plan = build_trade_plan(
    trend,
    structure,
    bos_status,
    choch_status,
    bullish_active_fvgs,
    bearish_active_fvgs,
    session_levels,
)
htf_bias = market_story["context"]

setup_structure = (
    "bullish"
    if "BULLISH" in timeframe_results["15 Minute"]["trend"]
    else "bearish"
    if "BEARISH" in timeframe_results["15 Minute"]["trend"]
    else "mixed"
)

confirmation_structure = (
    "bullish"
    if "BULLISH" in timeframe_results["5 Minute"]["trend"]
    else "bearish"
    if "BEARISH" in timeframe_results["5 Minute"]["trend"]
    else "mixed"
)

trigger_structure = (
    "bullish"
    if "BULLISH" in timeframe_results["1 Minute"]["trend"]
    else "bearish"
    if "BEARISH" in timeframe_results["1 Minute"]["trend"]
    else "mixed"
)

ict_playbook = evaluate_ict_liquidity_sweep_playbook(
    htf_bias=htf_bias,
    setup_structure=setup_structure,
    confirmation_structure=confirmation_structure,
    trigger_structure=trigger_structure,
    active_fvgs=active_fvgs,
    session_levels=session_levels,
)
st.subheader("🎯 ICT Playbook")

playbook_col1, playbook_col2, playbook_col3 = st.columns(3)

with playbook_col1:
    st.metric(
        "Playbook",
        ict_playbook["playbook"],
    )

with playbook_col2:
    st.metric(
        "Direction",
        ict_playbook["direction"] or "None",
    )

with playbook_col3:
    st.metric(
        "Status",
        ict_playbook["status"],
    )

st.write(f'**Current Phase:** {ict_playbook["phase"]}')

st.info(
    "Next Event: "
    + ict_playbook["next_event"]
)

with st.expander("ICT Setup Details"):
    if ict_playbook["reasons"]:
        st.write("**Confirmed:**")

        for reason in ict_playbook["reasons"]:
            st.markdown(f"✅ {reason}")

    if ict_playbook["missing"]:
        st.write("**Still Missing:**")

        for item in ict_playbook["missing"]:
            st.markdown(f"⏳ {item}")
render_market_brief(
    trade_plan,
    market_story,
    ict_playbook,
)
trade_checklist, readiness_score, recommendation = (
    generate_trade_checklist(
        trend,
        structure,
        bos_status,
        choch_status,
        bullish_active_fvgs,
        bearish_active_fvgs,
    )
)

market_snapshot = {
    "trend": trend,
    "structure": structure,
    "bos": bos_status,
    "choch": choch_status,
    "bullish_fvgs": bullish_active_fvgs,
    "bearish_fvgs": bearish_active_fvgs,
    "equal_highs": equal_highs,
    "equal_lows": equal_lows,
}

# ===== AI Dashboard =====

with st.expander("📊 Technical Details", expanded=False):

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.subheader("Trend")

        if "BULLISH" in trend:
            st.success(trend)
        elif "BEARISH" in trend:
            st.error(trend)
        else:
            st.warning(trend)


    with col2:
        st.subheader("Structure")
        st.info(structure)


    with col3:
        st.subheader("BOS")

        if bos_status is None:
            st.info("No BOS detected")

        elif bos_status["direction"] == "bullish":
            st.success(
                f'Bullish BOS at {bos_status["time"]}'
            )

        elif bos_status["direction"] == "bearish":
            st.error(
                f'Bearish BOS at {bos_status["time"]}'
            )


    with col4:
        st.subheader("CHoCH")

        if choch_status is None:
            st.info("No CHoCH detected")

        elif choch_status["direction"] == "bullish":
            st.success(
                f'Bullish CHoCH at {choch_status["time"]}'
            )

        elif choch_status["direction"] == "bearish":
            st.error(
                f'Bearish CHoCH at {choch_status["time"]}'
            )


st.subheader("🧠 AI Market Summary")
st.info(market_summary)

st.subheader("Liquidity")

st.write(f"Equal Highs Found: {len(equal_highs)}")
st.write(f"Equal Lows Found: {len(equal_lows)}")

st.write(f"Swing Highs: {len(highs)}")
st.write(f"Swing Lows: {len(lows)}")

if high_labels:
    st.write(f"Latest Swing High: {high_labels[-1][2]}")

if low_labels:
    st.write(f"Latest Swing Low: {low_labels[-1][2]}")

st.subheader("TradingView-Style Chart")


st.subheader("Fair Value Gaps")

bullish_fvgs = [
    fvg for fvg in fvgs
    if fvg["type"] == "bullish"
    and not fvg["mitigated"]
]

bearish_fvgs = [
    fvg for fvg in fvgs
    if fvg["type"] == "bearish"
    and not fvg["mitigated"]
]

col1, col2 = st.columns(2)

with col1:
    st.metric("Bullish", len(bullish_fvgs))

with col2:
    st.metric("Bearish", len(bearish_fvgs))

st.subheader("🧠 AI Market Coach")

coach_col1, coach_col2 = st.columns(2)

with coach_col1:
    st.metric("Confidence", ai_confidence)

    st.progress(ai_score / 100)

    st.metric(
        "Market Score",
        f"{ai_score}/100"
    )

with coach_col2:
    st.write("**Game Plan**")
    st.success(
        "🎯 Today's Plan\n\n"
        + ai_game_plan
    )


st.write("### Key Reasons")

for reason in ai_reasoning:
    st.markdown(f"✅ {reason}")

st.subheader("📋 Trade Readiness")

readiness_col1, readiness_col2 = st.columns(2)

with readiness_col1:
    for item_name, is_ready in trade_checklist:
        if is_ready:
            st.markdown(f"✅ **{item_name}**")
        else:
            st.markdown(f"❌ **{item_name}**")

with readiness_col2:
    st.metric(
        "Readiness Score",
        f"{readiness_score}/100",
    )

    st.progress(readiness_score / 100)

    if recommendation == "TRADE":
        st.success("Recommendation: TRADE")

    elif recommendation == "WATCH":
        st.warning("Recommendation: WATCH")

    else:
        st.error("Recommendation: WAIT")

st.subheader("Session Liquidity")

session_columns = st.columns(3)

session_names = ["Asia", "London", "New York"]

for index, session_name in enumerate(session_names):
    with session_columns[index]:
        session = session_levels.get(session_name)

        if session is None:
            st.info(f"{session_name}: No data")

        else:
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

st.subheader("🧠 Decision Engine")

decision_col1, decision_col2, decision_col3 = st.columns(3)

with decision_col1:
    st.metric("Status", trade_plan["status"])

with decision_col2:
    st.metric("Bias", trade_plan["bias"])

with decision_col3:
    st.metric(
        "Confidence",
        f'{trade_plan["confidence"]}/100',
    )

st.progress(trade_plan["confidence"] / 100)

st.write("**Next Action**")
st.info(trade_plan["next_action"])

with st.expander("Why this decision?"):
    for reason in trade_plan["reasons"]:
        st.markdown(f"✅ {reason}")

    if trade_plan["missing"]:
        st.write("**Still missing:**")

        for item in trade_plan["missing"]:
            st.markdown(f"⏳ {item}")

display_tradingview_chart(
    data,
    high_labels=high_labels[-labels_to_show:],
    low_labels=low_labels[-labels_to_show:],
    bos=bos_status,
    choch=choch_status,
    equal_highs=equal_highs[-3:],
    equal_lows=equal_lows[-3:],
    fvgs=active_fvgs,
    height=700,
)
