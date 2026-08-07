import pandas as pd

from instrument_pipeline import AnalysisSettings, TIMEFRAMES, build_instrument_analysis
from instruments import ES, NQ
from workstation_view import TimelineState, build_trading_workstation_view


def _frames(ohlc_factory):
    rows = [(100 + index, 103 + index, 98 + index, 102 + index, 100) for index in range(80)]
    return {item["interval"]: ohlc_factory(rows) for item in TIMEFRAMES.values()}


def test_view_is_completed_presentation_data_from_one_bundle(ohlc_factory):
    bundle = build_instrument_analysis(
        NQ, _frames(ohlc_factory), AnalysisSettings(5.0, 3)
    )
    refreshed = pd.Timestamp("2026-08-07 09:30", tz="America/New_York")
    view = build_trading_workstation_view(
        bundle, selected_chart_timeframe="5 Minute", refreshed_at=refreshed
    )

    assert view.top_bar.instrument_key == "NQ"
    assert view.top_bar.chart_timeframe == "5 Minute"
    assert view.authority.status == bundle.authority_decision.recommendation
    assert view.authority.next_event == bundle.authority_decision.playbook["next_event"]
    assert view.current_setup.stage == bundle.authority_decision.playbook["phase"]
    assert view.current_setup.waiting_event == bundle.authority_decision.playbook["next_event"]
    assert view.current_setup.next_milestone == bundle.authority_decision.trade_plan["next_action"]
    assert len(view.required_gates) == 6
    assert view.authority.market_story[-1].startswith("Optional location evidence")
    assert not hasattr(view, "recommendation")


def test_view_preserves_instrument_scope_and_chart_is_display_only(ohlc_factory):
    bundle = build_instrument_analysis(
        ES, _frames(ohlc_factory), AnalysisSettings(5.0, 3)
    )
    refreshed = pd.Timestamp("2026-08-07 09:30", tz="America/New_York")
    four_hour = build_trading_workstation_view(
        bundle, selected_chart_timeframe="4 Hour", refreshed_at=refreshed
    )
    one_minute = build_trading_workstation_view(
        bundle, selected_chart_timeframe="1 Minute", refreshed_at=refreshed
    )

    assert four_hour.authority == one_minute.authority
    assert four_hour.current_setup == one_minute.current_setup
    assert four_hour.top_bar.instrument_key == one_minute.top_bar.instrument_key == "ES"
    assert four_hour.top_bar.chart_timeframe != one_minute.top_bar.chart_timeframe


def test_timeline_has_no_invented_htf_or_setup_timestamps(ohlc_factory):
    bundle = build_instrument_analysis(
        NQ, _frames(ohlc_factory), AnalysisSettings(5.0, 3)
    )
    view = build_trading_workstation_view(
        bundle,
        selected_chart_timeframe="4 Hour",
        refreshed_at=pd.Timestamp("2026-08-07 09:30", tz="America/New_York"),
    )
    items = {item.key: item for item in view.timeline}

    assert items["htf_context"].timestamp is None
    assert items["setup_15m"].timestamp is None
    assert items["optional_confluence"].state in {
        TimelineState.COMPLETE,
        TimelineState.UNAVAILABLE,
    }


def test_invalid_chart_timeframe_is_rejected(ohlc_factory):
    import pytest

    bundle = build_instrument_analysis(
        NQ, _frames(ohlc_factory), AnalysisSettings(5.0, 3)
    )
    with pytest.raises(ValueError):
        build_trading_workstation_view(
            bundle,
            selected_chart_timeframe="30 Minute",
            refreshed_at=pd.Timestamp("2026-08-07 09:30", tz="America/New_York"),
        )
