from dataclasses import replace

from confluence import ConfluenceFactor
from setup_overlay import (
    OverlayAnnotation,
    OverlayAnnotationKind,
    OverlayProfileNode,
    OverlayProfileRange,
    SetupOverlay,
    VolumeProfileOverlaySupport,
    inactive_volume_profile_support,
)
from volume_profile_engine import (
    ProfileValidity,
    VolumeNode,
    VolumeNodeKind,
    VolumeProfileResult,
    assess_execution_zone_profile,
)


def attach_volume_profile_support(
    setup_overlay: SetupOverlay,
    profile: VolumeProfileResult | None,
) -> SetupOverlay:
    """Attach completed profile evidence without changing authority state."""

    if profile is not None and profile.instrument_key != setup_overlay.instrument_key:
        raise ValueError("Volume Profile instrument does not match SetupOverlay.")
    zone = setup_overlay.active_execution_zone
    applicable = (
        setup_overlay.authority_status in {"WATCH", "READY"}
        and setup_overlay.visibility.show_execution_zone
        and setup_overlay.direction is not None
        and zone is not None
    )
    if not applicable:
        support = inactive_volume_profile_support(
            "Volume Profile requires a visible authority execution FVG."
        )
        return replace(setup_overlay, volume_profile_support=support)
    if profile is None or profile.validity != ProfileValidity.VALID:
        limitations = profile.limitations if profile is not None else ()
        support = inactive_volume_profile_support(
            "A valid previous completed New York session profile is unavailable.",
            applicable=True,
            limitations=limitations,
        )
        return replace(
            setup_overlay,
            volume_profile_support=support,
            limitations=setup_overlay.limitations + tuple(limitations),
        )

    assessment = assess_execution_zone_profile(
        profile,
        execution_zone_bottom=zone.bottom,
        execution_zone_top=zone.top,
        direction=setup_overlay.direction,
    )
    if not assessment.evaluated:
        support = inactive_volume_profile_support(
            assessment.explanation,
            applicable=True,
            limitations=assessment.limitations,
        )
        return replace(setup_overlay, volume_profile_support=support)

    profile_range = profile.profile_range
    value_area = profile.value_area
    assert profile_range is not None and value_area is not None
    selected_hvn = _select_intersecting_node(
        profile.nodes, VolumeNodeKind.HVN, zone.bottom, zone.top
    )
    selected_lvn = _select_intersecting_node(
        profile.nodes, VolumeNodeKind.LVN, zone.bottom, zone.top
    )
    support = VolumeProfileOverlaySupport(
        applicable=True,
        evaluated=True,
        profile_range=OverlayProfileRange(
            start_time=profile_range.start_time,
            end_time=profile_range.end_time,
            price_low=profile_range.price_low,
            price_high=profile_range.price_high,
            poc=value_area.poc_price,
            vah=value_area.vah,
            val=value_area.val,
            source=profile.source.value,
            data_quality=profile.data_quality.value,
            importance="secondary",
        ),
        selected_hvn=_overlay_node(selected_hvn),
        selected_lvn=_overlay_node(selected_lvn),
        assessment=assessment,
        relationships=assessment.relationships,
        explanation=assessment.explanation,
        limitations=assessment.limitations,
    )
    annotation = OverlayAnnotation(
        kind=OverlayAnnotationKind.OPTIONAL_CONFLUENCE,
        text=(
            "Previous NY bar-volume profile: "
            + ", ".join(
                relationship.value.replace("_", " ")
                for relationship in assessment.relationships
            )
        ),
    )
    return replace(
        setup_overlay,
        volume_profile_support=support,
        visibility=replace(setup_overlay.visibility, show_volume_profile=True),
        annotations=setup_overlay.annotations + (annotation,),
        limitations=setup_overlay.limitations + assessment.limitations,
    )


def build_volume_profile_confluence_factor(
    setup_overlay: SetupOverlay,
) -> ConfluenceFactor:
    """Project a completed profile assessment into optional confluence."""

    support = setup_overlay.volume_profile_support
    active = support.applicable and support.evaluated
    satisfied = (
        support.assessment.directionally_supportive
        if active and support.assessment is not None
        else None
    )
    return ConfluenceFactor(
        key="volume_profile",
        name="Volume Profile Location",
        implemented=True,
        active=active,
        required=False,
        satisfied=satisfied,
        importance="secondary",
        source="VolumeProfileEngine",
        explanation=support.explanation,
        instrument_key=setup_overlay.instrument_key,
    )


def _select_intersecting_node(
    nodes: tuple[VolumeNode, ...],
    kind: VolumeNodeKind,
    zone_bottom: float,
    zone_top: float,
) -> VolumeNode | None:
    candidates = [
        node
        for node in nodes
        if node.kind == kind
        and min(zone_top, node.top) > max(zone_bottom, node.bottom)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda node: (node.bottom, node.top, node.peak_price))


def _overlay_node(node: VolumeNode | None) -> OverlayProfileNode | None:
    if node is None:
        return None
    return OverlayProfileNode(
        kind=node.kind,
        bottom=node.bottom,
        top=node.top,
        peak_price=node.peak_price,
        importance="secondary",
    )
