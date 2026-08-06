import pandas as pd

from indicators import calculate_ema, get_trend


def test_ema_trend_is_bullish_when_latest_close_is_above_ema(ohlc_factory):
    data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
            (102, 105, 102, 104, 10),
        ]
    )

    result = calculate_ema(data.copy(), period=2)

    expected = data["Close"].ewm(span=2).mean()
    pd.testing.assert_series_equal(result["EMA50"], expected, check_names=False)
    assert get_trend(result) == "BULLISH 🟢"


def test_ema_trend_is_bearish_when_latest_close_is_below_ema(ohlc_factory):
    data = ohlc_factory(
        [
            (104, 105, 103, 104, 10),
            (104, 104, 101, 102, 10),
            (102, 102, 99, 100, 10),
        ]
    )

    result = calculate_ema(data.copy(), period=2)

    assert get_trend(result) == "BEARISH 🔴"


def test_trend_reports_no_data_for_an_empty_analyzed_frame():
    data = pd.DataFrame(columns=["Close", "EMA50"])

    assert get_trend(data) == "NO DATA"
