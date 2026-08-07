from dataclasses import replace

from analysis_pipeline import analyze_timeframe
from dataclasses import FrozenInstanceError

import pytest

from decision_authority import AuthorityGateKey, DecisionAuthority
from timeframe_roles import Direction, SetupState


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
        fvgs=[],
    )


def _analyses(
    ohlc_factory,
    *,
    context="bullish",
    setup="aligned",
    confirmation=True,
    trigger=True,
    execution_fvg=True,
):
    context_trend = "BULLISH 🟢" if context == "bullish" else "BEARISH 🔴"
    context_direction = context
    setup_direction = (
        context_direction
        if setup == "aligned"
        else "bearish" if context_direction == "bullish" else "bullish"
    )
    setup_structure = (
        "Bullish Structure"
        if setup_direction == "bullish"
        else "Bearish Structure"
    )
    analyses = {
        "4 Hour": _analysis(ohlc_factory, "4h", context_trend),
        "1 Hour": _analysis(ohlc_factory, "1h", context_trend),
        "15 Minute": _analysis(
            ohlc_factory,
            "15m",
            context_trend,
            setup_structure,
        ),
        "5 Minute": _analysis(ohlc_factory, "5m", context_trend),
        "1 Minute": _analysis(ohlc_factory, "1m", context_trend),
    }
    if confirmation:
        analyses["5 Minute"] = replace(
            analyses["5 Minute"],
            bos={
                "direction": context_direction,
                "time": analyses["5 Minute"].data.index[-1],
                "level": 101.0,
                "text": "BOS",
            },
        )
    if trigger:
        analyses["1 Minute"] = replace(
            analyses["1 Minute"],
            choch={
                "direction": context_direction,
                "time": analyses["1 Minute"].data.index[-1],
                "level": 101.0,
                "text": "CHoCH",
            },
        )
    if execution_fvg:
        analyses["1 Minute"] = replace(
            analyses["1 Minute"],
            fvgs=[
                {
                    "type": context_direction,
                    "top": 106.0,
                    "bottom": 100.0,
                    "mitigated": False,
                }
            ],
        )
    return analyses


def _session_sweep(direction):
    return {
        "New York": {
            "high_swept": direction == "bearish",
            "low_swept": direction == "bullish",
        }
    }


def _evaluate(analyses, session_levels):
    return DecisionAuthority().evaluate(
        analyses,
        session_levels,
        minimum_fvg_size=5.0,
        maximum_fvgs=3,
    )


def test_chart_selection_cannot_change_the_recommendation(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    recommendations = set()

    for selected in analyses:
        display_analysis = analyses[selected]
        assert display_analysis is analyses[selected]
        recommendations.add(
            _evaluate(analyses, _session_sweep("bullish")).recommendation
        )

    assert recommendations == {"READY"}


def test_ema_direction_alone_cannot_confirm_mss_or_choch(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=False,
        trigger=False,
    )

    result = _evaluate(analyses, _session_sweep("bullish"))

    assert result.roles.confirmation_direction is None
    assert result.roles.trigger_direction is None
    assert result.recommendation == "WATCH"


def test_actual_5m_and_1m_structural_events_enable_ready_state(ohlc_factory):
    result = _evaluate(
        _analyses(ohlc_factory),
        _session_sweep("bullish"),
    )

    assert result.roles.confirmation_direction == Direction.BULLISH
    assert result.roles.trigger_direction == Direction.BULLISH
    assert result.recommendation == "READY"


def test_authority_exposes_one_immutable_snapshot_of_approved_gates(
    ohlc_factory,
):
    result = _evaluate(
        _analyses(ohlc_factory, trigger=False, execution_fvg=False),
        _session_sweep("bullish"),
    )

    assert tuple(gate.key for gate in result.gates) == (
        AuthorityGateKey.HTF_CONTEXT,
        AuthorityGateKey.SETUP_15M,
        AuthorityGateKey.LIQUIDITY_SWEEP,
        AuthorityGateKey.CONFIRMATION_5M,
        AuthorityGateKey.TRIGGER_1M,
        AuthorityGateKey.DIRECTIONAL_FVG_1M,
    )
    assert [gate.explanation for gate in result.gates if gate.satisfied] == (
        result.trade_plan["reasons"]
    )
    assert [gate.explanation for gate in result.gates if not gate.satisfied] == (
        result.trade_plan["missing"]
    )
    with pytest.raises(FrozenInstanceError):
        result.gates[0].satisfied = False


def test_conflicting_4h_and_1h_context_prevents_candidate(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(
        analyses["1 Hour"],
        trend="BEARISH 🔴",
    )

    result = _evaluate(analyses, _session_sweep("bullish"))

    assert result.roles.context_direction is None
    assert result.recommendation == "AVOID"
    assert result.playbook["status"] == "NO SETUP"


def test_bearish_context_with_bullish_15m_pullback_waits_for_confirmation(
    ohlc_factory,
):
    analyses = _analyses(
        ohlc_factory,
        context="bearish",
        setup="countertrend",
        confirmation=False,
        trigger=False,
    )

    result = _evaluate(analyses, _session_sweep("bearish"))

    assert result.roles.context_direction == Direction.BEARISH
    assert result.roles.setup_state == SetupState.COUNTERTREND_PULLBACK
    assert result.recommendation == "WAIT"
    assert result.playbook["phase"] == "waiting_for_mss"


def test_countertrend_pullback_can_progress_after_5m_shift(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        context="bearish",
        setup="countertrend",
        confirmation=True,
        trigger=False,
    )

    result = _evaluate(analyses, _session_sweep("bearish"))

    assert result.roles.setup_state == SetupState.COUNTERTREND_PULLBACK
    assert result.recommendation == "WATCH"
    assert result.playbook["phase"] == "waiting_for_trigger"


def test_authority_uses_only_directional_active_1m_fvg(ohlc_factory):
    analyses = _analyses(ohlc_factory, execution_fvg=False)
    analyses["1 Minute"] = replace(
        analyses["1 Minute"],
        fvgs=[
            {
                "type": "bearish",
                "top": 106.0,
                "bottom": 100.0,
                "mitigated": False,
            }
        ],
    )

    result = _evaluate(analyses, _session_sweep("bullish"))

    assert result.active_fvgs == analyses["1 Minute"].fvgs
    assert result.recommendation == "WATCH"
    assert "Directional active 1M FVG" in result.trade_plan["missing"]
