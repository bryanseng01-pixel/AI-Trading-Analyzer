from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

import pandas as pd

from timeframe_roles import Direction


class OrderBlockState(str, Enum):
    UNTOUCHED = "untouched"
    TOUCHED = "touched"
    PARTIALLY_MITIGATED = "partially_mitigated"
    FULLY_MITIGATED = "fully_mitigated"
    INVALIDATED = "invalidated"


class StructureEventType(str, Enum):
    BOS = "BOS"
    CHOCH = "CHoCH"


class OrderBlockZoneBasis(str, Enum):
    FULL_CANDLE_RANGE = "full_candle_range"


@dataclass(frozen=True)
class StructureBreakRef:
    direction: Direction
    event_type: StructureEventType
    time: pd.Timestamp
    level: float

    @classmethod
    def from_mapping(cls, event: Mapping[str, Any]) -> "StructureBreakRef":
        return cls(
            direction=Direction(event["direction"]),
            event_type=StructureEventType(event["text"]),
            time=pd.Timestamp(event["time"]),
            level=float(event["level"]),
        )


@dataclass(frozen=True)
class OrderBlockRules:
    displacement_body_lookback: int = 20
    minimum_baseline_bars: int = 5
    minimum_body_multiple: float = 1.5
    minimum_body_to_range: float = 0.60
    maximum_source_distance: int = 10
    zone_basis: OrderBlockZoneBasis = OrderBlockZoneBasis.FULL_CANDLE_RANGE

    def __post_init__(self) -> None:
        if self.displacement_body_lookback < self.minimum_baseline_bars:
            raise ValueError("Displacement lookback must cover minimum baseline bars.")
        if self.minimum_baseline_bars < 1:
            raise ValueError("minimum_baseline_bars must be positive.")
        if self.minimum_body_multiple <= 0:
            raise ValueError("minimum_body_multiple must be positive.")
        if not 0.0 < self.minimum_body_to_range <= 1.0:
            raise ValueError("minimum_body_to_range must be between 0 and 1.")
        if self.maximum_source_distance < 1:
            raise ValueError("maximum_source_distance must be positive.")


