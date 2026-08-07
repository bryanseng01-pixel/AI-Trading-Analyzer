from dataclasses import dataclass
from enum import Enum
import math

import pandas as pd

from timeframe_roles import Direction


NEW_YORK_TIMEZONE = "America/New_York"
NEW_YORK_SESSION_START = "08:30"
NEW_YORK_SESSION_END = "17:00"


class ProfileValidity(str, Enum):
    VALID = "valid"
    NO_COMPLETED_SESSION = "no_completed_session"
    INSUFFICIENT_BARS = "insufficient_bars"
    MISSING_VOLUME = "missing_volume"
    ZERO_VOLUME = "zero_volume"
    INVALID_PRICE_DATA = "invalid_price_data"


class VolumeProfileSource(str, Enum):
    YAHOO_BAR_OHLCV_APPROXIMATION = "yahoo_bar_ohlcv_approximation"


class DataQuality(str, Enum):
    APPROXIMATED = "approximated"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class VolumeNodeKind(str, Enum):
    HVN = "hvn"
    LVN = "lvn"


class ProfileRelationship(str, Enum):
    INSIDE_VALUE = "inside_value"
    ABOVE_VAH = "above_vah"
    BELOW_VAL = "below_val"
    OVERLAPS_VAH = "overlaps_vah"
    OVERLAPS_VAL = "overlaps_val"
    OVERLAPS_POC = "overlaps_poc"
    OVERLAPS_HVN = "overlaps_hvn"
    OVERLAPS_LVN = "overlaps_lvn"
    OUTSIDE_PROFILE = "outside_profile"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class VolumeProfileRules:
    """Centralized deterministic parameters for the initial profile."""

    value_area_percentage: float = 0.70
    ticks_per_bin: int = 4

    def __post_init__(self) -> None:
        if not 0.0 < self.value_area_percentage <= 1.0:
            raise ValueError("value_area_percentage must be in (0.0, 1.0].")
        if self.ticks_per_bin <= 0:
            raise ValueError("ticks_per_bin must be positive.")


DEFAULT_VOLUME_PROFILE_RULES = VolumeProfileRules()


@dataclass(frozen=True)
class ProfileRange:
    timeframe: str
    session_name: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    price_low: float
    price_high: float
    tick_size: float
    ticks_per_bin: int
    bin_size: float
    source: VolumeProfileSource


@dataclass(frozen=True)
class VolumeProfileBin:
    index: int
    bottom: float
    top: float
    midpoint: float
    estimated_volume: float
    volume_percentage: float
    in_value_area: bool
    node_kind: VolumeNodeKind | None


@dataclass(frozen=True)
class ValueArea:
    target_percentage: float
    achieved_percentage: float
    poc_price: float
    poc_bin_index: int
    vah: float
    val: float
    included_bin_indices: tuple[int, ...]


@dataclass(frozen=True)
class VolumeNode:
    kind: VolumeNodeKind
    bottom: float
    top: float
    peak_price: float
    bin_indices: tuple[int, ...]
    estimated_volume: float


@dataclass(frozen=True)
class VolumeProfileResult:
    validity: ProfileValidity
    profile_range: ProfileRange | None
    bins: tuple[VolumeProfileBin, ...]
    value_area: ValueArea | None
    nodes: tuple[VolumeNode, ...]
    total_reported_bar_volume: float
    total_distributed_volume: float
    eligible_bar_count: int
    expected_bar_count: int
    missing_bar_count: int
    source: VolumeProfileSource
    data_quality: DataQuality
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.validity == ProfileValidity.VALID:
            if self.profile_range is None or self.value_area is None or not self.bins:
                raise ValueError("A valid volume profile requires range, bins, and value area.")
        elif self.profile_range is not None or self.value_area is not None or self.bins:
            raise ValueError("An unavailable profile cannot expose calculated profile data.")


