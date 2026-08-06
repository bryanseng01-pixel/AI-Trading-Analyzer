from copy import deepcopy
from dataclasses import replace

from setup_overlay import (
    OverlayLevelState,
    build_setup_overlay,
)
from test_decision_authority import _analyses, _evaluate


def _sessions(analysis, direction, *, swept):
    first, last = analysis.data.index[[0, -1]]
    return {
        "London": {
            "high": 106.0,
            "low": 96.0,
            "start_time": first,
            "end_time": last,
            "high_swept": swept and direction == "bearish",
            "low_swept": swept and direction == "bullish",
            "high_sweep_time": (
                last if swept and direction == "bearish" else None
            ),
            "low_sweep_time": (
                last if swept and direction == "bullish" else None
            ),
        }
    }


def _add_pending_bullish_level(analysis, price=103.0):
    first, last = analysis.data.index[[0, -1]]
    return replace(
        analysis,
        structure="Bearish Structure",
        high_labels=[
            (first, price - 2, "LH"),
            (last, price, "LH"),
        ],
        bos=None,
        choch=None,
    )


def _add_execution_fvg(analysis, direction="bullish"):
    first, last = analysis.data.index[[0, -1]]
    return replace(
        analysis,
        fvgs=[
            {
                "type": direction,
                "top": 106.0,
                "bottom": 100.0,
                "mitigated": False,
                "start_time": first,
                "end_time": last,
            }
        ],
    )


