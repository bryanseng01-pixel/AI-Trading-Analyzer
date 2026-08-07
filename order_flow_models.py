from dataclasses import dataclass
from enum import Enum
import math

import pandas as pd

from timeframe_roles import Direction


class OrderFlowSourceType(str, Enum):
    TRADE_LEVEL = "trade_level"
    TRADE_AND_QUOTE_LEVEL = "trade_and_quote_level"
    PROVIDER_PRICE_LEVEL_AGGREGATE = "provider_price_level_aggregate"
    NORMALIZED_REPLAY = "normalized_replay"
    OHLCV_ONLY = "ohlcv_only"


class OrderFlowGranularity(str, Enum):
    TRADE = "trade"
    QUOTE = "quote"
    MARKET_DEPTH = "market_depth"
    PROVIDER_PRICE_LEVEL_AGGREGATE = "provider_price_level_aggregate"


class OrderFlowDataQuality(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    GAPPED = "gapped"
    DELAYED = "delayed"
    UNAVAILABLE = "unavailable"


class EntitlementState(str, Enum):
    AUTHORIZED = "authorized"
    DELAYED = "delayed"
    DENIED = "denied"
    UNKNOWN = "unknown"


class AggressorSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class AnalyticalAvailability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RolloverPolicy(str, Enum):
    EXPLICIT_CONTRACT_ONLY = "explicit_contract_only"


@dataclass(frozen=True)
class ProviderIdentity:
    provider_id: str
    display_name: str
    adapter_version: str
    api_version: str | None
    source_type: OrderFlowSourceType

    def __post_init__(self) -> None:
        if not self.provider_id or not self.display_name or not self.adapter_version:
            raise ValueError("Provider identity fields cannot be empty.")


@dataclass(frozen=True)
class ProviderCapabilities:
    historical_trades: bool
    live_trades: bool
    historical_quotes: bool
    live_quotes: bool
    aggressor_side_reported: bool
    market_depth: bool
    sequence_numbers: bool
    corrections: bool
    vendor_aggregated_footprint: bool
    maximum_history: pd.Timedelta | None


@dataclass(frozen=True)
class ProviderSymbol:
    provider_id: str
    symbol: str


@dataclass(frozen=True)
class FuturesInstrument:
    root_symbol: str
    exchange: str
    product_name: str
    currency: str
    tick_size: float
    tick_value: float
    exchange_timezone: str
    display_timezone: str

    def __post_init__(self) -> None:
        if not self.root_symbol or not self.exchange:
            raise ValueError("Instrument root and exchange are required.")
        _positive_finite(self.tick_size, "tick_size")
        _positive_finite(self.tick_value, "tick_value")


@dataclass(frozen=True)
class FuturesContract:
    instrument: FuturesInstrument
    contract_code: str
    contract_month: int
    contract_year: int
    expiration_time: pd.Timestamp
    first_notice_time: pd.Timestamp | None
    provider_symbols: tuple[ProviderSymbol, ...]

    def __post_init__(self) -> None:
        if not self.contract_code:
            raise ValueError("An explicit futures contract code is required.")
        if not 1 <= self.contract_month <= 12:
            raise ValueError("contract_month must be between 1 and 12.")
        _require_aware(self.expiration_time, "expiration_time")
        if self.first_notice_time is not None:
            _require_aware(self.first_notice_time, "first_notice_time")


@dataclass(frozen=True)
class TradeEvent:
    event_id: str
    contract_code: str
    exchange_timestamp: pd.Timestamp
    received_timestamp: pd.Timestamp | None
    sequence_number: int | None
    price: float
    quantity: float
    aggressor_side: AggressorSide
    aggressor_source: str
    is_correction: bool

    def __post_init__(self) -> None:
        if not self.event_id or not self.contract_code or not self.aggressor_source:
            raise ValueError("Trade identity, contract, and side source are required.")
        _require_aware(self.exchange_timestamp, "exchange_timestamp")
        if self.received_timestamp is not None:
            _require_aware(self.received_timestamp, "received_timestamp")
        _positive_finite(self.price, "price")
        _positive_finite(self.quantity, "quantity")


@dataclass(frozen=True)
class QuoteEvent:
    event_id: str
    contract_code: str
    exchange_timestamp: pd.Timestamp
    received_timestamp: pd.Timestamp | None
    sequence_number: int | None
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    depth_level: int

    def __post_init__(self) -> None:
        _require_aware(self.exchange_timestamp, "exchange_timestamp")
        if self.received_timestamp is not None:
            _require_aware(self.received_timestamp, "received_timestamp")
        _positive_finite(self.bid_price, "bid_price")
        _positive_finite(self.ask_price, "ask_price")
        _nonnegative_finite(self.bid_size, "bid_size")
        _nonnegative_finite(self.ask_size, "ask_size")
        if self.ask_price < self.bid_price:
            raise ValueError("Ask price cannot be below bid price.")
        if self.depth_level < 0:
            raise ValueError("depth_level cannot be negative.")


@dataclass(frozen=True)
class ProviderPriceLevelAggregate:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    price: float
    bid_traded_volume: float
    ask_traded_volume: float
    unknown_traded_volume: float
    trade_count: int

    def __post_init__(self) -> None:
        _require_time_range(self.start_time, self.end_time)
        _positive_finite(self.price, "price")
        for name in (
            "bid_traded_volume",
            "ask_traded_volume",
            "unknown_traded_volume",
        ):
            _nonnegative_finite(getattr(self, name), name)
        if self.trade_count < 0:
            raise ValueError("trade_count cannot be negative.")


@dataclass(frozen=True)
class DataGap:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    first_missing_sequence: int | None
    last_missing_sequence: int | None
    reason: str

    def __post_init__(self) -> None:
        _require_time_range(self.start_time, self.end_time)
        if not self.reason:
            raise ValueError("A data-gap reason is required.")


@dataclass(frozen=True)
class OrderFlowProvenance:
    provider: ProviderIdentity
    instrument: FuturesInstrument
    contract: FuturesContract
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    granularities: tuple[OrderFlowGranularity, ...]
    tick_or_trade_level: bool
    provider_aggregated: bool
    data_quality: OrderFlowDataQuality
    entitlement_state: EntitlementState
    exchange_timestamped: bool
    received_timestamped: bool
    first_sequence_number: int | None
    last_sequence_number: int | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_time_range(self.start_time, self.end_time)
        if self.instrument != self.contract.instrument:
            raise ValueError("Provenance instrument must match its contract.")
        if not self.granularities and self.data_quality != OrderFlowDataQuality.UNAVAILABLE:
            raise ValueError("Available provenance requires declared granularity.")
        if self.provider.source_type == OrderFlowSourceType.OHLCV_ONLY:
            raise UnsupportedOrderFlowSourceError(
                "OHLCV-only sources cannot produce order-flow provenance."
            )


@dataclass(frozen=True)
class OrderFlowBatch:
    provenance: OrderFlowProvenance
    trades: tuple[TradeEvent, ...]
    quotes: tuple[QuoteEvent, ...]
    provider_price_levels: tuple[ProviderPriceLevelAggregate, ...]
    gaps: tuple[DataGap, ...]

    def __post_init__(self) -> None:
        for event in (*self.trades, *self.quotes):
            if event.contract_code != self.provenance.contract.contract_code:
                raise ValueError("Order-flow event contract does not match provenance.")


@dataclass(frozen=True)
class OrderFlowWindow:
    provenance: OrderFlowProvenance
    trades: tuple[TradeEvent, ...]
    quotes: tuple[QuoteEvent, ...]
    provider_price_levels: tuple[ProviderPriceLevelAggregate, ...]
    gaps: tuple[DataGap, ...]


@dataclass(frozen=True)
class AuthorityExecutionLocation:
    playbook: str
    authority_status: str
    authority_phase: str
    direction: Direction
    timeframe: str
    zone_kind: str
    bottom: float
    top: float
    formation_time: pd.Timestamp
    source: str
    location_id: str | None = None
    source_contract: str | None = None

    def __post_init__(self) -> None:
        if self.top < self.bottom:
            raise ValueError("Execution-location top cannot be below bottom.")
        _require_aware(self.formation_time, "formation_time")


@dataclass(frozen=True)
class ExecutionLocationWindow:
    location: AuthorityExecutionLocation
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    interaction_start_time: pd.Timestamp | None
    interaction_end_time: pd.Timestamp | None
    authority_observed_at: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        _require_time_range(self.start_time, self.end_time)
        if self.interaction_start_time is not None:
            _require_aware(self.interaction_start_time, "interaction_start_time")
        if self.interaction_end_time is not None:
            _require_aware(self.interaction_end_time, "interaction_end_time")
        if self.authority_observed_at is not None:
            _require_aware(self.authority_observed_at, "authority_observed_at")


@dataclass(frozen=True)
class OrderFlowAnalysisMetadata:
    engine_name: str
    engine_version: str
    provenance: OrderFlowProvenance
    location: AuthorityExecutionLocation
    evaluated_start_time: pd.Timestamp
    evaluated_end_time: pd.Timestamp
    availability: AnalyticalAvailability
    limitations: tuple[str, ...]
    confidence_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.engine_name or not self.engine_version:
            raise ValueError("Engine name and version are required.")
        _require_time_range(self.evaluated_start_time, self.evaluated_end_time)


class UnsupportedOrderFlowSourceError(ValueError):
    """Raised when OHLCV-only data is presented as true order flow."""


def _require_aware(timestamp: pd.Timestamp, name: str) -> None:
    if pd.Timestamp(timestamp).tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware.")


def _require_time_range(start: pd.Timestamp, end: pd.Timestamp) -> None:
    _require_aware(start, "start_time")
    _require_aware(end, "end_time")
    if pd.Timestamp(end) < pd.Timestamp(start):
        raise ValueError("end_time cannot precede start_time.")


def _positive_finite(value: float, name: str) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")


def _nonnegative_finite(value: float, name: str) -> None:
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative.")
