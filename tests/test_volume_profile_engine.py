from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from timeframe_roles import Direction
from volume_profile_engine import (
    DEFAULT_VOLUME_PROFILE_RULES,
    DataQuality,
    ProfileRelationship,
    ProfileValidity,
    VolumeNodeKind,
    VolumeProfileRules,
    assess_execution_zone_profile,
    build_previous_new_york_profile,
)


def _bars(rows, *, date="2026-08-05"):
    index = pd.date_range(
        f"{date} 08:30",
        periods=len(rows),
        freq="1min",
        tz="America/New_York",
    )
    return pd.DataFrame(
        rows,
        columns=["Open", "High", "Low", "Close", "Volume"],
        index=index,
        dtype=float,
    )


def _profile():
    data = _bars(
        (
            (100.2, 100.9, 100.0, 100.5, 100.0),
            (101.2, 101.9, 101.0, 101.5, 200.0),
            (102.2, 102.9, 102.0, 102.5, 50.0),
        )
    )
    return build_previous_new_york_profile(
        data,
        evaluated_through=pd.Timestamp("2026-08-05 17:01", tz="America/New_York"),
        tick_size=0.25,
    )


def test_rules_centralize_approved_defaults_and_are_immutable():
    assert DEFAULT_VOLUME_PROFILE_RULES == VolumeProfileRules(
        value_area_percentage=0.70,
        ticks_per_bin=4,
    )
    with pytest.raises(FrozenInstanceError):
        DEFAULT_VOLUME_PROFILE_RULES.ticks_per_bin = 8