def test_avoid_overlay_has_context_only_and_no_trade_projections(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(
        analyses["1 Hour"],
        trend="BEARISH 🔴",
    )
    decision = _evaluate(analyses, {})

    overlay = build_setup_overlay(decision, analyses, {})

    assert overlay.authority_status == "AVOID"
    assert overlay.direction is None
    assert overlay.primary_waiting_level is None
    assert overlay.relevant_liquidity_level is None
    assert overlay.confirmation_level_5m is None
    assert overlay.trigger_level_1m is None
    assert overlay.active_execution_zone is None
    assert overlay.invalidation_level is None
    assert overlay.target_levels == ()
    assert overlay.visibility.show_context_explanation is True
    assert overlay.visibility.show_execution_zone is False
    assert len(overlay.annotations) == 1


def test_progress_is_a_direct_projection_of_authority_gates(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=False,
        trigger=False,
        execution_fvg=False,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=False)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    expected_complete = len(decision.trade_plan["reasons"])
    expected_total = expected_complete + len(decision.trade_plan["missing"])
    assert overlay.progress_step == expected_complete
    assert overlay.total_steps == expected_total
    assert overlay.completion_percentage == (
        expected_complete / expected_total * 100.0
    )


def test_waiting_for_liquidity_shows_only_latest_relevant_level(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=False,
        trigger=False,
        execution_fvg=False,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=False)
    older = deepcopy(sessions["London"])
    older["end_time"] = older["start_time"]
    older["low"] = 94.0
    sessions["Asia"] = older
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.current_phase == "waiting_for_liquidity"
    assert overlay.relevant_liquidity_level is not None
    assert overlay.relevant_liquidity_level.price == 96.0
    assert overlay.relevant_liquidity_level.source == "London"
    assert overlay.relevant_liquidity_level.importance == "primary"
    assert overlay.primary_waiting_level == overlay.relevant_liquidity_level
    assert overlay.active_execution_zone is None


def test_countertrend_wait_shows_sweep_and_pending_5m_close(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        context="bearish",
        setup="countertrend",
        confirmation=False,
        trigger=False,
        execution_fvg=False,
    )
    first, last = analyses["5 Minute"].data.index[[0, -1]]
    analyses["5 Minute"] = replace(
        analyses["5 Minute"],
        structure="Bullish Structure",
        low_labels=[(first, 99.0, "HL"), (last, 97.0, "HL")],
    )
    sessions = _sessions(analyses["5 Minute"], "bearish", swept=True)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.authority_status == "WAIT"
    assert overlay.current_phase == "waiting_for_mss"
    assert overlay.relevant_liquidity_level is not None
    assert overlay.relevant_liquidity_level.state == OverlayLevelState.SWEPT_BY_WICK
    assert overlay.confirmation_level_5m is not None
    assert overlay.confirmation_level_5m.price == 97.0
    assert overlay.confirmation_level_5m.event_type == "CHoCH"
    assert overlay.confirmation_level_5m.state == OverlayLevelState.WAITING_FOR_CLOSE
    assert overlay.primary_waiting_level == overlay.confirmation_level_5m
    assert overlay.visibility.show_execution_zone is False


def test_watch_uses_pending_5m_level_and_not_ema_direction(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=False,
        trigger=False,
        execution_fvg=False,
    )
    analyses["5 Minute"] = _add_pending_bullish_level(
        analyses["5 Minute"],
        price=103.0,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert decision.roles.confirmation_direction is None
    assert overlay.authority_status == "WATCH"
    assert overlay.confirmation_level_5m is not None
    assert overlay.confirmation_level_5m.price == 103.0
    assert overlay.confirmation_level_5m.state == OverlayLevelState.WAITING_FOR_CLOSE


def test_watch_after_5m_confirmation_shows_pending_1m_trigger(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=True,
        trigger=False,
        execution_fvg=False,
    )
    analyses["1 Minute"] = _add_pending_bullish_level(
        analyses["1 Minute"],
        price=104.0,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.current_phase == "waiting_for_trigger"
    assert overlay.confirmation_level_5m is not None
    assert overlay.confirmation_level_5m.state == OverlayLevelState.CONFIRMED_BY_CLOSE
    assert overlay.trigger_level_1m is not None
    assert overlay.trigger_level_1m.price == 104.0
    assert overlay.trigger_level_1m.state == OverlayLevelState.WAITING_FOR_CLOSE
    assert overlay.primary_waiting_level == overlay.trigger_level_1m


def test_ready_shows_one_zone_and_confirmed_levels_without_projections(
    ohlc_factory,
):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.authority_status == "READY"
    assert overlay.current_phase == "execution_zone_available"
    assert overlay.active_execution_zone is not None
    assert overlay.active_execution_zone.bottom == 100.0
    assert overlay.active_execution_zone.top == 106.0
    assert overlay.active_execution_zone.importance == "primary"
    assert overlay.confirmation_level_5m is not None
    assert overlay.trigger_level_1m is not None
    assert overlay.visibility.show_execution_zone is True
    assert overlay.invalidation_level is None
    assert overlay.target_levels == ()
    assert overlay.visibility.show_invalidation_level is False
    assert overlay.visibility.show_target_levels is False


def test_missing_structure_and_future_fvg_return_limitations(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=True,
        trigger=True,
        execution_fvg=False,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.current_phase == "waiting_for_execution_zone"
    assert overlay.active_execution_zone is None
    assert any("cannot be calculated before it forms" in item for item in overlay.limitations)
    assert any("Invalidation awaits" in item for item in overlay.limitations)
    assert any("Targets await" in item for item in overlay.limitations)


def test_unconfirmed_setup_returns_none_instead_of_estimating_level(
    ohlc_factory,
):
    analyses = _analyses(ohlc_factory)
    analyses["15 Minute"] = replace(
        analyses["15 Minute"],
        structure="Range / Transition",
        high_labels=[],
        low_labels=[],
        bos=None,
        choch=None,
    )
    decision = _evaluate(analyses, {})

    overlay = build_setup_overlay(decision, analyses, {})

    assert overlay.current_phase == "waiting_for_setup"
    assert overlay.primary_waiting_level is None
    assert any("pending 15M setup level" in item for item in overlay.limitations)


def test_ambiguous_latest_liquidity_levels_return_none(ohlc_factory):
    analyses = _analyses(
        ohlc_factory,
        confirmation=False,
        trigger=False,
        execution_fvg=False,
    )
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=False)
    sessions["Asia"] = deepcopy(sessions["London"])
    decision = _evaluate(analyses, sessions)

    overlay = build_setup_overlay(decision, analyses, sessions)

    assert overlay.relevant_liquidity_level is None
    assert overlay.primary_waiting_level is None
    assert any("ambiguous" in item for item in overlay.limitations)


def test_builder_does_not_mutate_inputs(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    sessions_before = deepcopy(sessions)
    fvgs_before = deepcopy(decision.active_fvgs)

    build_setup_overlay(decision, analyses, sessions)

    assert sessions == sessions_before
    assert decision.active_fvgs == fvgs_before
