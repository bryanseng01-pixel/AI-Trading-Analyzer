from copy import deepcopy
from dataclasses import replace

from confluence import evaluate_confluence
from order_block_engine import OrderBlockResult, evaluate_order_blocks
from order_block_integration import build_order_block_confluence_factor
from setup_overlay import (
    OverlayZoneKind,
    OverlayZonePurpose,
    build_setup_overlay,
)
from test_decision_authority import _analyses, _evaluate
from test_order_block_engine import _market
from test_setup_overlay import _add_execution_fvg, _sessions
from timeframe_roles import Direction
from tradingview_chart import _serialize_setup_overlay


def _result(ohlc_factory, direction=Direction.BULLISH, post_rows=()):
    data, event = _market(ohlc_factory, direction, post_rows)
    return evaluate_order_blocks(data, (event,), timeframe="1m")


def _overlay(
    ohlc_factory,
    result,
    *,
    context="bullish",
    swept=True,
):
    analyses = _analyses(ohlc_factory, context=context)
    analyses["1 Minute"] = _add_execution_fvg(
        analyses["1 Minute"],
        direction=context,
    )
    sessions = _sessions(analyses["5 Minute"], context, swept=swept)
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(
        decision,
        analyses,
        sessions,
        order_block_result=result,
    )
    return decision, overlay


def test_directional_order_block_strictly_overlaps_authority_fvg(ohlc_factory):
    decision, overlay = _overlay(ohlc_factory, _result(ohlc_factory))

    assert decision.recommendation == "READY"
    assert overlay.active_execution_zone.kind == OverlayZoneKind.ORIGINAL_FVG
    support = overlay.order_block_support
    assert support.applicable is True
    assert support.evaluated is True
    assert support.supporting_zone is not None
    assert support.supporting_zone.kind == OverlayZoneKind.ORDER_BLOCK
    assert (
        support.supporting_zone.purpose
        == OverlayZonePurpose.OPTIONAL_CONFLUENCE
    )
    assert support.supporting_zone.direction == Direction.BULLISH
    assert support.overlap_bottom == 100.0
    assert support.overlap_top == 102.0
    assert support.overlap_percentage == 2.0 / 6.0
    assert overlay.visibility.show_optional_order_block_zone is True


def test_direction_mismatch_non_overlap_and_inactive_blocks_are_excluded(
    ohlc_factory,
):
    bullish = _result(ohlc_factory)
    block = bullish.active_order_blocks[0]
    non_overlap = replace(block, top=98.0, bottom=95.0)
    non_overlap_result = replace(
        bullish,
        order_blocks=(non_overlap,),
        active_order_blocks=(non_overlap,),
    )
    _, non_overlap_overlay = _overlay(ohlc_factory, non_overlap_result)
    _, opposing_overlay = _overlay(
        ohlc_factory,
        _result(ohlc_factory, Direction.BEARISH),
    )
    mitigated = _result(
        ohlc_factory,
        post_rows=((101, 104, 98, 99, 10),),
    )
    _, mitigated_overlay = _overlay(ohlc_factory, mitigated)

    assert non_overlap_overlay.order_block_support.supporting_zone is None
    assert opposing_overlay.order_block_support.supporting_zone is None
    assert mitigated.active_order_blocks == ()
    assert mitigated_overlay.order_block_support.supporting_zone is None


def test_wait_and_avoid_never_show_order_block(ohlc_factory):
    result = _result(ohlc_factory)
    _, waiting = _overlay(ohlc_factory, result, swept=False)
    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(analyses["1 Hour"], trend="BEARISH 🔴")
    decision = _evaluate(analyses, {})
    avoid = build_setup_overlay(
        decision,
        analyses,
        {},
        order_block_result=result,
    )

    assert waiting.authority_status == "WAIT"
    assert waiting.order_block_support.applicable is False
    assert waiting.visibility.show_optional_order_block_zone is False
    assert avoid.authority_status == "AVOID"
    assert avoid.order_block_support.supporting_zone is None


def test_confluence_factor_semantics_and_placeholder_replacement(ohlc_factory):
    decision, supported = _overlay(ohlc_factory, _result(ohlc_factory))
    factor = build_order_block_confluence_factor(supported)
    result = evaluate_confluence(decision, supported, (factor,))

    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert "order_block" not in {
        item.key for item in result.pending_future_factors
    }

    empty_result = OrderBlockResult(
        timeframe="1m",
        evaluated_through=None,
        order_blocks=(),
        active_order_blocks=(),
        limitations=(),
    )
    _, absent = _overlay(ohlc_factory, empty_result)
    absent_factor = build_order_block_confluence_factor(absent)
    assert absent_factor.active is True
    assert absent_factor.satisfied is False

    _, waiting = _overlay(ohlc_factory, _result(ohlc_factory), swept=False)
    inactive = build_order_block_confluence_factor(waiting)
    assert inactive.active is False
    assert inactive.satisfied is None


def test_chart_serializes_order_block_separately_without_research_field(
    ohlc_factory,
):
    _, overlay = _overlay(ohlc_factory, _result(ohlc_factory))

    serialized = _serialize_setup_overlay(overlay)

    assert serialized["execution_zone"]["purpose"] == "authority_required"
    assert serialized["optional_ifvg_zone"] is None
    assert serialized["optional_order_block_zone"]["kind"] == "order_block"
    assert (
        serialized["optional_order_block_zone"]["purpose"]
        == "optional_confluence"
    )
    assert "still_respected" not in serialized["optional_order_block_zone"]


def test_chart_selection_cannot_change_order_block_projection(ohlc_factory):
    result = _result(ohlc_factory)
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
            order_block_result=result,
        )
        zone = overlay.order_block_support.supporting_zone
        snapshots.add(
            (
                decision.recommendation,
                zone.bottom if zone else None,
                zone.top if zone else None,
            )
        )

    assert snapshots == {("READY", 99.0, 102.0)}


def test_order_block_integration_does_not_mutate_authority(ohlc_factory):
    result = _result(ohlc_factory)
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    original = deepcopy(decision)

    overlay = build_setup_overlay(
        decision,
        analyses,
        sessions,
        order_block_result=result,
    )
    factor = build_order_block_confluence_factor(overlay)
    evaluate_confluence(decision, overlay, (factor,))

    assert decision == original
    assert decision.recommendation == "READY"
