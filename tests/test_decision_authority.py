from dataclasses import replace

from analysis_pipeline import analyze_timeframe
from decision_authority import DecisionAuthority


def test_authority_uses_configured_analysis_not_display_selection(ohlc_factory):
    bullish_data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
            (102, 105, 102, 104, 10),
        ]
    )
    bearish_data = ohlc_factory(
        [
            (104, 105, 103, 104, 10),
            (104, 104, 101, 102, 10),
            (102, 102, 99, 100, 10),
        ]
    )
    four_hour = analyze_timeframe(bullish_data, "4h", ema_period=2)
    one_minute = analyze_timeframe(bearish_data, "1m", ema_period=2)
    analyses = {"4 Hour": four_hour, "1 Minute": one_minute}
    authority = DecisionAuthority(strategy_timeframe="4 Hour")

    first = authority.evaluate(
        analyses,
        {},
        minimum_fvg_size=5.0,
        maximum_fvgs=3,
    )
    analyses["1 Minute"] = replace(one_minute, trend="BULLISH 🟢")
    second = authority.evaluate(
        analyses,
        {},
        minimum_fvg_size=5.0,
        maximum_fvgs=3,
    )

    assert first.strategy_timeframe == "4 Hour"
    assert first.analysis is four_hour
    assert first.recommendation == first.trade_plan["status"]
    assert second.trade_plan == first.trade_plan


def test_authority_applies_fvg_filters_before_building_trade_plan(
    ohlc_factory,
):
    data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
            (102, 105, 102, 104, 10),
        ]
    )
    analysis = analyze_timeframe(data, "4h", ema_period=2)
    analysis = replace(
        analysis,
        fvgs=[
            {
                "type": "bullish",
                "top": 103.0,
                "bottom": 97.0,
                "mitigated": False,
            },
            {
                "type": "bearish",
                "top": 106.0,
                "bottom": 104.0,
                "mitigated": False,
            },
        ],
    )

    result = DecisionAuthority().evaluate(
        {"4 Hour": analysis},
        {},
        minimum_fvg_size=5.0,
        maximum_fvgs=3,
    )

    assert result.active_fvgs == [analysis.fvgs[0]]
    assert result.trade_plan["bullish_points"] >= 10
    assert result.trade_plan["bearish_points"] == 0
