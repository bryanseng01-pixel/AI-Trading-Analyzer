from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

import pandas as pd

from timeframe_roles import Direction


class FvgLifecycleState(str, Enum):
    UNTOUCHED = "untouched"
    ENTERED = "entered"
    PARTIALLY_MITIGATED = "partially_mitigated"
    FULLY_FILLED = "fully_filled"
    INVERTED = "inverted"
    INVALIDATED = "invalidated"


class ImbalanceKind(str, Enum):
    FVG = "fvg"
    IFVG = "ifvg"


@dataclass(frozen=True)
class DetectedFvg:
    """Typed formation produced by the existing high/low FVG rule."""

    direction: Direction
    top: float
    bottom: float
    formation_start_time: pd.Timestamp
    formation_time: pd.Timestamp

    def __post_init__(self) -> None:
        if self.top <= self.bottom:
            raise ValueError("FVG top must be greater than bottom.")
        if self.formation_time < self.formation_start_time:
            raise ValueError("FVG formation time cannot precede its start.")

    @classmethod
    def from_mapping(cls, fvg: Mapping[str, Any]) -> "DetectedFvg":
        """Adapt the current dictionary contract without changing it."""

        return cls(
            direction=Direction(fvg["type"]),
            top=float(fvg["top"]),
            bottom=float(fvg["bottom"]),
            formation_start_time=pd.Timestamp(fvg["start_time"]),
            formation_time=pd.Timestamp(fvg["end_time"]),
        )


@dataclass(frozen=True)
class FvgLifecycle:
    """Immutable current snapshot of one original FVG and any inversion."""

    timeframe: str
    original_direction: Direction
    current_direction: Direction | None
    kind: ImbalanceKind
    state: FvgLifecycleState
    top: float
    bottom: float
    formation_start_time: pd.Timestamp
    formation_time: pd.Timestamp
    inversion_time: pd.Timestamp | None
    first_entry_time: pd.Timestamp | None
    partial_mitigation_time: pd.Timestamp | None
    full_fill_time: pd.Timestamp | None
    invalidation_time: pd.Timestamp | None
    last_evaluated_time: pd.Timestamp | None
    inversion_boundary: float
    fill_percentage: float
    legacy_mitigated: bool
    quality: str | None = None

    def __post_init__(self) -> None:
        if self.top <= self.bottom:
            raise ValueError("FVG top must be greater than bottom.")
        if not 0.0 <= self.fill_percentage <= 1.0:
            raise ValueError("fill_percentage must be between 0.0 and 1.0.")
        if self.formation_time < self.formation_start_time:
            raise ValueError("FVG formation time cannot precede its start.")
        if self.kind == ImbalanceKind.FVG:
            if self.current_direction != self.original_direction:
                raise ValueError("An FVG must retain its original direction.")
            if self.inversion_time is not None:
                raise ValueError("An uninverted FVG cannot have inversion_time.")
        if self.state == FvgLifecycleState.INVERTED:
            if self.kind != ImbalanceKind.IFVG or self.inversion_time is None:
                raise ValueError("An inverted zone must be a confirmed IFVG.")
            if self.current_direction != _opposite(self.original_direction):
                raise ValueError("An IFVG direction must oppose its original FVG.")
        if self.state == FvgLifecycleState.INVALIDATED:
            if self.kind != ImbalanceKind.IFVG or self.inversion_time is None:
                raise ValueError("Only a confirmed IFVG can be invalidated.")
            if self.current_direction is not None:
                raise ValueError("An invalidated IFVG has no active direction.")

    @property
    def size(self) -> float:
        return self.top - self.bottom

    @property
    def active(self) -> bool:
        return self.state in {
            FvgLifecycleState.UNTOUCHED,
            FvgLifecycleState.ENTERED,
            FvgLifecycleState.PARTIALLY_MITIGATED,
            FvgLifecycleState.INVERTED,
        }


@dataclass(frozen=True)
class FvgLifecycleResult:
    timeframe: str
    evaluated_through: pd.Timestamp | None
    zones: tuple[FvgLifecycle, ...]
    active_fvgs: tuple[FvgLifecycle, ...]
    active_ifvgs: tuple[FvgLifecycle, ...]
    limitations: tuple[str, ...]


def evaluate_fvg_lifecycles(
    data: pd.DataFrame,
    formed_fvgs: Iterable[DetectedFvg | Mapping[str, Any]],
    *,
    timeframe: str,
) -> FvgLifecycleResult:
    """Evaluate wick interaction and close-confirmed inversion only."""

    _validate_data(data)
    formations = tuple(_as_detected(fvg) for fvg in formed_fvgs)
    zones = tuple(
        _evaluate_one(data, formation, timeframe=timeframe)
        for formation in formations
    )
    evaluated_through = (
        pd.Timestamp(data.index[-1]) if not data.empty else None
    )
    return FvgLifecycleResult(
        timeframe=timeframe,
        evaluated_through=evaluated_through,
        zones=zones,
        active_fvgs=tuple(
            zone
            for zone in zones
            if zone.active and zone.kind == ImbalanceKind.FVG
        ),
        active_ifvgs=tuple(
            zone
            for zone in zones
            if zone.active and zone.kind == ImbalanceKind.IFVG
        ),
        limitations=(),
    )


