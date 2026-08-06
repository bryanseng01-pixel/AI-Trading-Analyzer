from dataclasses import dataclass
from typing import Any

import pandas as pd

from fair_value_gap import detect_fair_value_gaps
from indicators import calculate_ema, get_trend
from liquidity import find_equal_highs, find_equal_lows
from market_structure import (
    detect_bos,
    detect_choch,
    determine_structure,
    label_highs,
    label_lows,
)
from structure import find_swing_points


SwingPoint = tuple[pd.Timestamp, float]
StructureLabel = tuple[pd.Timestamp, float, str]


@dataclass(frozen=True)
class TimeframeAnalysis:
    """Complete technical-analysis result for one timeframe."""

    timeframe: str
    data: pd.DataFrame
    trend: str
    highs: list[SwingPoint]
    lows: list[SwingPoint]
    high_labels: list[StructureLabel]
    low_labels: list[StructureLabel]
    structure: str
    bos: dict[str, Any] | None
    choch: dict[str, Any] | None
    fvgs: list[dict[str, Any]]
    equal_highs: list[dict[str, Any]]
    equal_lows: list[dict[str, Any]]


def analyze_timeframe(
    data: pd.DataFrame,
    timeframe: str,
    *,
    ema_period: int = 50,
    swing_lookback: int = 3,
    liquidity_tolerance: float = 5.0,
) -> TimeframeAnalysis:
    """Run the existing technical rules once for a single timeframe."""

    analyzed_data = calculate_ema(data.copy(), period=ema_period)
    trend = get_trend(analyzed_data)
    highs, lows = find_swing_points(
        analyzed_data,
        lookback=swing_lookback,
    )
    high_labels = label_highs(highs)
    low_labels = label_lows(lows)
    structure = determine_structure(high_labels, low_labels)

    return TimeframeAnalysis(
        timeframe=timeframe,
        data=analyzed_data,
        trend=trend,
        highs=highs,
        lows=lows,
        high_labels=high_labels,
        low_labels=low_labels,
        structure=structure,
        bos=detect_bos(
            analyzed_data,
            high_labels,
            low_labels,
            structure,
        ),
        choch=detect_choch(
            analyzed_data,
            high_labels,
            low_labels,
            structure,
        ),
        fvgs=detect_fair_value_gaps(analyzed_data),
        equal_highs=find_equal_highs(
            highs,
            tolerance=liquidity_tolerance,
        ),
        equal_lows=find_equal_lows(
            lows,
            tolerance=liquidity_tolerance,
        ),
    )


def select_active_fvgs(
    analysis: TimeframeAnalysis,
    *,
    minimum_size: float,
    maximum_count: int,
) -> list[dict[str, Any]]:
    """Apply the dashboard's existing active-FVG filters to one analysis."""

    if analysis.data.empty:
        return []

    current_price = float(analysis.data["Close"].iloc[-1])
    active_fvgs = [
        fvg
        for fvg in analysis.fvgs
        if not fvg["mitigated"]
        and (fvg["top"] - fvg["bottom"]) >= minimum_size
    ]
    active_fvgs.sort(
        key=lambda fvg: abs(
            ((fvg["top"] + fvg["bottom"]) / 2) - current_price
        )
    )
    return active_fvgs[:maximum_count]
