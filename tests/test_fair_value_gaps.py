from fair_value_gap import detect_fair_value_gaps


def test_bullish_fvg_formation_uses_first_high_and_third_low(ohlc_factory):
    data = ohlc_factory(
        [
            (99, 101, 98, 100, 10),
            (100, 106, 99, 105, 10),
            (104, 107, 103, 106, 10),
        ]
    )

    result = detect_fair_value_gaps(data)

    assert len(result) == 1
    assert result[0]["type"] == "bullish"
    assert result[0]["bottom"] == 101.0
    assert result[0]["top"] == 103.0


def test_bearish_fvg_formation_uses_first_low_and_third_high(ohlc_factory):
    data = ohlc_factory(
        [
            (106, 107, 104, 105, 10),
            (105, 106, 99, 100, 10),
            (100, 102, 98, 99, 10),
        ]
    )

    result = detect_fair_value_gaps(data)

    assert len(result) == 1
    assert result[0]["type"] == "bearish"
    assert result[0]["bottom"] == 102.0
    assert result[0]["top"] == 104.0
