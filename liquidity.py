def find_equal_highs(highs, tolerance=1.0):
    """
    Finds Equal Highs.
    """

    equal_highs = []

    for i in range(1, len(highs)):

        previous = highs[i - 1]
        current = highs[i]

        if abs(current[1] - previous[1]) <= tolerance:

            equal_highs.append(
                {
                    "type": "buy_side",
                    "start_time": previous[0],
                    "end_time": current[0],
                    "level": previous[1],
                }
            )

    return equal_highs


def find_equal_lows(lows, tolerance=1.0):
    """
    Finds Equal Lows.
    """

    equal_lows = []

    for i in range(1, len(lows)):

        previous = lows[i - 1]
        current = lows[i]

        if abs(current[1] - previous[1]) <= tolerance:

            equal_lows.append(
                {
                    "type": "sell_side",
                    "start_time": previous[0],
                    "end_time": current[0],
                    "level": previous[1],
                }
            )

    return equal_lows