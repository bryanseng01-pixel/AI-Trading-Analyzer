import streamlit as st

from ai_market_coach import generate_market_summary
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

st.title("📈 AI Trading Analyzer")

st.write("Multi-Timeframe Market Bias")


symbol = "NQ=F"


timeframes = {
    "4 Hour": "4h",
    "1 Hour": "1h",
    "15 Minute": "15m"
}

bias_cols = st.columns(3)


for index, (name, timeframe) in enumerate(timeframes.items()):

    bias_data = get_market_data(symbol, timeframe)

    bias_data = calculate_ema(bias_data)

    bias = get_trend(bias_data)


    with bias_cols[index]:

        st.subheader(name)

        if "BULLISH" in bias:
            st.success(bias)

        elif "BEARISH" in bias:
            st.error(bias)

        else:
            st.warning(bias)

# CHART SELECTOR
selected = st.selectbox(
    "Chart Timeframe",
    ["4 Hour", "1 Hour", "15 Minute"]
)


 # Convert selected name into Yahoo timeframe

selected_timeframe = timeframes[selected]


# Load selected chart data

data = get_market_data(symbol, selected_timeframe)

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

# ===== AI Dashboard =====

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
    st.metric("Market Score", f"{ai_score}/100")

with coach_col2:
    st.write("**Game Plan**")
    st.info(ai_game_plan)

st.write("**Reasoning**")

for reason in ai_reasoning:
    st.write(f"• {reason}")
    
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