def select_relevant_imbalance(
    lifecycle_result: FvgLifecycleResult,
    *,
    direction: Direction,
    current_price: float,
    minimum_size: float,
    allowed_kinds: frozenset[ImbalanceKind],
) -> FvgLifecycle | None:
    """Select one active directional zone without deciding allowed kinds."""

    candidates = [
        zone
        for zone in lifecycle_result.zones
        if zone.active
        and zone.current_direction == direction
        and zone.kind in allowed_kinds
        and zone.size >= minimum_size
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda zone: (
            abs(((zone.top + zone.bottom) / 2.0) - current_price),
            -zone.formation_time.value,
            -zone.formation_start_time.value,
            zone.kind.value,
            zone.original_direction.value,
            zone.bottom,
            zone.top,
        ),
    )


def _evaluate_one(
    data: pd.DataFrame,
    formation: DetectedFvg,
    *,
    timeframe: str,
) -> FvgLifecycle:
    direction = formation.direction
    state = FvgLifecycleState.UNTOUCHED
    kind = ImbalanceKind.FVG
    current_direction: Direction | None = direction
    fill_percentage = 0.0
    first_entry_time = None
    partial_mitigation_time = None
    full_fill_time = None
    inversion_time = None
    invalidation_time = None
    last_evaluated_time = None

    candles = data.loc[data.index > formation.formation_time]
    for timestamp, candle in candles.iterrows():
        timestamp = pd.Timestamp(timestamp)
        last_evaluated_time = timestamp

        if state == FvgLifecycleState.INVERTED:
            if _ifvg_invalidated(direction, float(candle["Close"]), formation):
                state = FvgLifecycleState.INVALIDATED
                current_direction = None
                invalidation_time = timestamp
            continue
        if state == FvgLifecycleState.INVALIDATED:
            continue

        penetration, entered = _fill_interaction(candle, formation)
        fill_percentage = max(fill_percentage, penetration)
        if entered and first_entry_time is None:
            first_entry_time = timestamp
        if 0.0 < penetration < 1.0 and partial_mitigation_time is None:
            partial_mitigation_time = timestamp
        if penetration == 1.0 and full_fill_time is None:
            full_fill_time = timestamp

        if _inversion_confirmed(direction, float(candle["Close"]), formation):
            state = FvgLifecycleState.INVERTED
            kind = ImbalanceKind.IFVG
            current_direction = _opposite(direction)
            inversion_time = timestamp
            fill_percentage = 1.0
            if first_entry_time is None:
                first_entry_time = timestamp
            if full_fill_time is None:
                full_fill_time = timestamp
        elif fill_percentage == 1.0:
            state = FvgLifecycleState.FULLY_FILLED
        elif fill_percentage > 0.0:
            state = FvgLifecycleState.PARTIALLY_MITIGATED
        elif first_entry_time is not None:
            state = FvgLifecycleState.ENTERED

    return FvgLifecycle(
        timeframe=timeframe,
        original_direction=direction,
        current_direction=current_direction,
        kind=kind,
        state=state,
        top=formation.top,
        bottom=formation.bottom,
        formation_start_time=formation.formation_start_time,
        formation_time=formation.formation_time,
        inversion_time=inversion_time,
        first_entry_time=first_entry_time,
        partial_mitigation_time=partial_mitigation_time,
        full_fill_time=full_fill_time,
        invalidation_time=invalidation_time,
        last_evaluated_time=last_evaluated_time,
        inversion_boundary=(
            formation.bottom
            if direction == Direction.BULLISH
            else formation.top
        ),
        fill_percentage=fill_percentage,
        legacy_mitigated=fill_percentage == 1.0,
        quality=None,
    )


def _fill_interaction(
    candle: pd.Series,
    formation: DetectedFvg,
) -> tuple[float, bool]:
    size = formation.top - formation.bottom
    if formation.direction == Direction.BULLISH:
        extreme = float(candle["Low"])
        entered = extreme <= formation.top
        penetration = (formation.top - extreme) / size if entered else 0.0
    else:
        extreme = float(candle["High"])
        entered = extreme >= formation.bottom
        penetration = (extreme - formation.bottom) / size if entered else 0.0
    return min(max(penetration, 0.0), 1.0), entered


def _inversion_confirmed(
    direction: Direction,
    close: float,
    formation: DetectedFvg,
) -> bool:
    if direction == Direction.BULLISH:
        return close < formation.bottom
    return close > formation.top


def _ifvg_invalidated(
    original_direction: Direction,
    close: float,
    formation: DetectedFvg,
) -> bool:
    if original_direction == Direction.BULLISH:
        return close > formation.top
    return close < formation.bottom


def _opposite(direction: Direction) -> Direction:
    if direction == Direction.BULLISH:
        return Direction.BEARISH
    return Direction.BULLISH


def _as_detected(
    fvg: DetectedFvg | Mapping[str, Any],
) -> DetectedFvg:
    if isinstance(fvg, DetectedFvg):
        return fvg
    return DetectedFvg.from_mapping(fvg)


def _validate_data(data: pd.DataFrame) -> None:
    required = {"High", "Low", "Close"}
    if data is None:
        raise ValueError("Lifecycle evaluation requires an OHLC frame.")
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Lifecycle data is missing columns: {sorted(missing)}")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("Lifecycle data index must be increasing and unique.")