def test_latest_completed_new_york_session_is_selected_not_active_session():
    completed = _bars(((100, 101, 100, 101, 10),), date="2026-08-04")
    active = _bars(((200, 201, 200, 201, 999),), date="2026-08-05")
    result = build_previous_new_york_profile(
        pd.concat((completed, active)),
        evaluated_through=pd.Timestamp("2026-08-05 10:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert result.validity == ProfileValidity.VALID
    assert result.profile_range.start_time == pd.Timestamp(
        "2026-08-04 08:30", tz="America/New_York"
    )
    assert result.total_reported_bar_volume == 10.0


def test_latest_same_day_session_is_eligible_after_scheduled_close():
    result = _profile()

    assert result.profile_range.start_time == pd.Timestamp(
        "2026-08-05 08:30", tz="America/New_York"
    )
    assert result.profile_range.end_time == pd.Timestamp(
        "2026-08-05 17:00", tz="America/New_York"
    )
    assert result.profile_range.session_name == "Previous completed New York"


def test_no_completed_session_is_unavailable():
    result = build_previous_new_york_profile(
        _bars(((100, 101, 100, 101, 10),)),
        evaluated_through=pd.Timestamp("2026-08-05 10:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert result.validity == ProfileValidity.NO_COMPLETED_SESSION
    assert result.data_quality == DataQuality.UNAVAILABLE
    assert result.bins == ()


def test_binning_poc_value_area_and_nodes_are_deterministic():
    result = _profile()

    assert result.profile_range.bin_size == 1.0
    assert [item.estimated_volume for item in result.bins] == [100, 200, 50]
    assert result.total_distributed_volume == result.total_reported_bar_volume
    assert result.value_area.poc_bin_index == 1
    assert result.value_area.poc_price == 101.5
    assert result.value_area.val == 100.0
    assert result.value_area.vah == 102.0
    assert result.value_area.included_bin_indices == (0, 1)
    assert result.value_area.achieved_percentage == pytest.approx(300 / 350)
    assert result.bins[1].node_kind == VolumeNodeKind.HVN
    assert result.bins[2].node_kind == VolumeNodeKind.LVN


def test_bar_volume_is_distributed_uniformly_across_intersected_bins():
    data = _bars(((100.2, 102.2, 100.2, 101.0, 90.0),))
    result = build_previous_new_york_profile(
        data,
        evaluated_through=pd.Timestamp("2026-08-05 18:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert [item.estimated_volume for item in result.bins] == [30, 30, 30]
    assert result.value_area.poc_bin_index == 0
    assert [node.kind for node in result.nodes] == [VolumeNodeKind.HVN]
    assert "degenerate" in " ".join(result.limitations).lower()


def test_flat_bar_allocates_all_volume_to_containing_bin():
    data = _bars(((100.25, 100.25, 100.25, 100.25, 75.0),))
    result = build_previous_new_york_profile(
        data,
        evaluated_through=pd.Timestamp("2026-08-05 18:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert len(result.bins) == 1
    assert result.bins[0].estimated_volume == 75.0


def test_poc_and_value_area_ties_choose_lower_price_first():
    data = _bars(
        (
            (100, 100.9, 100, 100.5, 100),
            (101, 101.9, 101, 101.5, 100),
            (102, 102.9, 102, 102.5, 100),
        )
    )
    result = build_previous_new_york_profile(
        data,
        evaluated_through=pd.Timestamp("2026-08-05 18:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert result.value_area.poc_bin_index == 0
    assert result.value_area.included_bin_indices == (0, 1, 2)


@pytest.mark.parametrize(
    ("frame", "expected"),
    (
        (_bars(((100, 101, 100, 101, 0),)), ProfileValidity.ZERO_VOLUME),
        (
            _bars(((100, 101, 100, 101, float("nan")),)),
            ProfileValidity.MISSING_VOLUME,
        ),
        (_bars(((100, 99, 100, 101, 10),)), ProfileValidity.INVALID_PRICE_DATA),
    ),
)
def test_invalid_source_data_returns_explicit_unavailable_result(frame, expected):
    result = build_previous_new_york_profile(
        frame,
        evaluated_through=pd.Timestamp("2026-08-05 18:00", tz="America/New_York"),
        tick_size=0.25,
    )

    assert result.validity == expected
    assert result.value_area is None


def test_missing_bars_are_visible_as_degraded_quality():
    result = _profile()

    assert result.data_quality == DataQuality.DEGRADED
    assert result.expected_bar_count == 510
    assert result.missing_bar_count == 507
    assert "missing 507" in " ".join(result.limitations)


def test_execution_zone_relationships_and_directional_value_edge_semantics():
    profile = _profile()
    bullish = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=99.5,
        execution_zone_top=100.0,
        direction=Direction.BULLISH,
    )
    bearish = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=102.0,
        execution_zone_top=102.5,
        direction=Direction.BEARISH,
    )

    assert ProfileRelationship.OVERLAPS_VAL in bullish.relationships
    assert bullish.directionally_supportive is True
    assert ProfileRelationship.OVERLAPS_VAH in bearish.relationships
    assert bearish.directionally_supportive is True


def test_poc_hvn_and_lvn_are_descriptive_not_automatic_support():
    profile = _profile()
    poc = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=101.4,
        execution_zone_top=101.6,
        direction=Direction.BULLISH,
    )
    lvn = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=102.1,
        execution_zone_top=102.8,
        direction=Direction.BULLISH,
    )

    assert ProfileRelationship.OVERLAPS_POC in poc.relationships
    assert ProfileRelationship.OVERLAPS_HVN in poc.relationships
    assert poc.directionally_supportive is False
    assert ProfileRelationship.OVERLAPS_LVN in lvn.relationships
    assert lvn.directionally_supportive is False


def test_outside_and_unavailable_assessments_are_explicit():
    profile = _profile()
    outside = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=110,
        execution_zone_top=111,
        direction=Direction.BULLISH,
    )
    unavailable = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=None,
        execution_zone_top=None,
        direction=Direction.BULLISH,
    )

    assert outside.relationships == (ProfileRelationship.OUTSIDE_PROFILE,)
    assert outside.directionally_supportive is False
    assert unavailable.relationships == (ProfileRelationship.UNAVAILABLE,)
    assert unavailable.evaluated is False


def test_result_makes_no_true_order_flow_claims():
    limitations = " ".join(_profile().limitations).lower()

    assert "cannot provide true tick-level volume" in limitations
    assert "no bid/ask" in limitations
    assert "delta" in limitations
