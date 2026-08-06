from dataclasses import replace

from analysis_pipeline import (
    TimeframeAnalysis,
    analyze_timeframe,
    select_active_fvgs,
)


def test_analyze_timeframe_returns_a_complete_independent_result(ohlc_factory):
    source = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
            (102, 102, 98, 99, 10),
            (99, 105, 99, 104, 10),
            (104, 104, 97, 98, 10),
            (98, 106, 98, 105, 10),
            (105, 108, 100, 107, 10),
        ]
    )

    result = analyze_timeframe(
        source,
        "15m",
        ema_period=2,
        swing_lookback=1,
        liquidity_tolerance=1.0,
    )

    assert isinstance(result, TimeframeAnalysis)
    assert result.timeframe == "15m"
    assert result.trend == "BULLISH 🟢"
    assert result.highs
    assert result.lows
    assert result.high_labels
    assert result.low_labels
    assert result.structure in {
        "Bullish Structure",
        "Bearish Structure",
        "Range / Transition",
    }
    assert "EMA50" in result.data.columns
    assert "EMA50" not in source.columns


def test_each_timeframe_analysis_owns_its_data_copy(ohlc_factory):
    source = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
            (102, 105, 102, 104, 10),
        ]
    )

    four_hour = analyze_timeframe(source, "4h", ema_period=2)
    one_minute = analyze_timeframe(source, "1m", ema_period=2)
    four_hour.data.iloc[0, four_hour.data.columns.get_loc("Close")] = 999

    assert one_minute.data["Close"].iloc[0] == 100.0
    assert source["Close"].iloc[0] == 100.0


def test_select_active_fvgs_preserves_size_proximity_and_count_filters(
    ohlc_factory,
):
    source = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 101, 99, 100, 10),
        ]
    )
    analysis = analyze_timeframe(source, "4h")
    analysis = replace(
        analysis,
        fvgs=[
            {
                "type": "bullish",
                "top": 94.0,
                "bottom": 90.0,
                "mitigated": False,
            },
            {
                "type": "bullish",
                "top": 99.0,
                "bottom": 98.0,
                "mitigated": False,
            },
            {
                "type": "bearish",
                "top": 102.0,
                "bottom": 100.0,
                "mitigated": False,
            },
            {
                "type": "bearish",
                "top": 101.0,
                "bottom": 99.0,
                "mitigated": True,
            },
        ],
    )

    result = select_active_fvgs(
        analysis,
        minimum_size=2.0,
        maximum_count=1,
    )

    assert result == [analysis.fvgs[2]]


def test_analyze_timeframe_accepts_a_one_candle_frame(ohlc_factory):
    source = ohlc_factory([(100, 101, 99, 100, 10)])

    result = analyze_timeframe(source, "1m")

    assert result.data["EMA50"].iloc[0] == 100.0
    assert result.trend == "BEARISH 🔴"
    assert result.structure == "Not enough data"
