from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable

import pandas as pd

from timeframe_roles import Direction


SwingPoint = tuple[pd.Timestamp, float]


class DealingRangeValidity(str, Enum):
    VALID = "valid"
    INSUFFICIENT_SWINGS = "insufficient_swings"
    NO_COMPLETED_DIRECTIONAL_LEG = "no_completed_directional_leg"
    INVALIDATED_BY_LATER_SWING = "invalidated_by_later_swing"
    INVALID_BOUNDS = "invalid_bounds"


class DealingRangeSource(str, Enum):
    LATEST_COMPLETED_15M_DIRECTIONAL_SWING_LEG = (
        "latest_completed_15m_directional_swing_leg"
    )


class LocationClassification(str, Enum):
    PREMIUM = "premium"
    DISCOUNT = "discount"
    EQUILIBRIUM = "equilibrium"
    CROSSES_EQUILIBRIUM = "crosses_equilibrium"
    OUTSIDE_RANGE = "outside_range"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DealingRange:
    timeframe: str
    direction: Direction
    high: float
    low: float
    equilibrium: float
    high_time: pd.Timestamp
    low_time: pd.Timestamp
    formation_start_time: pd.Timestamp
    formation_end_time: pd.Timestamp
    formation_time: pd.Timestamp
    source: DealingRangeSource
    validity: DealingRangeValidity
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if _normalize_timeframe(self.timeframe) != "15m":
            raise ValueError("Dealing Range timeframe must be 15M.")
        if self.high <= self.low:
            raise ValueError("Dealing Range high must be greater than low.")
        expected_equilibrium = (self.high + self.low) / 2.0
        if self.equilibrium != expected_equilibrium:
            raise ValueError("Dealing Range equilibrium must equal its midpoint.")
        if self.validity != DealingRangeValidity.VALID:
            raise ValueError("A DealingRange object must be valid.")
        if self.formation_time != self.formation_end_time:
            raise ValueError("Formation time must equal the later range anchor.")
        if self.direction == Direction.BULLISH:
            if not self.low_time < self.high_time:
                raise ValueError("A bullish range must run from low to high.")
            if (
                self.formation_start_time != self.low_time
                or self.formation_end_time != self.high_time
            ):
                raise ValueError("Bullish formation timestamps must match anchors.")
        elif self.direction == Direction.BEARISH:
            if not self.high_time < self.low_time:
                raise ValueError("A bearish range must run from high to low.")
            if (
                self.formation_start_time != self.high_time
                or self.formation_end_time != self.low_time
            ):
                raise ValueError("Bearish formation timestamps must match anchors.")


@dataclass(frozen=True)
class DealingRangeResult:
    timeframe: str
    direction: Direction
    dealing_range: DealingRange | None
    validity: DealingRangeValidity
    evaluated_through: pd.Timestamp | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if _normalize_timeframe(self.timeframe) != "15m":
            raise ValueError("Dealing Range result timeframe must be 15M.")
        if self.validity == DealingRangeValidity.VALID:
            if self.dealing_range is None:
                raise ValueError("A valid result requires a dealing range.")
        elif self.dealing_range is not None:
            raise ValueError("An invalid result cannot expose a dealing range.")


@dataclass(frozen=True)
class PremiumDiscountAssessment:
    dealing_range: DealingRange
    location_top: float
    location_bottom: float
    location_midpoint: float
    classification: LocationClassification
    directionally_aligned: bool
    evaluated: bool
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.location_top < self.location_bottom:
            raise ValueError("Execution location top cannot be below bottom.")
        if self.location_midpoint != (
            self.location_top + self.location_bottom
        ) / 2.0:
            raise ValueError("Execution location midpoint is inconsistent.")


def construct_dealing_range(
    highs: Iterable[SwingPoint],
    lows: Iterable[SwingPoint],
    *,
    direction: Direction,
    timeframe: str,
    evaluated_through: pd.Timestamp | None = None,
) -> DealingRangeResult:
    """Build one latest completed directional 15M swing-leg range."""

    if _normalize_timeframe(timeframe) != "15m":
        raise ValueError("Premium/Discount requires 15M swing data.")
    sorted_highs = _normalize_swings(highs, name="high")
    sorted_lows = _normalize_swings(lows, name="low")
    evaluated = pd.Timestamp(evaluated_through) if evaluated_through is not None else None
    if not sorted_highs or not sorted_lows:
        return _invalid_result(
            direction,
            timeframe,
            DealingRangeValidity.INSUFFICIENT_SWINGS,
            evaluated,
            "Both confirmed 15M swing highs and lows are required.",
        )

    if direction == Direction.BULLISH:
        candidate = _latest_bullish_candidate(sorted_highs, sorted_lows)
    else:
        candidate = _latest_bearish_candidate(sorted_highs, sorted_lows)
    if candidate is None:
        return _invalid_result(
            direction,
            timeframe,
            DealingRangeValidity.NO_COMPLETED_DIRECTIONAL_LEG,
            evaluated,
            "No completed directional 15M swing leg is available.",
        )

    low_time, low, high_time, high = candidate
    if high <= low:
        return _invalid_result(
            direction,
            timeframe,
            DealingRangeValidity.INVALID_BOUNDS,
            evaluated,
            "The selected swing leg does not have valid price bounds.",
        )

    if direction == Direction.BULLISH:
        invalidated = any(
            time > high_time and price < low
            for time, price in sorted_lows
        )
        start_time, end_time = low_time, high_time
    else:
        invalidated = any(
            time > low_time and price > high
            for time, price in sorted_highs
        )
        start_time, end_time = high_time, low_time
    if invalidated:
        return _invalid_result(
            direction,
            timeframe,
            DealingRangeValidity.INVALIDATED_BY_LATER_SWING,
            evaluated,
            "The latest completed range was invalidated by a later confirmed swing.",
        )

    dealing_range = DealingRange(
        timeframe=timeframe,
        direction=direction,
        high=high,
        low=low,
        equilibrium=(high + low) / 2.0,
        high_time=high_time,
        low_time=low_time,
        formation_start_time=start_time,
        formation_end_time=end_time,
        formation_time=end_time,
        source=DealingRangeSource.LATEST_COMPLETED_15M_DIRECTIONAL_SWING_LEG,
        validity=DealingRangeValidity.VALID,
        limitations=(
            "Formation timestamps are confirmed-swing pivot timestamps; "
            "pivot confirmation timestamps are unavailable.",
        ),
    )
    return DealingRangeResult(
        timeframe=timeframe,
        direction=direction,
        dealing_range=dealing_range,
        validity=DealingRangeValidity.VALID,
        evaluated_through=evaluated,
        limitations=dealing_range.limitations,
    )


