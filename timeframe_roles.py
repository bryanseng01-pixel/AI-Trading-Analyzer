from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import pandas as pd

from analysis_pipeline import TimeframeAnalysis


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class SetupState(str, Enum):
    ALIGNED_CONTINUATION = "aligned_continuation"
    COUNTERTREND_PULLBACK = "countertrend_pullback"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True)
class TimeframeRoleState:
    """Directional state for the approved multi-timeframe strategy roles."""

    context_direction: Direction | None
    setup_state: SetupState
    setup_direction: Direction | None
    confirmation_direction: Direction | None
    trigger_direction: Direction | None

    @property
    def confirmation_aligned(self) -> bool:
        return self.confirmation_direction == self.context_direction

    @property
    def trigger_aligned(self) -> bool:
        return self.trigger_direction == self.context_direction


def trend_direction(trend: str) -> Direction | None:
    if "BULLISH" in trend:
        return Direction.BULLISH
    if "BEARISH" in trend:
        return Direction.BEARISH
    return None


def structure_direction(structure: str) -> Direction | None:
    if structure == "Bullish Structure":
        return Direction.BULLISH
    if structure == "Bearish Structure":
        return Direction.BEARISH
    return None


def latest_break_direction(
    analysis: TimeframeAnalysis,
) -> Direction | None:
    """Return the direction of the latest actual BOS/CHoCH event."""

    events: list[tuple[pd.Timestamp, int, dict[str, Any]]] = []
    if analysis.bos is not None:
        events.append((pd.Timestamp(analysis.bos["time"]), 0, analysis.bos))
    if analysis.choch is not None:
        # A CHoCH wins the deterministic tie-break if timestamps are equal.
        events.append((pd.Timestamp(analysis.choch["time"]), 1, analysis.choch))

    if not events:
        return None

    event = max(events, key=lambda item: (item[0], item[1]))[2]
    try:
        return Direction(event["direction"])
    except ValueError:
        return None


def evaluate_timeframe_roles(
    analyses: Mapping[str, TimeframeAnalysis],
) -> TimeframeRoleState:
    """Map independent timeframe analyses into approved strategy roles."""

    four_hour_direction = trend_direction(analyses["4 Hour"].trend)
    one_hour_direction = trend_direction(analyses["1 Hour"].trend)
    context_direction = (
        four_hour_direction
        if four_hour_direction is not None
        and four_hour_direction == one_hour_direction
        else None
    )

    setup_analysis = analyses["15 Minute"]
    setup_direction = (
        latest_break_direction(setup_analysis)
        or structure_direction(setup_analysis.structure)
    )

    if context_direction is None or setup_direction is None:
        setup_state = SetupState.UNCONFIRMED
    elif setup_direction == context_direction:
        setup_state = SetupState.ALIGNED_CONTINUATION
    else:
        setup_state = SetupState.COUNTERTREND_PULLBACK

    return TimeframeRoleState(
        context_direction=context_direction,
        setup_state=setup_state,
        setup_direction=setup_direction,
        confirmation_direction=latest_break_direction(
            analyses["5 Minute"]
        ),
        trigger_direction=latest_break_direction(analyses["1 Minute"]),
    )