@dataclass(frozen=True)
class OrderBlock:
    timeframe: str
    direction: Direction
    top: float
    bottom: float
    formation_time: pd.Timestamp
    source_candle_time: pd.Timestamp
    displacement_time: pd.Timestamp
    structure_event_type: StructureEventType
    structure_level: float
    state: OrderBlockState
    first_touch_time: pd.Timestamp | None
    partial_mitigation_time: pd.Timestamp | None
    mitigation_time: pd.Timestamp | None
    invalidation_time: pd.Timestamp | None
    last_evaluated_time: pd.Timestamp | None
    quality: str | None = None
    still_respected: bool | None = None

    def __post_init__(self) -> None:
        if self.top <= self.bottom:
            raise ValueError("Order Block top must be greater than bottom.")
        if self.formation_time < self.source_candle_time:
            raise ValueError("Formation cannot precede the source candle.")
        if self.displacement_time != self.formation_time:
            raise ValueError("Initial displacement time must equal formation time.")
        for timestamp in (
            self.first_touch_time,
            self.partial_mitigation_time,
            self.mitigation_time,
            self.invalidation_time,
            self.last_evaluated_time,
        ):
            if timestamp is not None and timestamp <= self.formation_time:
                raise ValueError("Lifecycle timestamps must follow formation.")

    @property
    def active(self) -> bool:
        return self.state in {
            OrderBlockState.UNTOUCHED,
            OrderBlockState.TOUCHED,
            OrderBlockState.PARTIALLY_MITIGATED,
        }

    @property
    def mitigated(self) -> bool:
        return self.state in {
            OrderBlockState.FULLY_MITIGATED,
            OrderBlockState.INVALIDATED,
        }

    @property
    def invalidated(self) -> bool:
        return self.state == OrderBlockState.INVALIDATED

    @property
    def size(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class OrderBlockResult:
    timeframe: str
    evaluated_through: pd.Timestamp | None
    order_blocks: tuple[OrderBlock, ...]
    active_order_blocks: tuple[OrderBlock, ...]
    limitations: tuple[str, ...]


def evaluate_order_blocks(
    data: pd.DataFrame,
    structure_events: Iterable[StructureBreakRef | Mapping[str, Any]],
    *,
    timeframe: str,
    rules: OrderBlockRules = OrderBlockRules(),
) -> OrderBlockResult:
    """Form and evaluate structural Order Blocks without issuing decisions."""

    _validate_data(data)
    events = tuple(_as_event(event) for event in structure_events)
    ambiguous_times = {
        event.time
        for event in events
        if len({item.direction for item in events if item.time == event.time}) > 1
    }
    limitations = [
        f"Opposing structure events are ambiguous at {timestamp}."
        for timestamp in sorted(ambiguous_times)
    ]
    formed: dict[tuple[Any, ...], OrderBlock] = {}

    for event in sorted(
        (item for item in events if item.time not in ambiguous_times),
        key=lambda item: (item.time, _event_priority(item.event_type)),
    ):
        candidate, limitation = _form_order_block(
            data,
            event,
            timeframe=timeframe,
            rules=rules,
        )
        if limitation is not None:
            limitations.append(limitation)
        if candidate is None:
            continue
        key = (
            candidate.direction,
            candidate.source_candle_time,
            candidate.formation_time,
            candidate.bottom,
            candidate.top,
        )
        existing = formed.get(key)
        if (
            existing is None
            or _event_priority(candidate.structure_event_type)
            > _event_priority(existing.structure_event_type)
        ):
            formed[key] = candidate

    order_blocks = tuple(
        sorted(
            formed.values(),
            key=lambda block: (
                block.formation_time,
                block.source_candle_time,
                block.direction.value,
                block.bottom,
                block.top,
            ),
        )
    )
    return OrderBlockResult(
        timeframe=timeframe,
        evaluated_through=(
            pd.Timestamp(data.index[-1]) if not data.empty else None
        ),
        order_blocks=order_blocks,
        active_order_blocks=tuple(block for block in order_blocks if block.active),
        limitations=tuple(limitations),
    )


def select_relevant_order_block(
    result: OrderBlockResult,
    *,
    direction: Direction,
    authority_zone_bottom: float,
    authority_zone_top: float,
) -> OrderBlock | None:
    """Select one active directional block by strict geometric overlap."""

    if authority_zone_top <= authority_zone_bottom:
        raise ValueError("Authority zone top must be greater than bottom.")
    authority_midpoint = (authority_zone_top + authority_zone_bottom) / 2.0
    candidates = []
    for block in result.active_order_blocks:
        if block.direction != direction:
            continue
        overlap_bottom = max(authority_zone_bottom, block.bottom)
        overlap_top = min(authority_zone_top, block.top)
        if overlap_top <= overlap_bottom:
            continue
        candidates.append((block, overlap_top - overlap_bottom))
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -item[1],
            abs(((item[0].top + item[0].bottom) / 2.0) - authority_midpoint),
            -item[0].formation_time.value,
            -item[0].source_candle_time.value,
            -_event_priority(item[0].structure_event_type),
            item[0].direction.value,
            item[0].bottom,
            item[0].top,
        ),
    )[0]


def _form_order_block(
    data: pd.DataFrame,
    event: StructureBreakRef,
    *,
    timeframe: str,
    rules: OrderBlockRules,
) -> tuple[OrderBlock | None, str | None]:
    if event.time not in data.index:
        return None, f"Structure event time {event.time} is absent from OHLC data."
    event_position = int(data.index.get_loc(event.time))
    if event_position == 0:
        return None, f"Structure event at {event.time} has no source history."
    event_candle = data.iloc[event_position]
    preceding = data.iloc[
        max(0, event_position - rules.displacement_body_lookback) : event_position
    ]
    if len(preceding) < rules.minimum_baseline_bars:
        return None, f"Insufficient displacement baseline before {event.time}."
    bodies = (preceding["Close"] - preceding["Open"]).abs()
    baseline = float(bodies.median())
    body = abs(float(event_candle["Close"] - event_candle["Open"]))
    candle_range = float(event_candle["High"] - event_candle["Low"])
    if baseline <= 0.0 or candle_range <= 0.0:
        return None, f"Invalid displacement baseline or range at {event.time}."
    if not _event_close_confirmed(event, event_candle):
        return None, f"Structure event at {event.time} is not close-confirmed."
    if not _aligned_candle(event.direction, event_candle):
        return None, f"Structure break candle at {event.time} is not directional."
    if (
        body < baseline * rules.minimum_body_multiple
        or body / candle_range < rules.minimum_body_to_range
    ):
        return None, f"Structure break candle at {event.time} lacks displacement."

    source_position = event_position - 1
    distance = 1
    while (
        source_position >= 0
        and _aligned_candle(event.direction, data.iloc[source_position])
    ):
        source_position -= 1
        distance += 1
    if source_position < 0 or distance > rules.maximum_source_distance:
        return None, f"No bounded opposing source candle before {event.time}."
    source = data.iloc[source_position]
    if not _opposing_candle(event.direction, source):
        return None, f"No strict opposing source candle before {event.time}."

    top = float(source["High"])
    bottom = float(source["Low"])
    if top <= bottom:
        return None, f"Source candle at {data.index[source_position]} has no range."
    block = _evaluate_lifecycle(
        data,
        timeframe=timeframe,
        direction=event.direction,
        top=top,
        bottom=bottom,
        formation_time=event.time,
        source_candle_time=pd.Timestamp(data.index[source_position]),
        event_type=event.event_type,
        structure_level=event.level,
    )
    return block, None


