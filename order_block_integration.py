from confluence import ConfluenceFactor
from setup_overlay import SetupOverlay


def build_order_block_confluence_factor(
    setup_overlay: SetupOverlay,
) -> ConfluenceFactor:
    """Project completed Order Block support into optional confluence."""

    support = setup_overlay.order_block_support
    active = support.applicable and support.evaluated
    satisfied = support.supporting_zone is not None if active else None
    return ConfluenceFactor(
        key="order_block",
        name="Order Block",
        implemented=True,
        active=active,
        required=False,
        satisfied=satisfied,
        importance="secondary",
        source="OrderBlockEngine",
        explanation=support.explanation,
        instrument_key=setup_overlay.instrument_key,
    )
