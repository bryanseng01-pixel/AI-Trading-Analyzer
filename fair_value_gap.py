def detect_fair_value_gaps(data):
    """
    Detect bullish and bearish Fair Value Gaps.

    Returns:
        A list of FVG dictionaries, including whether each gap
        has already been mitigated.
    """

    fvgs = []

    if data is None or len(data) < 3:
        return fvgs

    for i in range(1, len(data) - 1):
        previous = data.iloc[i - 1]
        next_candle = data.iloc[i + 1]

        # Bullish FVG
        if previous["High"] < next_candle["Low"]:
            top = float(next_candle["Low"])
            bottom = float(previous["High"])

            candles_after = data.iloc[i + 2 :]

            mitigated = False

            if not candles_after.empty:
                mitigated = bool(
                    (candles_after["Low"] <= bottom).any()
                )

            fvgs.append(
                {
                    "type": "bullish",
                    "start_time": data.index[i - 1],
                    "end_time": data.index[i + 1],
                    "top": top,
                    "bottom": bottom,
                    "mitigated": mitigated,
                }
            )

        # Bearish FVG
        elif previous["Low"] > next_candle["High"]:
            top = float(previous["Low"])
            bottom = float(next_candle["High"])

            candles_after = data.iloc[i + 2 :]

            mitigated = False

            if not candles_after.empty:
                mitigated = bool(
                    (candles_after["High"] >= top).any()
                )

            fvgs.append(
                {
                    "type": "bearish",
                    "start_time": data.index[i - 1],
                    "end_time": data.index[i + 1],
                    "top": top,
                    "bottom": bottom,
                    "mitigated": mitigated,
                }
            )

    return fvgs