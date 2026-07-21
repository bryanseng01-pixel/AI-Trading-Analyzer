import pandas as pd


def find_swing_points(data, lookback=3):

    highs = []
    lows = []

    for i in range(lookback, len(data) - lookback):

        high = data["High"].iloc[i]
        low = data["Low"].iloc[i]


        # Swing High
        if high == max(data["High"].iloc[i-lookback:i+lookback+1]):
            highs.append((data.index[i], high))


        # Swing Low
        if low == min(data["Low"].iloc[i-lookback:i+lookback+1]):
            lows.append((data.index[i], low))


    return highs, lows