def detect_order_blocks(data):
    """
    Detect simple ICT-style Order Blocks.

    Returns:
        List of bullish and bearish order blocks.
    """

    order_blocks = []

    if len(data) < 5:
        return order_blocks

    for i in range(2, len(data) - 2):

        candle = data.iloc[i]

        # Bullish candle
        if candle["Close"] > candle["Open"]:

            previous = data.iloc[i - 1]

            if previous["Close"] < previous["Open"]:

                order_blocks.append(
                    {
                        "type": "bullish",
                        "time": data.index[i - 1],
                        "top": float(previous["High"]),
                        "bottom": float(previous["Low"]),
                    }
                )

        # Bearish candle
        elif candle["Close"] < candle["Open"]:

            previous = data.iloc[i - 1]

            if previous["Close"] > previous["Open"]:

                order_blocks.append(
                    {
                        "type": "bearish",
                        "time": data.index[i - 1],
                        "top": float(previous["High"]),
                        "bottom": float(previous["Low"]),
                    }
                )

    return order_blocks