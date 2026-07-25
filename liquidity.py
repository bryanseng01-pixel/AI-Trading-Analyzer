def find_equal_highs(highs, tolerance=1.0):
    """
    Finds Equal Highs using swing highs.

    Returns:
        List of matching Equal High pairs.
    """

    equal_highs = []

    for i in range(1, len(highs)):
        previous = highs[i - 1]
        current = highs[i]

        if abs(current[1] - previous[1]) <= tolerance:
            equal_highs.append((previous, current))

    return equal_highs


def find_equal_lows(lows, tolerance=1.0):
    """
    Finds Equal Lows using swing lows.

    Returns:
        List of matching Equal Low pairs.
    """

    equal_lows = []

    for i in range(1, len(lows)):
        previous = lows[i - 1]
        current = lows[i]

        if abs(current[1] - previous[1]) <= tolerance:
            equal_lows.append((previous, current))

    return equal_lows