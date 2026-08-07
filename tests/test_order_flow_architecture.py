import asyncio
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from order_flow_models import (
    AggressorSide,
    AnalyticalAvailability,
    AuthorityExecutionLocation,
    EntitlementState,
    ExecutionLocationWindow,
    FuturesContract,
    FuturesInstrument,
    OrderFlowAnalysisMetadata,
    OrderFlowBatch,
    OrderFlowDataQuality,
    OrderFlowGranularity,
    OrderFlowProvenance,
    OrderFlowSourceType,
    ProviderCapabilities,
    ProviderIdentity,
    ProviderSymbol,
    TradeEvent,
    UnsupportedOrderFlowSourceError,
)
from order_flow_provider import (
    HistoricalOrderFlowRequest,
    LiveOrderFlowSubscription,
    OrderFlowProvider,
    validate_order_flow_provider,
)
from timeframe_roles import Direction


def _instrument():
    return FuturesInstrument(
        root_symbol="NQ",
        exchange="CME",
        product_name="E-mini Nasdaq-100",
        currency="USD",
        tick_size=0.25,
        tick_value=5.0,
        exchange_timezone="America/Chicago",
        display_timezone="America/New_York",
    )


def _contract():
    instrument = _instrument()
    return FuturesContract(
        instrument=instrument,
        contract_code="NQU6",
        contract_month=9,
        contract_year=2026,
        expiration_time=pd.Timestamp("2026-09-18 16:00", tz="UTC"),
        first_notice_time=None,
        provider_symbols=(ProviderSymbol("fake", "NQU6"),),
    )


def _identity(source_type=OrderFlowSourceType.TRADE_AND_QUOTE_LEVEL):
    return ProviderIdentity(
        provider_id="fake",
        display_name="Fake Licensed Feed",
        adapter_version="1.0",
        api_version="test",
        source_type=source_type,
    )


def _capabilities(*, trades=True):
    return ProviderCapabilities(
        historical_trades=trades,
        live_trades=trades,
        historical_quotes=True,
        live_quotes=True,
        aggressor_side_reported=True,
        market_depth=False,
        sequence_numbers=True,
        corrections=True,
        vendor_aggregated_footprint=False,
        maximum_history=pd.Timedelta(days=30),
    )


def _trade(sequence, side, price=20000.0, quantity=2.0):
    timestamp = pd.Timestamp("2026-08-05 14:30", tz="UTC") + pd.Timedelta(
        milliseconds=sequence
    )
    return TradeEvent(
        event_id=f"trade-{sequence}",
        contract_code="NQU6",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp + pd.Timedelta(milliseconds=2),
        sequence_number=sequence,
        price=price,
        quantity=quantity,
        aggressor_side=side,
        aggressor_source="provider_reported",
        is_correction=False,
    )


def _provenance(identity=None):
    contract = _contract()
    return OrderFlowProvenance(
        provider=identity or _identity(),
        instrument=contract.instrument,
        contract=contract,
        start_time=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        end_time=pd.Timestamp("2026-08-05 14:31", tz="UTC"),
        granularities=(OrderFlowGranularity.TRADE,),
        tick_or_trade_level=True,
        provider_aggregated=False,
        data_quality=OrderFlowDataQuality.COMPLETE,
        entitlement_state=EntitlementState.AUTHORIZED,
        exchange_timestamped=True,
        received_timestamped=True,
        first_sequence_number=1,
        last_sequence_number=3,
        limitations=(),
    )


def _batch(trades=None):
    return OrderFlowBatch(
        provenance=_provenance(),
        trades=trades
        or (
            _trade(1, AggressorSide.BUY),
            _trade(2, AggressorSide.SELL),
            _trade(3, AggressorSide.UNKNOWN),
        ),
        quotes=(),
        provider_price_levels=(),
        gaps=(),
    )


class FakeProvider:
    identity = _identity()
    capabilities = _capabilities()

    def __init__(self, batch):
        self.batch = batch

    async def fetch(self, request):
        return self.batch

    async def _stream(self):
        yield self.batch

    def stream(self, subscription):
        return self._stream()