def evaluate_premium_discount(
    range_result: DealingRangeResult,
    *,
    execution_zone_top: float,
    execution_zone_bottom: float,
) -> PremiumDiscountAssessment | None:
    """Classify the existing authority FVG inside one valid dealing range."""

    if range_result.validity != DealingRangeValidity.VALID:
        return None
    dealing_range = range_result.dealing_range
    if dealing_range is None:
        return None
    top = float(execution_zone_top)
    bottom = float(execution_zone_bottom)
    if not math.isfinite(top) or not math.isfinite(bottom):
        raise ValueError("Execution location bounds must be finite.")
    if top < bottom:
        raise ValueError("Execution location top cannot be below bottom.")

    equilibrium = dealing_range.equilibrium
    if bottom < dealing_range.low or top > dealing_range.high:
        classification = LocationClassification.OUTSIDE_RANGE
    elif bottom == top:
        if top == equilibrium:
            classification = LocationClassification.EQUILIBRIUM
        elif top > equilibrium:
            classification = LocationClassification.PREMIUM
        else:
            classification = LocationClassification.DISCOUNT
    elif bottom >= equilibrium and top > bottom:
        classification = LocationClassification.PREMIUM
    elif top <= equilibrium and top > bottom:
        classification = LocationClassification.DISCOUNT
    else:
        classification = LocationClassification.CROSSES_EQUILIBRIUM

    aligned = (
        dealing_range.direction == Direction.BULLISH
        and classification == LocationClassification.DISCOUNT
    ) or (
        dealing_range.direction == Direction.BEARISH
        and classification == LocationClassification.PREMIUM
    )
    explanation = (
        f"The authority execution FVG is {classification.value.replace('_', ' ')} "
        f"within the active 15M dealing-range evaluation."
    )
    return PremiumDiscountAssessment(
        dealing_range=dealing_range,
        location_top=top,
        location_bottom=bottom,
        location_midpoint=(top + bottom) / 2.0,
        classification=classification,
        directionally_aligned=aligned,
        evaluated=True,
        explanation=explanation,
        limitations=range_result.limitations,
    )


def _latest_bullish_candidate(
    highs: tuple[SwingPoint, ...],
    lows: tuple[SwingPoint, ...],
) -> tuple[pd.Timestamp, float, pd.Timestamp, float] | None:
    candidates = []
    for high_time, high in highs:
        preceding = [item for item in lows if item[0] < high_time]
        if not preceding:
            continue
        low_time, low = max(preceding, key=lambda item: (item[0], item[1]))
        if high > low:
            candidates.append((low_time, low, high_time, high))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[2], item[0], item[3], -item[1]))


def _latest_bearish_candidate(
    highs: tuple[SwingPoint, ...],
    lows: tuple[SwingPoint, ...],
) -> tuple[pd.Timestamp, float, pd.Timestamp, float] | None:
    candidates = []
    for low_time, low in lows:
        preceding = [item for item in highs if item[0] < low_time]
        if not preceding:
            continue
        high_time, high = max(preceding, key=lambda item: (item[0], item[1]))
        if high > low:
            candidates.append((low_time, low, high_time, high))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[2], -item[1], item[3]))


def _normalize_swings(
    swings: Iterable[SwingPoint],
    *,
    name: str,
) -> tuple[SwingPoint, ...]:
    by_time: dict[pd.Timestamp, float] = {}
    for timestamp, price in swings:
        time = pd.Timestamp(timestamp)
        value = float(price)
        if not math.isfinite(value):
            raise ValueError(f"{name.title()} swing prices must be finite.")
        if time in by_time and by_time[time] != value:
            raise ValueError(f"Conflicting {name} swings share timestamp {time}.")
        by_time[time] = value
    return tuple(sorted(by_time.items(), key=lambda item: (item[0], item[1])))


def _invalid_result(
    direction: Direction,
    timeframe: str,
    validity: DealingRangeValidity,
    evaluated_through: pd.Timestamp | None,
    limitation: str,
) -> DealingRangeResult:
    return DealingRangeResult(
        timeframe=timeframe,
        direction=direction,
        dealing_range=None,
        validity=validity,
        evaluated_through=evaluated_through,
        limitations=(limitation,),
    )


def _normalize_timeframe(timeframe: str) -> str:
    normalized = timeframe.strip().lower().replace(" ", "")
    if normalized in {"15m", "15min", "15minute"}:
        return "15m"
    return normalized
