import streamlit as st

from data import get_market_data
from indicators import calculate_ema, get_trend


st.title("AI Trading Analyzer")


symbol = "NQ=F"


timeframes = {
    "4 Hour": "4h",
    "1 Hour": "1h",
    "15 Minute": "15m"
}


for name, timeframe in timeframes.items():

    data = get_market_data(symbol, timeframe)


    data = calculate_ema(data)

    trend = get_trend(data)

    st.subheader(name)

    st.metric("Market Bias", trend)