import streamlit as st
import plotly.graph_objects as go

from data import get_market_data
from indicators import calculate_ema, get_trend
from structure import find_swing_points


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
        increasing_line_width=2,
        decreasing_line_width=2,
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