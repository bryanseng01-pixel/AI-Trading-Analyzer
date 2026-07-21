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


cols = st.columns(3)


for index, (name, timeframe) in enumerate(timeframes.items()):

    data = get_market_data(symbol, timeframe)

    data = calculate_ema(data)

    trend = get_trend(data)

    highs, lows = find_swing_points(data)



    with cols[index]:

        st.subheader(name)

        if "BULLISH" in trend:
            st.success(trend)

        elif "BEARISH" in trend:
            st.error(trend)

        else:
            st.warning(trend)

        st.write("Swing Highs:", len(highs))
        st.write("Swing Lows:", len(lows))


        fig = go.Figure()

        # 1. Candlesticks
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


        #EMA 50
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data["EMA50"],
                mode="lines",
                name="EMA 50"
            )
        )

        # Swing High markers
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


        # Swing Low markers
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
            height=650,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
            margin=dict(
                l=20,
                r=20,
                t=50,
                b=20
            ),
            xaxis=dict(
                showgrid=False,
                showspikes=True,
                spikemode="across",
                spikesnap="cursor"
            ),
            yaxis=dict(
                showgrid=True,
                showspikes=True,
                spikemode="across"
            )
        )


        st.plotly_chart(
            fig,
            use_container_width=True
        )