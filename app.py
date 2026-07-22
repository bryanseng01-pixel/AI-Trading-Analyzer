import streamlit as st
import plotly.graph_objects as go

from data import get_market_data
from indicators import calculate_ema, get_trend
from structure import find_swing_points
from market_structure import (
    label_highs,
    label_lows,
    determine_structure,
    interpret_bias_and_structure,
)


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


# Display bias

st.subheader("Current Market Bias")

if "BULLISH" in trend:
    st.success(trend)

elif "BEARISH" in trend:
    st.error(trend)

else:
    st.warning(trend)


st.write("Swing Highs:", len(highs))
st.write("Swing Lows:", len(lows))
st.subheader("Market Structure")
st.info(structure)
if high_labels:
    latest_high_label = high_labels[-1][2]
    st.write("Latest Swing High:", latest_high_label)

if low_labels:
    latest_low_label = low_labels[-1][2]
    st.write("Latest Swing Low:", latest_low_label)
st.subheader("Market Interpretation")
st.success(market_summary)

# Create chart

fig = go.Figure()


# Candles
fig.add_trace(
    go.Candlestick(
        x=data.index,
        open=data["Open"],
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        name="Price",
        increasing_line_color="green",
        increasing_fillcolor="green",
        decreasing_line_color="red",
        decreasing_fillcolor="red"
    )
)


# EMA 50
fig.add_trace(
    go.Scatter(
        x=data.index,
        y=data["EMA50"],
        mode="lines",
        name="EMA 50"
    )
)


# Swing Highs
if highs:
    fig.add_trace(
        go.Scatter(
            x=[x[0] for x in highs[-3:]],
            y=[x[1] for x in highs[-3:]],
            mode="markers",
            marker=dict(
                size=10,
                symbol="triangle-down"
            ),
            name="Swing High"
        )
    )


# Swing Lows
if lows:
    fig.add_trace(
        go.Scatter(
            x=[x[0] for x in lows[-3:]],
            y=[x[1] for x in lows[-3:]],
            mode="markers",
            marker=dict(
                size=10,
                symbol="triangle-up"
            ),
            name="Swing Low"
        )
    )


fig.update_layout(
    height=750,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    hovermode="x unified"
)


st.plotly_chart(
    fig,
    use_container_width=True
)