from confluence import ConfluenceFactor
from setup_overlay import SetupOverlay


def build_premium_discount_confluence_factor(
    setup_overlay: SetupOverlay,
) -> ConfluenceFactor:
    """Project completed range classification into optional confluence."""

    support = setup_overlay.premium_discount_support
    active = support.applicable and support.evaluated
    satisfied = support.directionally_aligned if active else None
    return ConfluenceFactor(
        key="premium_discount",
        name="Premium / Discount",
        implemented=True,
        active=active,
        required=False,
        satisfied=satisfied,
        importance="secondary",
        source="PremiumDiscountEngine",
        explanation=support.explanation,
    )
