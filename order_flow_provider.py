from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from order_flow_models import (
    FuturesContract,
    OrderFlowBatch,
    OrderFlowGranularity,
    OrderFlowSourceType,
    OrderFlowWindow,
    ProviderCapabilities,
    ProviderIdentity,
    RolloverPolicy,
    UnsupportedOrderFlowSourceError,
)


@dataclass(frozen=True)
class HistoricalOrderFlowRequest:
    contract: FuturesContract
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    required_granularities: tuple[OrderFlowGranularity, ...]

    def __post_init__(self) -> None:
        _validate_range(self.start_time, self.end_time)
        if not self.required_granularities:
            raise ValueError("Historical requests require at least one granularity.")


@dataclass(frozen=True)
class LiveOrderFlowSubscription:
    contract: FuturesContract
    required_granularities: tuple[OrderFlowGranularity, ...]
    resume_after_sequence: int | None

    def __post_init__(self) -> None:
        if not self.required_granularities:
            raise ValueError("Live subscriptions require at least one granularity.")


@runtime_checkable
class OrderFlowProvider(Protocol):
    """Vendor adapter contract for historical and live normalized data."""

    @property
    def identity(self) -> ProviderIdentity: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def fetch(
        self,
        request: HistoricalOrderFlowRequest,
    ) -> OrderFlowBatch: ...

    def stream(
        self,
        subscription: LiveOrderFlowSubscription,
    ) -> AsyncIterator[OrderFlowBatch]: ...


class ContractResolver(Protocol):
    def resolve(
        self,
        root_symbol: str,
        timestamp: pd.Timestamp,
        policy: RolloverPolicy,
    ) -> FuturesContract: ...


class OrderFlowWindowAssembler(Protocol):
    """Mode-neutral boundary; deduplication/correction rules remain deferred."""

    def apply(self, batch: OrderFlowBatch) -> None: ...

    def snapshot(
        self,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> OrderFlowWindow: ...


def validate_order_flow_provider(provider: OrderFlowProvider) -> None:
    """Reject OHLCV inference and providers without real flow capability."""

    identity = provider.identity
    capabilities = provider.capabilities
    if identity.source_type == OrderFlowSourceType.OHLCV_ONLY:
        raise UnsupportedOrderFlowSourceError(
            "Yahoo or other OHLCV-only data cannot be used as order flow."
        )
    supplies_trades = capabilities.historical_trades or capabilities.live_trades
    supplies_aggregates = capabilities.vendor_aggregated_footprint
    if not supplies_trades and not supplies_aggregates:
        raise UnsupportedOrderFlowSourceError(
            "Order flow requires trade-level data or authoritative provider aggregates."
        )


def _validate_range(start: pd.Timestamp, end: pd.Timestamp) -> None:
    start_value = pd.Timestamp(start)
    end_value = pd.Timestamp(end)
    if start_value.tzinfo is None or end_value.tzinfo is None:
        raise ValueError("Order-flow request timestamps must be timezone-aware.")
    if end_value < start_value:
        raise ValueError("Request end_time cannot precede start_time.")
