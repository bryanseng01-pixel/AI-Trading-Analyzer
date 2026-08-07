from copy import deepcopy
from dataclasses import replace

import pandas as pd

from confluence import evaluate_confluence
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate
from test_setup_overlay import _add_execution_fvg, _sessions
from timeframe_roles import Direction
from tradingview_chart import _serialize_setup_overlay
from volume_profile_engine import (
    DataQuality,
    ProfileRange,
    ProfileValidity,
    ValueArea,
    VolumeNode,
    VolumeNodeKind,
    VolumeProfileBin,
    VolumeProfileResult,
    VolumeProfileSource,
)
from volume_profile_integration import (
    attach_volume_profile_support,
    build_volume_profile_confluence_factor,
)


def _profile(*, valid=True):
    source = VolumeProfileSource.YAHOO_BAR_OHLCV_APPROXIMATION
    if not valid:
        return VolumeProfileResult(
            validity=ProfileValidity.NO_COMPLETED_SESSION,
            profile_range=None,
            bins=(),
            value_area=None,
            nodes=(),
            total_reported_bar_volume=0.0,
            total_distributed_volume=0.0,
            eligible_bar_count=0,
            expected_bar_count=510,
            missing_bar_count=510,
            source=source,
            data_quality=DataQuality.UNAVAILABLE,
            limitations=("No completed session.",),
        )
    start = pd.Timestamp("2026-01-04 08:30", tz="America/New_York")
    end = pd.Timestamp("2026-01-04 17:00", tz="America/New_York")
    return VolumeProfileResult(
        validity=ProfileValidity.VALID,
        profile_range=ProfileRange(
            timeframe="1m",
            session_name="Previous completed New York",
            start_time=start,
            end_time=end,
            price_low=95.0,
            price_high=115.0,
            tick_size=0.25,
            ticks_per_bin=4,
            bin_size=1.0,
            source=source,
        ),
        bins=(
            VolumeProfileBin(0, 95, 96, 95.5, 100, 1.0, True, None),
        ),
        value_area=ValueArea(0.70, 0.72, 105.0, 10, 108.0, 102.0, (7, 8, 9, 10, 11, 12)),
        nodes=(
            VolumeNode(VolumeNodeKind.HVN, 104, 105, 104.5, (9,), 200),
            VolumeNode(VolumeNodeKind.HVN, 105, 106, 105.5, (10,), 180),
            VolumeNode(VolumeNodeKind.LVN, 100, 101, 100.5, (5,), 20),
        ),
        total_reported_bar_volume=100.0,
        total_distributed_volume=100.0,
        eligible_bar_count=510,
        expected_bar_count=510,
        missing_bar_count=0,
        source=source,
        data_quality=DataQuality.APPROXIMATED,
        limitations=("Bar-volume approximation.",),
    )


def _ready_overlay(ohlc_factory, *, context="bullish"):
    analyses = _analyses(ohlc_factory, context=context)
    analyses["1 Minute"] = _add_execution_fvg(
        analyses["1 Minute"], direction=context
    )
    sessions = _sessions(analyses["5 Minute"], context, swept=True)
    decision = _evaluate(analyses, sessions)
    return analyses, decision, build_setup_overlay(decision, analyses, sessions)


def test_completed_profile_attaches_to_authority_execution_zone(ohlc_factory):
    _, decision, overlay = _ready_overlay(ohlc_factory)
    attached = attach_volume_profile_support(overlay, _profile())
    support = attached.volume_profile_support

    assert decision.recommendation == "READY"
    assert support.applicable is True
    assert support.evaluated is True
    assert support.assessment.authority_zone_bottom == 100.0
    assert support.assessment.authority_zone_top == 106.0
    assert support.assessment.directionally_supportive is True
    assert attached.visibility.show_volume_profile is True


def test_only_one_intersecting_hvn_and_lvn_are_projected(ohlc_factory):
    _, _, overlay = _ready_overlay(ohlc_factory)
    support = attach_volume_profile_support(
        overlay, _profile()
    ).volume_profile_support

    assert support.selected_hvn.bottom == 104.0
    assert support.selected_lvn.bottom == 100.0


def test_invalid_profile_and_nonvisible_authority_zone_are_inactive(ohlc_factory):
    analyses, _, ready = _ready_overlay(ohlc_factory)
    invalid = attach_volume_profile_support(ready, _profile(valid=False))
    waiting_sessions = _sessions(analyses["5 Minute"], "bullish", swept=False)
    waiting_decision = _evaluate(analyses, waiting_sessions)
    waiting = attach_volume_profile_support(
        build_setup_overlay(waiting_decision, analyses, waiting_sessions),
        _profile(),
    )

    assert invalid.volume_profile_support.applicable is True
    assert invalid.volume_profile_support.evaluated is False
    assert waiting_decision.recommendation == "WAIT"
    assert waiting.volume_profile_support.applicable is False
    assert waiting.visibility.show_volume_profile is False


def test_factor_replaces_placeholder_but_remains_optional(ohlc_factory):
    _, decision, overlay = _ready_overlay(ohlc_factory)
    attached = attach_volume_profile_support(overlay, _profile())
    factor = build_volume_profile_confluence_factor(attached)
    result = evaluate_confluence(decision, attached, (factor,))

    assert factor.key == "volume_profile"
    assert factor.name == "Volume Profile Location"
    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert "volume_profile" not in {
        item.key for item in result.pending_future_factors
    }


def test_inside_value_is_evaluable_without_optional_support(ohlc_factory):
    _, _, overlay = _ready_overlay(ohlc_factory)
    profile = _profile()
    profile = replace(
        profile,
        value_area=replace(profile.value_area, val=99.0, vah=110.0),
    )
    attached = attach_volume_profile_support(overlay, profile)
    factor = build_volume_profile_confluence_factor(attached)

    assert factor.active is True
    assert factor.satisfied is False


def test_chart_serializes_completed_profile_without_profile_calculation(ohlc_factory):
    _, _, overlay = _ready_overlay(ohlc_factory)
    serialized = _serialize_setup_overlay(
        attach_volume_profile_support(overlay, _profile())
    )
    profile = serialized["volume_profile"]

    assert profile["poc"] == 105.0
    assert profile["vah"] == 108.0
    assert profile["val"] == 102.0
    assert [node["kind"] for node in profile["nodes"]] == ["hvn", "lvn"]
    assert serialized["execution_zone"]["purpose"] == "authority_required"


def test_profile_integration_cannot_mutate_authority_or_other_location_support(
    ohlc_factory,
):
    _, decision, overlay = _ready_overlay(ohlc_factory)
    original_decision = deepcopy(decision)
    attached = attach_volume_profile_support(overlay, _profile())

    assert decision == original_decision
    assert decision.recommendation == "READY"
    assert attached.active_execution_zone == overlay.active_execution_zone
    assert attached.ifvg_support == overlay.ifvg_support
    assert attached.order_block_support == overlay.order_block_support
    assert attached.premium_discount_support == overlay.premium_discount_support


def test_chart_selection_is_not_an_input_to_profile_integration(ohlc_factory):
    analyses, decision, overlay = _ready_overlay(ohlc_factory)
    snapshots = set()
    for selected in analyses:
        assert analyses[selected] is not None
        attached = attach_volume_profile_support(overlay, _profile())
        factor = build_volume_profile_confluence_factor(attached)
        snapshots.add(
            (
                decision.recommendation,
                attached.volume_profile_support.profile_range.poc,
                factor.satisfied,
            )
        )

    assert snapshots == {("READY", 105.0, True)}