def _evaluate_lifecycle(
    data: pd.DataFrame,
    *,
    timeframe: str,
    direction: Direction,
    top: float,
    bottom: float,
    formation_time: pd.Timestamp,
    source_candle_time: pd.Timestamp,
    event_type: StructureEventType,
    structure_level: float,
) -> OrderBlock:
    state = OrderBlockState.UNTOUCHED
    first_touch_time = None
    partial_mitigation_time = None
    mitigation_time = None
    invalidation_time = None
    last_evaluated_time = None
    maximum_interaction = 0

    for timestamp, candle in data.loc[data.index > formation_time].iterrows():
        timestamp = pd.Timestamp(timestamp)
        last_evaluated_time = timestamp
        if state == OrderBlockState.INVALIDATED:
            continue

        interaction = _interaction_depth(direction, candle, top=top, bottom=bottom)
        maximum_interaction = max(maximum_interaction, interaction)
        if interaction >= 1 and first_touch_time is None:
            first_touch_time = timestamp
        if interaction == 2 and partial_mitigation_time is None:
            partial_mitigation_time = timestamp
        if interaction == 3 and mitigation_time is None:
            mitigation_time = timestamp

        if _invalidated(direction, float(candle["Close"]), top=top, bottom=bottom):
            state = OrderBlockState.INVALIDATED
            invalidation_time = timestamp
            if first_touch_time is None:
                first_touch_time = timestamp
            if mitigation_time is None:
                mitigation_time = timestamp
        elif maximum_interaction == 3:
            state = OrderBlockState.FULLY_MITIGATED
        elif maximum_interaction == 2:
            state = OrderBlockState.PARTIALLY_MITIGATED
        elif maximum_interaction == 1:
            state = OrderBlockState.TOUCHED

    return OrderBlock(
        timeframe=timeframe,
        direction=direction,
        top=top,
        bottom=bottom,
        formation_time=formation_time,
        source_candle_time=source_candle_time,
        displacement_time=formation_time,
        structure_event_type=event_type,
        structure_level=structure_level,
        state=state,
        first_touch_time=first_touch_time,
        partial_mitigation_time=partial_mitigation_time,
        mitigation_time=mitigation_time,
        invalidation_time=invalidation_time,
        last_evaluated_time=last_evaluated_time,
        quality=None,
        still_respected=None,
    )


def _interaction_depth(
    direction: Direction,
    candle: pd.Series,
    *,
    top: float,
    bottom: float,
) -> int:
    if direction == Direction.BULLISH:
        extreme = float(candle["Low"])
        if extreme > top:
            return 0
        if extreme == top:
            return 1
        if extreme > bottom:
            return 2
        return 3
    extreme = float(candle["High"])
    if extreme < bottom:
        return 0
    if extreme == bottom:
        return 1
    if extreme < top:
        return 2
    return 3


def _invalidated(
    direction: Direction,
    close: float,
    *,
    top: float,
    bottom: float,
) -> bool:
    if direction == Direction.BULLISH:
        return close < bottom
    return close > top


def _event_close_confirmed(event: StructureBreakRef, candle: pd.Series) -> bool:
    close = float(candle["Close"])
    if event.direction == Direction.BULLISH:
        return close > event.level
    return close < event.level


def _aligned_candle(direction: Direction, candle: pd.Series) -> bool:
    if direction == Direction.BULLISH:
        return bool(candle["Close"] > candle["Open"])
    return bool(candle["Close"] < candle["Open"])


def _opposing_candle(direction: Direction, candle: pd.Series) -> bool:
    if direction == Direction.BULLISH:
        return bool(candle["Close"] < candle["Open"])
    return bool(candle["Close"] > candle["Open"])


def _event_priority(event_type: StructureEventType) -> int:
    return 1 if event_type == StructureEventType.CHOCH else 0


def _as_event(
    event: StructureBreakRef | Mapping[str, Any],
) -> StructureBreakRef:
    if isinstance(event, StructureBreakRef):
        return event
    return StructureBreakRef.from_mapping(event)


def _validate_data(data: pd.DataFrame) -> None:
    if data is None:
        raise ValueError("Order Block evaluation requires an OHLC frame.")
    required = {"Open", "High", "Low", "Close"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Order Block data is missing columns: {sorted(missing)}")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("Order Block data index must be increasing and unique.")
