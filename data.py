import yfinance as yf
import pandas as pd


def get_market_data(symbol, timeframe):

    # 4-hour candles are created from 1-hour data
    if timeframe == "4h":
        data = yf.download(
            symbol,
            period="3mo",
            interval="1h",
            auto_adjust=False,
            progress=False,
        )

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        data = data.resample("4h").agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        ).dropna()

        return data

    # Yahoo restricts how much intraday history is available
    if timeframe == "1m":
        period = "7d"

    elif timeframe in ["5m", "15m"]:
        period = "60d"

    else:
        period = "3mo"

    data = yf.download(
        symbol,
        period=period,
        interval=timeframe,
        auto_adjust=False,
        progress=False,
    )

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data.dropna()