from copy import deepcopy
from dataclasses import replace

import pytest

from confluence import evaluate_confluence
from fvg_lifecycle import (
    DetectedFvg,
    FvgLifecycleResult,
    evaluate_fvg_lifecycles,
)
from ifvg_integration import build_ifvg_confluence_factor
from setup_overlay import (
    OverlayZoneKind,
    OverlayZonePurpose,
    build_setup_overlay,
)
from test_decision_authority import _analyses, _evaluate
from test_setup_overlay import _add_execution_fvg, _sessions
from timeframe_roles import Direction
from tradingview_chart import _serialize_setup_overlay


def _lifecycle(
    ohlc_factory,
    *,
    current_direction=Direction.BULLISH,
    close_confirmed=True,
    invalidate=False,
):
    data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 104, 99, 103, 10),
            (102, 104, 102, 103, 10),
            (
                (103, 105, 99, 104.5, 10)
                if current_direction == Direction.BULLISH and close_confirmed
                else (101, 105, 99, 103.5, 10)
                if current_direction == Direction.BULLISH
                else (101, 105, 99, 99.5, 10)
                if close_confirmed
                else (101, 105, 99, 100.5, 10)
            ),
        ]
        + (
            [(101, 105, 99, 99.5, 10)]
            if invalidate and current_direction == Direction.BULLISH
            else [(101, 105, 99, 104.5, 10)]
            if invalidate
            else []
        )
    )
    original_direction = (
        Direction.BEARISH
        if current_direction == Direction.BULLISH
        else Direction.BULLISH
    )
    formation = DetectedFvg(
        direction=original_direction,
        top=104.0,
        bottom=100.0,
        formation_start_time=data.index[0],
        formation_time=data.index[2],
    )
    return evaluate_fvg_lifecycles(
        data,
        (formation,),
        timeframe="1m",
    )


def _overlay(
    ohlc_factory,
    lifecycle,
    *,
    context="bullish",
    status_setup="ready",
):
    analyses = _analyses(
        ohlc_factory,
        context=context,
        trigger=status_setup != "watch",
    )
    analyses["1 Minute"] = _add_execution_fvg(
        analyses["1 Minute"],
        direction=context,
    )
    sessions = _sessions(
        analyses["5 Minute"],
        context,
        swept=status_setup != "wait",
    )
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(
        decision,
        analyses,
        sessions,
        fvg_lifecycle_result=lifecycle,
        minimum_ifvg_size=1.0,
    )
    return decision, overlay


