from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from analysis_pipeline import TimeframeAnalysis, analyze_timeframe
from confluence import ConfluenceResult, evaluate_confluence
from decision_authority import AuthorityDecision, DecisionAuthority
from fvg_lifecycle import FvgLifecycleResult, evaluate_fvg_lifecycles
from ifvg_integration import build_ifvg_confluence_factor
from instruments import InstrumentConfig
from order_block_engine import OrderBlockResult, evaluate_order_blocks
from order_block_integration import build_order_block_confluence_factor
from premium_discount_engine import DealingRangeResult, construct_dealing_range
from premium_discount_integration import build_premium_discount_confluence_factor
from sessions import detect_session_levels
from setup_overlay import SetupOverlay, build_setup_overlay
from volume_profile_engine import VolumeProfileResult, build_previous_new_york_profile
from volume_profile_integration import (
    attach_volume_profile_support,
    build_volume_profile_confluence_factor,
)


TIMEFRAMES = MappingProxyType({
    "4 Hour": {"interval": "4h", "role": "🧭 Context"},
    "1 Hour": {"interval": "1h", "role": "✅ Context"},
    "15 Minute": {"interval": "15m", "role": "📈 Setup"},
    "5 Minute": {"interval": "5m", "role": "🔍 Confirmation"},
    "1 Minute": {"interval": "1m", "role": "⚡ Trigger"},
})


@dataclass(frozen=True)
class AnalysisSettings:
    minimum_fvg_size: float
    maximum_fvgs: int


@dataclass(frozen=True)
class InstrumentAnalysisBundle:
    instrument: InstrumentConfig
    timeframe_analyses: Mapping[str, TimeframeAnalysis]
    session_levels: Mapping[str, dict]
    authority_decision: AuthorityDecision
    fvg_lifecycle_result: FvgLifecycleResult
    order_block_result: OrderBlockResult
    dealing_range_result: DealingRangeResult | None
    volume_profile_result: VolumeProfileResult | None
    setup_overlay: SetupOverlay
    confluence_result: ConfluenceResult

    def __post_init__(self) -> None:
        keys = {item.instrument_key for item in self.timeframe_analyses.values()}
        if keys != {self.instrument.key}:
            raise ValueError("Timeframe analyses do not match the bundle instrument.")
        if self.setup_overlay.instrument_key != self.instrument.key:
            raise ValueError("SetupOverlay does not match the bundle instrument.")
        if self.confluence_result.instrument_key != self.instrument.key:
            raise ValueError("Confluence does not match the bundle instrument.")
        if (
            self.volume_profile_result is not None
            and self.volume_profile_result.instrument_key != self.instrument.key
        ):
            raise ValueError("Volume Profile does not match the bundle instrument.")


def build_instrument_analysis(
    instrument: InstrumentConfig,
    market_frames: Mapping[str, pd.DataFrame],
    settings: AnalysisSettings,
) -> InstrumentAnalysisBundle:
    """Run the complete strategy once for one explicitly selected instrument."""

    expected = {item["interval"] for item in TIMEFRAMES.values()}
    if set(market_frames) != expected:
        raise ValueError("Market frames must contain every configured strategy timeframe.")
    defaults = instrument.strategy_defaults
    analyses = {
        name: analyze_timeframe(
            market_frames[info["interval"]],
            info["interval"],
            ema_period=defaults.ema_period,
            swing_lookback=defaults.swing_lookback,
            liquidity_tolerance=defaults.equal_level_tolerance_points,
            instrument_key=instrument.key,
        )
        for name, info in TIMEFRAMES.items()
    }
    session_levels = detect_session_levels(analyses["5 Minute"].data) or {}
    decision = DecisionAuthority().evaluate(
        analyses,
        session_levels,
        minimum_fvg_size=settings.minimum_fvg_size,
        maximum_fvgs=settings.maximum_fvgs,
    )
    execution = analyses["1 Minute"]
    lifecycle = evaluate_fvg_lifecycles(
        execution.data,
        execution.fvgs,
        timeframe="1m",
        instrument_key=instrument.key,
    )
    structure_events = tuple(
        event for event in (execution.bos, execution.choch) if event is not None
    )
    order_blocks = evaluate_order_blocks(
        execution.data,
        structure_events,
        timeframe="1m",
        instrument_key=instrument.key,
    )
    dealing_range = None
    if decision.roles.context_direction is not None:
        setup = analyses["15 Minute"]
        dealing_range = construct_dealing_range(
            setup.highs,
            setup.lows,
            direction=decision.roles.context_direction,
            timeframe="15m",
            evaluated_through=setup.data.index[-1] if not setup.data.empty else None,
            instrument_key=instrument.key,
        )
    overlay = build_setup_overlay(
        decision,
        analyses,
        session_levels,
        fvg_lifecycle_result=lifecycle,
        minimum_ifvg_size=settings.minimum_fvg_size,
        order_block_result=order_blocks,
        dealing_range_result=dealing_range,
        instrument_key=instrument.key,
    )
    profile = None
    if not execution.data.empty:
        profile = build_previous_new_york_profile(
            execution.data,
            evaluated_through=execution.data.index[-1],
            tick_size=instrument.tick_size,
            instrument_key=instrument.key,
        )
    overlay = attach_volume_profile_support(overlay, profile)
    factors = (
        build_ifvg_confluence_factor(overlay),
        build_order_block_confluence_factor(overlay),
        build_premium_discount_confluence_factor(overlay),
        build_volume_profile_confluence_factor(overlay),
    )
    confluence = evaluate_confluence(decision, overlay, factors)
    return InstrumentAnalysisBundle(
        instrument=instrument,
        timeframe_analyses=MappingProxyType(analyses),
        session_levels=MappingProxyType(session_levels),
        authority_decision=decision,
        fvg_lifecycle_result=lifecycle,
        order_block_result=order_blocks,
        dealing_range_result=dealing_range,
        volume_profile_result=profile,
        setup_overlay=overlay,
        confluence_result=confluence,
    )
