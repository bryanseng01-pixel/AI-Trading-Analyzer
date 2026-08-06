import pandas as pd
import pytest


@pytest.fixture
def ohlc_factory():
    """Build deterministic OHLC frames for technical-analysis tests."""

    def build(
        rows,
        *,
        start="2026-01-05 09:30",
        frequency="5min",
        timezone="America/New_York",
    ):
        index = pd.date_range(
            start=start,
            periods=len(rows),
            freq=frequency,
            tz=timezone,
        )
        return pd.DataFrame(
            rows,
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=index,
            dtype=float,
        )

    return build