def test_close_confirmed_directional_ifvg_supports_authority_zone(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    decision, overlay = _overlay(ohlc_factory, lifecycle)

    assert decision.recommendation == "READY"
    assert overlay.active_execution_zone is not None
    assert overlay.active_execution_zone.kind == OverlayZoneKind.ORIGINAL_FVG
    assert (
        overlay.active_execution_zone.purpose
        == OverlayZonePurpose.AUTHORITY_REQUIRED
    )
    support = overlay.ifvg_support
    assert support.applicable is True
    assert support.evaluated is True
    assert support.supporting_zone is not None
    assert support.supporting_zone.kind == OverlayZoneKind.IFVG
    assert support.supporting_zone.direction == Direction.BULLISH
    assert support.overlap_bottom == 100.0
    assert support.overlap_top == 104.0
    assert support.overlap_percentage == pytest.approx(4.0 / 6.0)
    assert overlay.visibility.show_optional_ifvg_zone is True


def test_wick_only_and_opposing_ifvg_do_not_support_location(ohlc_factory):
    wick_only = _lifecycle(ohlc_factory, close_confirmed=False)
    _, wick_overlay = _overlay(ohlc_factory, wick_only)
    opposing = _lifecycle(
        ohlc_factory,
        current_direction=Direction.BEARISH,
    )
    _, opposing_overlay = _overlay(ohlc_factory, opposing)

    assert wick_overlay.ifvg_support.evaluated is True
    assert wick_overlay.ifvg_support.supporting_zone is None
    assert opposing_overlay.ifvg_support.supporting_zone is None


def test_non_overlap_and_boundary_contact_do_not_qualify(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    zone = lifecycle.active_ifvgs[0]
    non_overlap = replace(zone, top=96.0, bottom=92.0)
    boundary_touch = replace(zone, top=100.0, bottom=96.0)

    for candidate in (non_overlap, boundary_touch):
        result = replace(
            lifecycle,
            zones=(candidate,),
            active_ifvgs=(candidate,),
        )
        _, overlay = _overlay(ohlc_factory, result)
        assert overlay.ifvg_support.supporting_zone is None


def test_invalidated_ifvg_is_excluded(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory, invalidate=True)
    _, overlay = _overlay(ohlc_factory, lifecycle)

    assert lifecycle.active_ifvgs == ()
    assert overlay.ifvg_support.evaluated is True
    assert overlay.ifvg_support.supporting_zone is None


def test_one_zone_selection_uses_overlap_not_input_order(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    smaller = replace(lifecycle.active_ifvgs[0], top=102.0)
    larger = replace(
        lifecycle.active_ifvgs[0],
        top=105.0,
        inversion_boundary=105.0,
    )

    selected = []
    for candidates in ((smaller, larger), (larger, smaller)):
        result = replace(
            lifecycle,
            zones=candidates,
            active_ifvgs=candidates,
        )
        _, overlay = _overlay(ohlc_factory, result)
        selected.append(overlay.ifvg_support.supporting_zone)

    assert selected[0] == selected[1]
    assert selected[0].top == 105.0


def test_avoid_and_wait_never_show_ifvg(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    _, waiting = _overlay(
        ohlc_factory,
        lifecycle,
        status_setup="wait",
    )

    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(analyses["1 Hour"], trend="BEARISH 🔴")
    decision = _evaluate(analyses, {})
    avoid = build_setup_overlay(
        decision,
        analyses,
        {},
        fvg_lifecycle_result=lifecycle,
        minimum_ifvg_size=1.0,
    )

    assert waiting.authority_status == "WAIT"
    assert waiting.ifvg_support.applicable is False
    assert waiting.visibility.show_optional_ifvg_zone is False
    assert avoid.authority_status == "AVOID"
    assert avoid.ifvg_support.supporting_zone is None


def test_ifvg_factor_semantics_and_placeholder_replacement(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    decision, supported = _overlay(ohlc_factory, lifecycle)
    factor = build_ifvg_confluence_factor(supported)
    result = evaluate_confluence(decision, supported, (factor,))

    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert "ifvg" not in {item.key for item in result.pending_future_factors}

    _, absent = _overlay(
        ohlc_factory,
        _lifecycle(ohlc_factory, close_confirmed=False),
    )
    absent_factor = build_ifvg_confluence_factor(absent)
    assert absent_factor.active is True
    assert absent_factor.satisfied is False

    _, waiting = _overlay(
        ohlc_factory,
        lifecycle,
        status_setup="wait",
    )
    inactive = build_ifvg_confluence_factor(waiting)
    assert inactive.active is False
    assert inactive.satisfied is None

    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    unavailable_decision = _evaluate(analyses, sessions)
    unavailable_overlay = build_setup_overlay(
        unavailable_decision,
        analyses,
        sessions,
    )
    unavailable = build_ifvg_confluence_factor(unavailable_overlay)
    assert unavailable.active is False
    assert unavailable.satisfied is None


def test_overlap_percentage_is_descriptive_only(ohlc_factory):
    decision, overlay = _overlay(ohlc_factory, _lifecycle(ohlc_factory))
    changed = replace(
        overlay,
        ifvg_support=replace(overlay.ifvg_support, overlap_percentage=0.01),
    )

    assert build_ifvg_confluence_factor(overlay) == (
        build_ifvg_confluence_factor(changed)
    )
    assert _serialize_setup_overlay(overlay) == _serialize_setup_overlay(changed)
    assert decision.recommendation == "READY"


def test_chart_serialization_separates_required_fvg_and_optional_ifvg(
    ohlc_factory,
):
    _, overlay = _overlay(ohlc_factory, _lifecycle(ohlc_factory))

    serialized = _serialize_setup_overlay(overlay)

    assert serialized["execution_zone"]["kind"] == "original_fvg"
    assert serialized["execution_zone"]["purpose"] == "authority_required"
    assert serialized["optional_ifvg_zone"]["kind"] == "ifvg"
    assert (
        serialized["optional_ifvg_zone"]["purpose"]
        == "optional_confluence"
    )
    assert "overlap_percentage" not in serialized["optional_ifvg_zone"]


def test_chart_selection_cannot_change_ifvg_projection(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    snapshots = set()

    for selected in analyses:
        assert analyses[selected] is not None
        overlay = build_setup_overlay(
            decision,
            analyses,
            sessions,
            fvg_lifecycle_result=lifecycle,
            minimum_ifvg_size=1.0,
        )
        zone = overlay.ifvg_support.supporting_zone
        snapshots.add(
            (
                decision.recommendation,
                zone.bottom if zone else None,
                zone.top if zone else None,
            )
        )

    assert snapshots == {("READY", 100.0, 104.0)}


def test_integration_does_not_mutate_or_change_authority(ohlc_factory):
    lifecycle = _lifecycle(ohlc_factory)
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    original = deepcopy(decision)

    overlay = build_setup_overlay(
        decision,
        analyses,
        sessions,
        fvg_lifecycle_result=lifecycle,
        minimum_ifvg_size=1.0,
    )
    factor = build_ifvg_confluence_factor(overlay)
    evaluate_confluence(decision, overlay, (factor,))

    assert decision == original
    assert decision.recommendation == "READY"
