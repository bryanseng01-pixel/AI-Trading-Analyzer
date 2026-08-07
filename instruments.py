from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

import pandas as pd

from order_flow_models import FuturesInstrument


@dataclass(frozen=True)
class ProviderInstrumentMapping:
    provider_id: str
    root_symbol: str

    def __post_init__(self) -> None:
        if not self.provider_id or not self.root_symbol:
            raise ValueError("Provider instrument mappings cannot be empty.")


@dataclass(frozen=True)
class InstrumentStrategyDefaults:
    ema_period: int = 50
    swing_lookback: int = 3
    equal_level_tolerance_points: float = 5.0
    minimum_fvg_size_points: float = 5.0
    maximum_active_fvgs: int = 3


DEFAULT_DAY_TRADING_DEFAULTS = InstrumentStrategyDefaults()


@dataclass(frozen=True)
class InstrumentConfig:
    key: str
    display_name: str
    yahoo_symbol: str
    futures_instrument: FuturesInstrument
    provider_mappings: tuple[ProviderInstrumentMapping, ...] = ()
    strategy_defaults: InstrumentStrategyDefaults = DEFAULT_DAY_TRADING_DEFAULTS

    def __post_init__(self) -> None:
        if not self.key or self.key != self.key.upper():
            raise ValueError("Instrument keys must be nonempty uppercase identifiers.")
        if not self.display_name or not self.yahoo_symbol:
            raise ValueError("Instrument display and Yahoo symbols are required.")
        if self.key != self.futures_instrument.root_symbol:
            raise ValueError("Instrument key must match the futures root symbol.")

    @property
    def root_symbol(self) -> str:
        return self.futures_instrument.root_symbol

    @property
    def tick_size(self) -> float:
        return self.futures_instrument.tick_size

    @property
    def exchange(self) -> str:
        return self.futures_instrument.exchange

    @property
    def exchange_timezone(self) -> str:
        return self.futures_instrument.exchange_timezone

    @property
    def display_timezone(self) -> str:
        return self.futures_instrument.display_timezone


@dataclass(frozen=True)
class InstrumentRegistry:
    instruments: tuple[InstrumentConfig, ...]

    def __post_init__(self) -> None:
        if not self.instruments:
            raise ValueError("The instrument registry cannot be empty.")
        _require_unique((item.key for item in self.instruments), "instrument key")
        _require_unique((item.root_symbol for item in self.instruments), "root symbol")
        _require_unique((item.yahoo_symbol for item in self.instruments), "Yahoo symbol")
        _require_unique(
            (
                (mapping.provider_id, mapping.root_symbol)
                for item in self.instruments
                for mapping in item.provider_mappings
            ),
            "provider/root mapping",
        )

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.instruments)

    def resolve(self, key: str) -> InstrumentConfig:
        normalized = str(key).upper()
        for instrument in self.instruments:
            if instrument.key == normalized:
                return instrument
        raise KeyError(f"Unknown instrument: {key}")

    def resolve_yahoo_symbol(self, key: str) -> str:
        return self.resolve(key).yahoo_symbol


NQ = InstrumentConfig(
    key="NQ",
    display_name="NQ — E-mini Nasdaq-100",
    yahoo_symbol="NQ=F",
    futures_instrument=FuturesInstrument(
        root_symbol="NQ",
        exchange="CME",
        product_name="E-mini Nasdaq-100",
        currency="USD",
        tick_size=0.25,
        tick_value=5.0,
        exchange_timezone="America/Chicago",
        display_timezone="America/New_York",
    ),
)

ES = InstrumentConfig(
    key="ES",
    display_name="ES — E-mini S&P 500",
    yahoo_symbol="ES=F",
    futures_instrument=FuturesInstrument(
        root_symbol="ES",
        exchange="CME",
        product_name="E-mini S&P 500",
        currency="USD",
        tick_size=0.25,
        tick_value=12.5,
        exchange_timezone="America/Chicago",
        display_timezone="America/New_York",
    ),
)

def build_location_id(
    instrument: InstrumentConfig,
    *,
    source_identity: str,
    timeframe: str,
    zone_kind: str,
    formation_time: pd.Timestamp,
    bottom: float,
    top: float,
) -> str:
    """Build a stable instrument-qualified analytical location identity."""

    if not source_identity:
        raise ValueError("Location source identity is required.")
    timestamp = pd.Timestamp(formation_time)
    if timestamp.tzinfo is None:
        raise ValueError("Location formation time must be timezone-aware.")
    bottom_tick = _tick_index(bottom, instrument.tick_size)
    top_tick = _tick_index(top, instrument.tick_size)
    return ":".join((
        instrument.root_symbol,
        source_identity,
        timeframe.upper(),
        zone_kind,
        timestamp.tz_convert("UTC").isoformat(),
        str(bottom_tick),
        str(top_tick),
    ))


def _tick_index(price: float, tick_size: float) -> int:
    raw = Decimal(str(price)) / Decimal(str(tick_size))
    nearest = raw.to_integral_value(rounding=ROUND_HALF_EVEN)
    if raw != nearest:
        raise ValueError("Location bounds must align to the instrument tick size.")
    return int(nearest)


def _require_unique(values, name: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"Duplicate {name} in instrument registry.")


INSTRUMENT_REGISTRY = InstrumentRegistry((NQ, ES))
