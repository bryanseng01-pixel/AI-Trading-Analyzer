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