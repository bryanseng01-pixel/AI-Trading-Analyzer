def label_highs(highs):
    """
    Labels swing highs as HH or LH.

    Returns:
        List of tuples:
        (timestamp, price, label)
    """

    labeled = []

    if len(highs) < 2:
        return labeled

    for i in range(1, len(highs)):
        previous = highs[i - 1]
        current = highs[i]

        if current[1] > previous[1]:
            label = "HH"
        else:
            label = "LH"

        labeled.append((current[0], current[1], label))

    return labeled


def label_lows(lows):
    """
    Labels swing lows as HL or LL.
    """

    labeled = []

    if len(lows) < 2:
        return labeled

    for i in range(1, len(lows)):
        previous = lows[i - 1]
        current = lows[i]

        if current[1] > previous[1]:
            label = "HL"
        else:
            label = "LL"

        labeled.append((current[0], current[1], label))

    return labeled


def determine_structure(high_labels, low_labels):
    """
    Determines the overall market structure
    using the latest swing labels.
    """

    if not high_labels or not low_labels:
        return "Not enough data"

    last_high = high_labels[-1][2]
    last_low = low_labels[-1][2]

    if last_high == "HH" and last_low == "HL":
        return "Bullish Structure"

    if last_high == "LH" and last_low == "LL":
        return "Bearish Structure"

    return "Range / Transition"

def interpret_bias_and_structure(trend, structure):
    """
    Combines EMA trend and market structure into a readable explanation.
    """

    if "BEARISH" in trend and structure == "Bullish Structure":
        return "Bullish pullback inside a bearish trend"

    if "BULLISH" in trend and structure == "Bearish Structure":
        return "Bearish pullback inside a bullish trend"

    if "BULLISH" in trend and structure == "Bullish Structure":
        return "Bullish trend confirmed"

    if "BEARISH" in trend and structure == "Bearish Structure":
        return "Bearish trend confirmed"

    return "Mixed or transitioning market conditions"

def detect_bos(data, high_labels, low_labels, structure):
    """
    Detects continuation Break of Structure.

    Bullish structure:
        Close above the previous swing high = Bullish BOS

    Bearish structure:
        Close below the previous swing low = Bearish BOS
    """

    if data.empty:
        return "No BOS detected"

    # Bullish continuation BOS
    if structure == "Bullish Structure" and len(high_labels) >= 2:
        previous_high_time = high_labels[-2][0]
        previous_high_price = high_labels[-2][1]

        candles_after_high = data[data.index > previous_high_time]

        broken_candles = candles_after_high[
            candles_after_high["Close"] > previous_high_price
        ]

        if not broken_candles.empty:
            break_time = broken_candles.index[0]
            return f"Bullish BOS detected at {break_time}"

    # Bearish continuation BOS
    if structure == "Bearish Structure" and len(low_labels) >= 2:
        previous_low_time = low_labels[-2][0]
        previous_low_price = low_labels[-2][1]

        candles_after_low = data[data.index > previous_low_time]

        broken_candles = candles_after_low[
            candles_after_low["Close"] < previous_low_price
        ]

        if not broken_candles.empty:
            break_time = broken_candles.index[0]
            return f"Bearish BOS detected at {break_time}"

    return "No BOS detected"