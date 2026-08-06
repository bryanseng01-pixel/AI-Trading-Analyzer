def calculate_ema(data, period=50):

    data["EMA50"] = (
        data["Close"]
        .ewm(span=period)
        .mean()
    )

    return data


def get_trend(data):

    if data.empty:
        return "NO DATA"


    latest_close = data["Close"].iloc[-1]
    latest_ema = data["EMA50"].iloc[-1]


    if latest_close > latest_ema:
        return "BULLISH 🟢"

    else:
        return "BEARISH 🔴"
