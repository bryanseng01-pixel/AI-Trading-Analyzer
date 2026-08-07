from dataclasses import dataclass
from enum import Enum
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
    from timeframe_roles import Direction


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
class FootprintLevel:
    tick_index: int
    price: float
    bid_volume: float
    ask_volume: float
    unknown_volume: float
    delta: float
    trade_count: int
    classification_coverage: float
    inside_authority_zone: bool
    comparison_only: bool


@dataclass(frozen=True)
class FootprintImbalance:
    subject_tick_index: int
    subject_price: float
    comparison_tick_index: int
    comparison_price: float
    side: AggressorSide
    numerator_volume: float
    denominator_volume: float
    ratio: float | None
    zero_denominator: bool
    stacked_sequence_id: str | None


@dataclass(frozen=True)
class FootprintResult:
    metadata: OrderFlowAnalysisMetadata
    location_id: str
    tick_size: float
    observation_start: pd.Timestamp | None
    evaluated_through: pd.Timestamp
    core_bottom: float
    core_top: float
    footprint_bottom: float
    footprint_top: float
    levels: tuple[FootprintLevel, ...]
    total_bid_volume: float
    total_ask_volume: float
    total_unknown_volume: float
    classification_coverage: float


class ImbalanceContext(str, Enum):
    SUPPORTIVE_AGGRESSION = "supportive_aggression"
    OPPOSING_AGGRESSION = "opposing_aggression"
    MIXED = "mixed"
    NO_STACKED_IMBALANCE = "no_stacked_imbalance"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class BidAskImbalanceResult:
    metadata: OrderFlowAnalysisMetadata
    location_id: str
    authority_direction: "Direction"
    imbalances: tuple[FootprintImbalance, ...]
    ask_stacks: tuple[tuple[FootprintImbalance, ...], ...]
    bid_stacks: tuple[tuple[FootprintImbalance, ...], ...]
    context: ImbalanceContext
    supportive: bool | None
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.context == ImbalanceContext.UNAVAILABLE:
            if self.supportive is not None:
                raise ValueError("Unavailable imbalance cannot claim support.")
        elif self.supportive is None:
            raise ValueError("Completed imbalance assessment requires a result.")


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
        footprint: FootprintResult,
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
