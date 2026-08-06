from dataclasses import replace

from analysis_pipeline import analyze_timeframe
from timeframe_roles import (
    Direction,
    SetupState,
    evaluate_timeframe_roles,
    latest_break_direction,
)


def _analysis(ohlc_factory, timeframe, trend, structure="Not enough data"):
    data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
        ]
    )
    return replace(
        analyze_timeframe(data, timeframe, ema_period=2),
        trend=trend,
        structure=structure,
        bos=None,
        choch=None,
    )


def test_ema_direction_alone_cannot_confirm_5m_or_trigger_1m(ohlc_factory):
    analyses = {
        "4 Hour": _analysis(ohlc_factory, "4h", "BULLISH 🟢"),
        "1 Hour": _analysis(ohlc_factory, "1h", "BULLISH 🟢"),
        "15 Minute": _analysis(
            ohlc_factory,
            "15m",
            "BULLISH 🟢",
            "Bullish Structure",
        ),
        "5 Minute": _analysis(ohlc_factory, "5m", "BULLISH 🟢"),
        "1 Minute": _analysis(ohlc_factory, "1m", "BULLISH 🟢"),
    }

    roles = evaluate_timeframe_roles(analyses)

    assert roles.context_direction == Direction.BULLISH
    assert roles.setup_state == SetupState.ALIGNED_CONTINUATION
    assert roles.confirmation_direction is None
    assert roles.trigger_direction is None
    assert roles.confirmation_aligned is False
    assert roles.trigger_aligned is False


def test_actual_bos_and_choch_control_confirmation_and_trigger(ohlc_factory):
    analyses = {
        "4 Hour": _analysis(ohlc_factory, "4h", "BEARISH 🔴"),
        "1 Hour": _analysis(ohlc_factory, "1h", "BEARISH 🔴"),
        "15 Minute": _analysis(
            ohlc_factory,
            "15m",
            "BULLISH 🟢",
            "Bearish Structure",
        ),
        "5 Minute": _analysis(ohlc_factory, "5m", "BULLISH 🟢"),
        "1 Minute": _analysis(ohlc_factory, "1m", "BULLISH 🟢"),
    }
    five_minute_time = analyses["5 Minute"].data.index[-1]
    one_minute_time = analyses["1 Minute"].data.index[-1]
    analyses["5 Minute"] = replace(
        analyses["5 Minute"],
        bos={
            "direction": "bearish",
            "time": five_minute_time,
            "level": 99.0,
            "text": "BOS",
        },
    )
    analyses["1 Minute"] = replace(
        analyses["1 Minute"],
        choch={
            "direction": "bearish",
            "time": one_minute_time,
            "level": 99.0,
            "text": "CHoCH",
        },
    )

    roles = evaluate_timeframe_roles(analyses)

    assert roles.confirmation_direction == Direction.BEARISH
    assert roles.trigger_direction == Direction.BEARISH
    assert roles.confirmation_aligned is True
    assert roles.trigger_aligned is True


def test_latest_bos_or_choch_timestamp_controls_conflicting_signals(
    ohlc_factory,
):
    analysis = _analysis(ohlc_factory, "5m", "BULLISH 🟢")
    first_time, second_time = analysis.data.index
    analysis = replace(
        analysis,
        bos={
            "direction": "bullish",
            "time": first_time,
            "level": 101.0,
            "text": "BOS",
        },
        choch={
            "direction": "bearish",
            "time": second_time,
            "level": 99.0,
            "text": "CHoCH",
        },
    )

    assert latest_break_direction(analysis) == Direction.BEARISH


def test_opposing_15m_structure_is_a_countertrend_pullback(ohlc_factory):
    analyses = {
        "4 Hour": _analysis(ohlc_factory, "4h", "BEARISH 🔴"),
        "1 Hour": _analysis(ohlc_factory, "1h", "BEARISH 🔴"),
        "15 Minute": _analysis(
            ohlc_factory,
            "15m",
            "BULLISH 🟢",
            "Bullish Structure",
        ),
        "5 Minute": _analysis(ohlc_factory, "5m", "BULLISH 🟢"),
        "1 Minute": _analysis(ohlc_factory, "1m", "BULLISH 🟢"),
    }

    roles = evaluate_timeframe_roles(analyses)

    assert roles.context_direction == Direction.BEARISH
    assert roles.setup_state == SetupState.COUNTERTREND_PULLBACK
