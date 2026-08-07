from dataclasses import dataclass
import math

import pandas as pd

from order_flow_engines import DeltaBucket
from order_flow_models import DataGap, OrderFlowProvenance, TradeEvent, AggressorSide


@dataclass(frozen=True)
class DeltaBucketSeries:
    """Canonical completed Delta buckets with source-quality attestations."""

    provenance: OrderFlowProvenance
    series_id: str
    contract_code: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    bucket_interval: pd.Timedelta
    bucket_anchor_time: pd.Timestamp
    buckets: tuple[DeltaBucket, ...]
    total_ask_volume: float
    total_bid_volume: float
    total_unknown_volume: float
    classification_coverage: float
    minimum_classification_coverage: float
    normalization_complete: bool
    duplicates_resolved: bool
    corrections_resolved: bool
    gaps: tuple[DataGap, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.series_id or not self.contract_code:
            raise ValueError("Delta bucket series identity and contract are required.")
        if self.bucket_interval <= pd.Timedelta(0):
            raise ValueError("Delta bucket interval must be positive.")
        if self.end_time < self.start_time:
            raise ValueError("Delta bucket series end cannot precede start.")
        if not 0.0 <= self.classification_coverage <= 1.0:
            raise ValueError("classification_coverage must be in [0, 1].")
        if not 0.0 <= self.minimum_classification_coverage <= 1.0:
            raise ValueError("minimum_classification_coverage must be in [0, 1].")


def aggregate_delta_buckets(
    trades: tuple[TradeEvent, ...],
    *,
    bucket_anchor_time: pd.Timestamp,
    evaluated_through: pd.Timestamp,
    bucket_interval: pd.Timedelta,
) -> tuple[DeltaBucket, ...]:
    """Apply the single shared BUY/SELL/UNKNOWN bucket arithmetic."""

    anchor = pd.Timestamp(bucket_anchor_time)
    evaluated = pd.Timestamp(evaluated_through)
    if anchor.tzinfo is None or evaluated.tzinfo is None:
        raise ValueError("Delta aggregation timestamps must be timezone-aware.")
    if evaluated < anchor:
        raise ValueError("evaluated_through cannot precede the bucket anchor.")
    if bucket_interval <= pd.Timedelta(0):
        raise ValueError("bucket_interval must be positive.")

    grouped: dict[int, list[TradeEvent]] = {}
    interval_ns = bucket_interval.value
    for trade in trades:
        timestamp = pd.Timestamp(trade.exchange_timestamp)
        if timestamp < anchor or timestamp > evaluated:
            continue
        index = int((timestamp - anchor).value // interval_ns)
        grouped.setdefault(index, []).append(trade)

    buckets = []
    for index in sorted(grouped):
        bucket_trades = grouped[index]
        ask = math.fsum(
            trade.quantity
            for trade in bucket_trades
            if trade.aggressor_side == AggressorSide.BUY
        )
        bid = math.fsum(
            trade.quantity
            for trade in bucket_trades
            if trade.aggressor_side == AggressorSide.SELL
        )
        unknown = math.fsum(
            trade.quantity
            for trade in bucket_trades
            if trade.aggressor_side == AggressorSide.UNKNOWN
        )
        bucket_start = anchor + index * bucket_interval
        buckets.append(
            DeltaBucket(
                start_time=bucket_start,
                end_time=min(bucket_start + bucket_interval, evaluated),
                ask_volume=ask,
                bid_volume=bid,
                unknown_volume=unknown,
                delta=ask - bid,
                total_classified_volume=ask + bid,
            )
        )
    return tuple(buckets)


def build_delta_bucket_series(
    trades: tuple[TradeEvent, ...],
    *,
    provenance: OrderFlowProvenance,
    series_id: str,
    start_time: pd.Timestamp,
    evaluated_through: pd.Timestamp,
    bucket_interval: pd.Timedelta,
    minimum_classification_coverage: float,
    normalization_complete: bool,
    duplicates_resolved: bool,
    corrections_resolved: bool,
    gaps: tuple[DataGap, ...] = (),
    limitations: tuple[str, ...] = (),
) -> DeltaBucketSeries:
    """Package already-normalized trades into one canonical bucket series."""

    buckets = aggregate_delta_buckets(
        trades,
        bucket_anchor_time=start_time,
        evaluated_through=evaluated_through,
        bucket_interval=bucket_interval,
    )
    ask = math.fsum(bucket.ask_volume for bucket in buckets)
    bid = math.fsum(bucket.bid_volume for bucket in buckets)
    unknown = math.fsum(bucket.unknown_volume for bucket in buckets)
    classified = ask + bid
    total = classified + unknown
    return DeltaBucketSeries(
        provenance=provenance,
        series_id=series_id,
        contract_code=provenance.contract.contract_code,
        start_time=pd.Timestamp(start_time),
        end_time=pd.Timestamp(evaluated_through),
        bucket_interval=bucket_interval,
        bucket_anchor_time=pd.Timestamp(start_time),
        buckets=buckets,
        total_ask_volume=ask,
        total_bid_volume=bid,
        total_unknown_volume=unknown,
        classification_coverage=classified / total if total else 0.0,
        minimum_classification_coverage=minimum_classification_coverage,
        normalization_complete=normalization_complete,
        duplicates_resolved=duplicates_resolved,
        corrections_resolved=corrections_resolved,
        gaps=gaps,
        limitations=limitations,
    )
