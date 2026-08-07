from confluence import ConfluenceFactor
from setup_overlay import SetupOverlay


def build_ifvg_confluence_factor(
    setup_overlay: SetupOverlay,
) -> ConfluenceFactor:
    """Project completed IFVG overlay evidence into optional confluence."""

    support = setup_overlay.ifvg_support
    active = support.applicable and support.evaluated
    satisfied = support.supporting_zone is not None if active else None
    return ConfluenceFactor(
        key="ifvg",
        name="IFVG",
        implemented=True,
        active=active,
        required=False,
        satisfied=satisfied,
        importance="secondary",
        source="FvgLifecycleEngine",
        explanation=support.explanation,
        instrument_key=setup_overlay.instrument_key,
    )
