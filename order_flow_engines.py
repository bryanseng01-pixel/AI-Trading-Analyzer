from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import pandas as pd

from order_flow_models import (
    AggressorSide,
    ExecutionLocationWindow,
    OrderFlowAnalysisMetadata,
    OrderFlowWindow,
)

if TYPE_CHECKING:
    from cumulative_delta_engine import (
        CumulativeDeltaAnchor,
        CumulativeDeltaResetEvent,
    )
    from delta_aggregation import DeltaBucketSeries
    from delta_engine import DeltaLocationAssessment


@dataclass(frozen=True)
class DeltaBucket:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    ask_volume: float
    bid_volume: float
    unknown_volume: float
    delta: float
    total_classified_volume: float


@dataclass(frozen=True)
class DeltaResult:
    metadata: OrderFlowAnalysisMetadata
    buckets: tuple[DeltaBucket, ...]
    total_ask_volume: float
    total_bid_volume: float
    total_unknown_volume: float
    net_delta: float
    classification_coverage: float


@dataclass(frozen=True)
class CumulativeDeltaPoint:
    timestamp: pd.Timestamp
    bucket_delta: float
    cumulative_delta: float


@dataclass(frozen=True)
class CumulativeDeltaResult:
    metadata: OrderFlowAnalysisMetadata
    anchor: "CumulativeDeltaAnchor"
    anchor_time: pd.Timestamp
    anchor_reason: str
    starting_value: float
    ending_value: float
    points: tuple[CumulativeDeltaPoint, ...]
    reset_events: tuple["CumulativeDeltaResetEvent", ...]
    valid_through: pd.Timestamp | None


@dataclass(frozen=True)
class BidAskImbalanceResult:
    metadata: OrderFlowAnalysisMetadata
    ask_volume: float
    bid_volume: float
    unknown_volume: float
    ask_bid_ratio: float | None
    dominant_side: AggressorSide | None
    threshold_satisfied: bool | None
    explanation: str


@dataclass(frozen=True)
class FootprintLevel:
    price: float
    bid_volume: float
    ask_volume: float
    unknown_volume: float
    delta: float
    trade_count: int


@dataclass(frozen=True)
class FootprintImbalance:
    price: float
    side: AggressorSide
    comparison_price: float
    numerator_volume: float
    denominator_volume: float
    ratio: float | None
    stacked_sequence_id: str | None


@dataclass(frozen=True)
class FootprintResult:
    metadata: OrderFlowAnalysisMetadata
    tick_size: float
    levels: tuple[FootprintLevel, ...]
    imbalances: tuple[FootprintImbalance, ...]


@dataclass(frozen=True)
class AbsorptionObservation:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    price_bottom: float
    price_top: float
    aggressive_side: AggressorSide
    aggressive_volume: float
    price_response_ticks: float
    detected: bool
    explanation: str


@dataclass(frozen=True)
class AbsorptionResult:
    metadata: OrderFlowAnalysisMetadata
    observations: tuple[AbsorptionObservation, ...]
    detected_sides: tuple[AggressorSide, ...]


@dataclass(frozen=True)
class ExhaustionObservation:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    extreme_price: float
    approach_side: AggressorSide
    volume_sequence: tuple[float, ...]
    trade_count_sequence: tuple[int, ...]
    detected: bool
    explanation: str


@dataclass(frozen=True)
class ExhaustionResult:
    metadata: OrderFlowAnalysisMetadata
    observations: tuple[ExhaustionObservation, ...]
    detected_sides: tuple[AggressorSide, ...]


class DeltaEngine(Protocol):
    def evaluate(
        self,
        window: OrderFlowWindow,
        location_window: ExecutionLocationWindow,
    ) -> "DeltaLocationAssessment": ...


class CumulativeDeltaEngine(Protocol):
    def evaluate(
        self,
        bucket_series: "DeltaBucketSeries",
        anchor: "CumulativeDeltaAnchor",
        *,
        evaluated_through: pd.Timestamp,
    ) -> CumulativeDeltaResult: ...


class BidAskImbalanceEngine(Protocol):
    def evaluate(
        self,
        window: OrderFlowWindow,
        location_window: ExecutionLocationWindow,
    ) -> BidAskImbalanceResult: ...


class FootprintEngine(Protocol):
    def evaluate(
        self,
        window: OrderFlowWindow,
        location_window: ExecutionLocationWindow,
    ) -> FootprintResult: ...


class AbsorptionEngine(Protocol):
    def evaluate(
        self,
        window: OrderFlowWindow,
        location_window: ExecutionLocationWindow,
    ) -> AbsorptionResult: ...


class ExhaustionEngine(Protocol):
    def evaluate(
        self,
        window: OrderFlowWindow,
        location_window: ExecutionLocationWindow,
    ) -> ExhaustionResult: ...