def test_fake_provider_supports_historical_and_live_normalized_batches():
    batch = _batch()
    provider = FakeProvider(batch)
    request = HistoricalOrderFlowRequest(
        contract=_contract(),
        start_time=batch.provenance.start_time,
        end_time=batch.provenance.end_time,
        required_granularities=(OrderFlowGranularity.TRADE,),
    )
    subscription = LiveOrderFlowSubscription(
        contract=_contract(),
        required_granularities=(OrderFlowGranularity.TRADE,),
        resume_after_sequence=None,
    )

    async def collect():
        historical = await provider.fetch(request)
        live = [item async for item in provider.stream(subscription)]
        return historical, live

    historical, live = asyncio.run(collect())

    assert isinstance(provider, OrderFlowProvider)
    assert historical == batch
    assert live == [batch]


def test_synthetic_trade_stream_preserves_real_side_and_unknown_volume():
    batch = _batch()

    assert [trade.aggressor_side for trade in batch.trades] == [
        AggressorSide.BUY,
        AggressorSide.SELL,
        AggressorSide.UNKNOWN,
    ]
    assert all(
        trade.aggressor_source == "provider_reported" for trade in batch.trades
    )


def test_yahoo_and_other_ohlcv_only_sources_are_explicitly_rejected():
    class YahooLikeProvider:
        identity = _identity(OrderFlowSourceType.OHLCV_ONLY)
        capabilities = _capabilities(trades=False)

    with pytest.raises(UnsupportedOrderFlowSourceError, match="OHLCV-only"):
        validate_order_flow_provider(YahooLikeProvider())

    with pytest.raises(UnsupportedOrderFlowSourceError, match="OHLCV-only"):
        _provenance(YahooLikeProvider.identity)


def test_provider_without_trade_or_authoritative_aggregate_is_rejected():
    class QuoteOnlyProvider:
        identity = _identity(OrderFlowSourceType.TRADE_AND_QUOTE_LEVEL)
        capabilities = _capabilities(trades=False)

    with pytest.raises(UnsupportedOrderFlowSourceError, match="trade-level"):
        validate_order_flow_provider(QuoteOnlyProvider())


def test_events_must_match_explicit_contract_provenance():
    wrong = TradeEvent(
        event_id="wrong",
        contract_code="ESU6",
        exchange_timestamp=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        received_timestamp=None,
        sequence_number=1,
        price=6000,
        quantity=1,
        aggressor_side=AggressorSide.BUY,
        aggressor_source="provider_reported",
        is_correction=False,
    )

    with pytest.raises(ValueError, match="contract"):
        _batch((wrong,))


def test_metadata_records_descriptive_confidence_reasons_without_score():
    location = AuthorityExecutionLocation(
        playbook="ICT Liquidity Sweep Reversal",
        authority_status="READY",
        authority_phase="execution_zone_available",
        direction=Direction.BULLISH,
        timeframe="1M",
        zone_kind="original_fvg",
        bottom=19999.0,
        top=20001.0,
        formation_time=pd.Timestamp("2026-08-05 14:29", tz="UTC"),
        source="authority_filtered_fvg",
    )
    metadata = OrderFlowAnalysisMetadata(
        engine_name="FutureDeltaEngine",
        engine_version="0",
        provenance=_provenance(),
        location=location,
        evaluated_start_time=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        evaluated_end_time=pd.Timestamp("2026-08-05 14:31", tz="UTC"),
        availability=AnalyticalAvailability.DEGRADED,
        limitations=("One sequence gap is present.",),
        confidence_reasons=(
            "Exchange timestamps are available.",
            "The sequence gap makes the assessment degraded.",
        ),
    )

    assert metadata.confidence_reasons[0].startswith("Exchange timestamps")
    assert not hasattr(metadata, "confidence_score")
    with pytest.raises(FrozenInstanceError):
        metadata.confidence_reasons = ()


def test_location_window_references_existing_authority_zone_only():
    location = AuthorityExecutionLocation(
        playbook="ICT Liquidity Sweep Reversal",
        authority_status="READY",
        authority_phase="execution_zone_available",
        direction=Direction.BEARISH,
        timeframe="1M",
        zone_kind="original_fvg",
        bottom=20000,
        top=20005,
        formation_time=pd.Timestamp("2026-08-05 14:29", tz="UTC"),
        source="authority_filtered_fvg",
    )
    window = ExecutionLocationWindow(
        location=location,
        start_time=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        end_time=pd.Timestamp("2026-08-05 14:31", tz="UTC"),
        interaction_start_time=None,
        interaction_end_time=None,
    )

    assert window.location.bottom == 20000
    assert window.location.top == 20005
    assert not hasattr(window, "entry")
    assert not hasattr(window, "stop")
    assert not hasattr(window, "target")
