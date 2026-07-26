import streamlit as st

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

display_tradingview_chart(
    data,
    high_labels=high_labels,
    low_labels=low_labels,
    bos=bos_status,
    choch=choch_status,
    height=700,
)

