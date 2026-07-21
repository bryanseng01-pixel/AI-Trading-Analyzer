import streamlit as st
import plotly.graph_objects as go

from data import get_market_data
from indicators import calculate_ema, get_trend


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


cols = st.columns(3)


for index, (name, timeframe) in enumerate(timeframes.items()):

    data = get_market_data(symbol, timeframe)

    data = calculate_ema(data)

    trend = get_trend(data)


    with cols[index]:

        st.subheader(name)

        if "BULLISH" in trend:
            st.success(trend)

        elif "BEARISH" in trend:
            st.error(trend)

        else:
            st.warning(trend)
            
        fig = go.Figure()

        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data["Open"],
                high=data["High"],
                low=data["Low"],
                close=data["Close"],
                name="Price"
            )
        )


        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data["EMA50"],
                mode="lines",
                name="EMA 50"
            )
        )


        fig.update_layout(
            height=400,
            xaxis_rangeslider_visible=False,
            title=f"{name} Chart"
        )


        st.plotly_chart(
            fig,
            use_container_width=True
        )