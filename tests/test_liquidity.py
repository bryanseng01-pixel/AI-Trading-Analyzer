from liquidity import find_equal_highs, find_equal_lows


def test_equal_highs_and_lows_use_configured_point_tolerance(ohlc_factory):
    data = ohlc_factory([(1, 2, 0, 1, 1)] * 3)
    times = data.index

    equal_highs = find_equal_highs(
        [(times[0], 100.0), (times[1], 100.75), (times[2], 103.0)],
        tolerance=1.0,
    )
    equal_lows = find_equal_lows(
        [(times[0], 90.0), (times[1], 89.25), (times[2], 87.0)],
        tolerance=1.0,
    )

    assert len(equal_highs) == 1
    assert equal_highs[0]["type"] == "buy_side"
    assert equal_highs[0]["level"] == 100.0
    assert len(equal_lows) == 1
    assert equal_lows[0]["type"] == "sell_side"
    assert equal_lows[0]["level"] == 90.0
