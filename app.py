import streamlit as st

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