@dataclass(frozen=True)
class ExecutionZoneProfileAssessment:
    applicable: bool
    evaluated: bool
    authority_zone_bottom: float | None
    authority_zone_top: float | None
    direction: Direction | None
    relationships: tuple[ProfileRelationship, ...]
    directionally_supportive: bool | None
    overlapping_node_kinds: tuple[VolumeNodeKind, ...]
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.evaluated:
            if not self.applicable or self.directionally_supportive is None:
                raise ValueError("An evaluated profile assessment requires a result.")
        elif self.directionally_supportive is not None:
            raise ValueError("An unevaluated assessment cannot claim support.")


_SOURCE_LIMITATIONS = (
    "Volume is distributed uniformly across each bar's high-low price bins.",
    "Yahoo OHLCV cannot provide true tick-level volume at price.",
    "No bid/ask, delta, footprint, imbalance, absorption, or aggressor-side claims are made.",
    "Scheduled New York session boundaries do not account for exchange holidays or early closes.",
)


def build_previous_new_york_profile(
    data: pd.DataFrame,
    *,
    evaluated_through: pd.Timestamp,
    tick_size: float,
    rules: VolumeProfileRules = DEFAULT_VOLUME_PROFILE_RULES,
) -> VolumeProfileResult:
    """Build one completed New York session bar-volume approximation."""

    tick = float(tick_size)
    if not math.isfinite(tick) or tick <= 0.0:
        raise ValueError("tick_size must be finite and positive.")
    if not isinstance(rules, VolumeProfileRules):
        raise TypeError("rules must be a VolumeProfileRules instance.")
    if data is None or data.empty:
        return _unavailable(ProfileValidity.NO_COMPLETED_SESSION)

    required_prices = {"Open", "High", "Low", "Close"}
    if not required_prices.issubset(data.columns):
        return _unavailable(ProfileValidity.INVALID_PRICE_DATA)
    if "Volume" not in data.columns:
        return _unavailable(ProfileValidity.MISSING_VOLUME)

    localized = _to_new_york_time(data)
    evaluated = _to_new_york_timestamp(evaluated_through)
    selected = _select_latest_completed_session(localized, evaluated)
    if selected is None:
        return _unavailable(ProfileValidity.NO_COMPLETED_SESSION)
    session_start, session_end, bars = selected
    expected = int((session_end - session_start) / pd.Timedelta(minutes=1))

    if bars.empty:
        return _unavailable(ProfileValidity.INSUFFICIENT_BARS)
    numeric = bars[["Open", "High", "Low", "Close", "Volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    values = numeric.to_numpy(dtype=float)
    if not all(math.isfinite(value) for row in values for value in row):
        validity = (
            ProfileValidity.MISSING_VOLUME
            if numeric["Volume"].isna().any()
            else ProfileValidity.INVALID_PRICE_DATA
        )
        return _unavailable(validity)
    if (numeric["Volume"] < 0.0).any():
        return _unavailable(ProfileValidity.MISSING_VOLUME)
    invalid_prices = (
        (numeric["High"] < numeric["Low"])
        | (numeric["High"] < numeric[["Open", "Close"]].max(axis=1))
        | (numeric["Low"] > numeric[["Open", "Close"]].min(axis=1))
    )
    if invalid_prices.any():
        return _unavailable(ProfileValidity.INVALID_PRICE_DATA)

    total_volume = float(numeric["Volume"].sum())
    if total_volume == 0.0:
        return _unavailable(ProfileValidity.ZERO_VOLUME)

    bin_size = tick * rules.ticks_per_bin
    session_low = float(numeric["Low"].min())
    session_high = float(numeric["High"].max())
    origin = math.floor(session_low / bin_size) * bin_size
    maximum_index = int(math.floor((session_high - origin) / bin_size + 1e-12))
    volumes = [0.0] * (maximum_index + 1)
    for row in numeric.itertuples():
        low_index = int(math.floor((float(row.Low) - origin) / bin_size + 1e-12))
        high_index = int(math.floor((float(row.High) - origin) / bin_size + 1e-12))
        count = high_index - low_index + 1
        allocation = float(row.Volume) / count
        for index in range(low_index, high_index + 1):
            volumes[index] += allocation

    distributed = float(sum(volumes))
    value_area = _build_value_area(volumes, origin, bin_size, total_volume, rules)
    node_kinds, nodes, node_limitations = _classify_nodes(
        volumes, origin, bin_size, value_area.poc_bin_index
    )
    bins = tuple(
        VolumeProfileBin(
            index=index,
            bottom=origin + index * bin_size,
            top=origin + (index + 1) * bin_size,
            midpoint=origin + (index + 0.5) * bin_size,
            estimated_volume=volume,
            volume_percentage=volume / total_volume,
            in_value_area=index in value_area.included_bin_indices,
            node_kind=node_kinds.get(index),
        )
        for index, volume in enumerate(volumes)
    )
    missing = max(expected - len(bars), 0)
    limitations = list(_SOURCE_LIMITATIONS)
    if missing:
        limitations.append(
            f"The selected session is missing {missing} of {expected} expected 1-minute bars."
        )
    limitations.extend(node_limitations)
    profile_range = ProfileRange(
        timeframe="1m",
        session_name="Previous completed New York",
        start_time=session_start,
        end_time=session_end,
        price_low=origin,
        price_high=origin + len(volumes) * bin_size,
        tick_size=tick,
        ticks_per_bin=rules.ticks_per_bin,
        bin_size=bin_size,
        source=VolumeProfileSource.YAHOO_BAR_OHLCV_APPROXIMATION,
    )
    return VolumeProfileResult(
        validity=ProfileValidity.VALID,
        profile_range=profile_range,
        bins=bins,
        value_area=value_area,
        nodes=nodes,
        total_reported_bar_volume=total_volume,
        total_distributed_volume=distributed,
        eligible_bar_count=len(bars),
        expected_bar_count=expected,
        missing_bar_count=missing,
        source=VolumeProfileSource.YAHOO_BAR_OHLCV_APPROXIMATION,
        data_quality=DataQuality.DEGRADED if missing else DataQuality.APPROXIMATED,
        limitations=tuple(limitations),
    )


def assess_execution_zone_profile(
    profile: VolumeProfileResult,
    *,
    execution_zone_bottom: float | None,
    execution_zone_top: float | None,
    direction: Direction | None,
) -> ExecutionZoneProfileAssessment:
    """Evaluate only the supplied authority execution zone against a profile."""

    applicable = execution_zone_bottom is not None and execution_zone_top is not None
    if not applicable or direction is None:
        return _unevaluated_assessment(
            applicable=False,
            direction=direction,
            explanation="A directional authority execution FVG is required.",
            limitations=profile.limitations,
        )
    if profile.validity != ProfileValidity.VALID:
        return _unevaluated_assessment(
            applicable=True,
            direction=direction,
            explanation="The completed-session volume profile is unavailable.",
            limitations=profile.limitations,
            bottom=execution_zone_bottom,
            top=execution_zone_top,
        )
    bottom = float(execution_zone_bottom)
    top = float(execution_zone_top)
    if not math.isfinite(bottom) or not math.isfinite(top) or top < bottom:
        raise ValueError("Execution-zone bounds must be finite and ordered.")
    profile_range = profile.profile_range
    value_area = profile.value_area
    assert profile_range is not None and value_area is not None

    relationships: list[ProfileRelationship] = []
    if top < profile_range.price_low or bottom > profile_range.price_high:
        relationships.append(ProfileRelationship.OUTSIDE_PROFILE)
    else:
        if bottom >= value_area.val and top <= value_area.vah:
            relationships.append(ProfileRelationship.INSIDE_VALUE)
        if bottom > value_area.vah:
            relationships.append(ProfileRelationship.ABOVE_VAH)
        if top < value_area.val:
            relationships.append(ProfileRelationship.BELOW_VAL)
        if bottom <= value_area.vah <= top:
            relationships.append(ProfileRelationship.OVERLAPS_VAH)
        if bottom <= value_area.val <= top:
            relationships.append(ProfileRelationship.OVERLAPS_VAL)
        if bottom <= value_area.poc_price <= top:
            relationships.append(ProfileRelationship.OVERLAPS_POC)

    overlapping_kinds = []
    for kind, relationship in (
        (VolumeNodeKind.HVN, ProfileRelationship.OVERLAPS_HVN),
        (VolumeNodeKind.LVN, ProfileRelationship.OVERLAPS_LVN),
    ):
        if any(
            node.kind == kind and _positive_overlap(bottom, top, node.bottom, node.top)
            for node in profile.nodes
        ):
            relationships.append(relationship)
            overlapping_kinds.append(kind)

    supportive = (
        direction == Direction.BULLISH
        and (
            ProfileRelationship.BELOW_VAL in relationships
            or ProfileRelationship.OVERLAPS_VAL in relationships
            and bottom < value_area.val
        )
    ) or (
        direction == Direction.BEARISH
        and (
            ProfileRelationship.ABOVE_VAH in relationships
            or ProfileRelationship.OVERLAPS_VAH in relationships
            and top > value_area.vah
        )
    )
    limitations = list(profile.limitations)
    if bottom < profile_range.price_low or top > profile_range.price_high:
        limitations.append(
            "The authority execution FVG is only partially covered by the profile range."
        )
    relation_text = ", ".join(item.value.replace("_", " ") for item in relationships)
    return ExecutionZoneProfileAssessment(
        applicable=True,
        evaluated=True,
        authority_zone_bottom=bottom,
        authority_zone_top=top,
        direction=direction,
        relationships=tuple(relationships),
        directionally_supportive=supportive,
        overlapping_node_kinds=tuple(overlapping_kinds),
        explanation=(
            f"The authority execution FVG relationship is: {relation_text or 'within profile range'}. "
            "HVN/LVN observations are descriptive only."
        ),
        limitations=tuple(limitations),
    )


def _build_value_area(
    volumes: list[float],
    origin: float,
    bin_size: float,
    total_volume: float,
    rules: VolumeProfileRules,
) -> ValueArea:
    maximum = max(volumes)
    poc_index = next(index for index, volume in enumerate(volumes) if volume == maximum)
    included = {poc_index}
    cumulative = volumes[poc_index]
    lower = poc_index - 1
    upper = poc_index + 1
    target = total_volume * rules.value_area_percentage
    while cumulative < target and (lower >= 0 or upper < len(volumes)):
        lower_volume = volumes[lower] if lower >= 0 else -1.0
        upper_volume = volumes[upper] if upper < len(volumes) else -1.0
        if lower_volume >= upper_volume:
            included.add(lower)
            cumulative += lower_volume
            lower -= 1
        else:
            included.add(upper)
            cumulative += upper_volume
            upper += 1
    ordered = tuple(sorted(included))
    return ValueArea(
        target_percentage=rules.value_area_percentage,
        achieved_percentage=cumulative / total_volume,
        poc_price=origin + (poc_index + 0.5) * bin_size,
        poc_bin_index=poc_index,
        vah=origin + (ordered[-1] + 1) * bin_size,
        val=origin + ordered[0] * bin_size,
        included_bin_indices=ordered,
    )


def _classify_nodes(
    volumes: list[float],
    origin: float,
    bin_size: float,
    poc_index: int,
) -> tuple[dict[int, VolumeNodeKind], tuple[VolumeNode, ...], tuple[str, ...]]:
    positive = [volume for volume in volumes if volume > 0.0]
    lower = float(pd.Series(positive).quantile(0.25))
    upper = float(pd.Series(positive).quantile(0.75))
    kinds: dict[int, VolumeNodeKind] = {}
    limitations: tuple[str, ...] = ()
    if math.isclose(lower, upper):
        kinds[poc_index] = VolumeNodeKind.HVN
        limitations = (
            "The volume distribution is degenerate; only the POC is labeled HVN and no LVNs are emitted.",
        )
    else:
        for index, volume in enumerate(volumes):
            if volume <= 0.0:
                continue
            if volume >= upper:
                kinds[index] = VolumeNodeKind.HVN
            elif volume <= lower:
                kinds[index] = VolumeNodeKind.LVN

    nodes: list[VolumeNode] = []
    for kind in (VolumeNodeKind.HVN, VolumeNodeKind.LVN):
        indices = [index for index in range(len(volumes)) if kinds.get(index) == kind]
        for group in _contiguous_groups(indices):
            peak_volume = max(volumes[index] for index in group) if kind == VolumeNodeKind.HVN else min(volumes[index] for index in group)
            peak_index = next(index for index in group if volumes[index] == peak_volume)
            nodes.append(
                VolumeNode(
                    kind=kind,
                    bottom=origin + group[0] * bin_size,
                    top=origin + (group[-1] + 1) * bin_size,
                    peak_price=origin + (peak_index + 0.5) * bin_size,
                    bin_indices=tuple(group),
                    estimated_volume=sum(volumes[index] for index in group),
                )
            )
    return kinds, tuple(nodes), limitations


def _contiguous_groups(indices: list[int]) -> tuple[list[int], ...]:
    groups: list[list[int]] = []
    for index in indices:
        if not groups or index != groups[-1][-1] + 1:
            groups.append([index])
        else:
            groups[-1].append(index)
    return tuple(groups)


def _select_latest_completed_session(
    data: pd.DataFrame,
    evaluated: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.DataFrame] | None:
    candidates = []
    for session_date in sorted(set(data.index.date)):
        start = pd.Timestamp(f"{session_date} {NEW_YORK_SESSION_START}", tz=NEW_YORK_TIMEZONE)
        end = pd.Timestamp(f"{session_date} {NEW_YORK_SESSION_END}", tz=NEW_YORK_TIMEZONE)
        if end > evaluated:
            continue
        bars = data[(data.index >= start) & (data.index < end)]
        if not bars.empty:
            candidates.append((start, end, bars))
    return candidates[-1] if candidates else None


def _to_new_york_time(data: pd.DataFrame) -> pd.DataFrame:
    localized = data.copy()
    index = pd.DatetimeIndex(localized.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    localized.index = index.tz_convert(NEW_YORK_TIMEZONE)
    return localized.sort_index()


def _to_new_york_timestamp(timestamp: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return value.tz_convert(NEW_YORK_TIMEZONE)


def _positive_overlap(left_bottom: float, left_top: float, right_bottom: float, right_top: float) -> bool:
    return min(left_top, right_top) > max(left_bottom, right_bottom)


def _unavailable(validity: ProfileValidity) -> VolumeProfileResult:
    explanation = {
        ProfileValidity.NO_COMPLETED_SESSION: "No completed New York session is available.",
        ProfileValidity.INSUFFICIENT_BARS: "The completed New York session has no eligible bars.",
        ProfileValidity.MISSING_VOLUME: "Usable bar volume is unavailable or invalid.",
        ProfileValidity.ZERO_VOLUME: "The completed New York session reports zero total volume.",
        ProfileValidity.INVALID_PRICE_DATA: "Usable OHLC price data is unavailable or inconsistent.",
    }[validity]
    return VolumeProfileResult(
        validity=validity,
        profile_range=None,
        bins=(),
        value_area=None,
        nodes=(),
        total_reported_bar_volume=0.0,
        total_distributed_volume=0.0,
        eligible_bar_count=0,
        expected_bar_count=510,
        missing_bar_count=510,
        source=VolumeProfileSource.YAHOO_BAR_OHLCV_APPROXIMATION,
        data_quality=DataQuality.UNAVAILABLE,
        limitations=(explanation,) + _SOURCE_LIMITATIONS,
    )


def _unevaluated_assessment(
    *,
    applicable: bool,
    direction: Direction | None,
    explanation: str,
    limitations: tuple[str, ...],
    bottom: float | None = None,
    top: float | None = None,
) -> ExecutionZoneProfileAssessment:
    return ExecutionZoneProfileAssessment(
        applicable=applicable,
        evaluated=False,
        authority_zone_bottom=bottom,
        authority_zone_top=top,
        direction=direction,
        relationships=(ProfileRelationship.UNAVAILABLE,),
        directionally_supportive=None,
        overlapping_node_kinds=(),
        explanation=explanation,
        limitations=limitations,
    )
