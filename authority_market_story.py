from timeframe_roles import Direction, SetupState, TimeframeRoleState


def build_authority_market_story(
    roles: TimeframeRoleState,
) -> list[str]:
    """Describe the approved timeframe roles without inferring structure from EMA."""

    story: list[str] = []
    context = roles.context_direction

    if context is None:
        story.append(
            "The preliminary 4-hour and 1-hour EMA context is conflicting."
        )
    else:
        story.append(
            "The preliminary 4-hour and 1-hour EMA context is "
            f"aligned {context.value}."
        )

    if roles.setup_state == SetupState.ALIGNED_CONTINUATION:
        story.append(
            "The 15-minute structural setup supports continuation "
            "with the higher-timeframe context."
        )
    elif roles.setup_state == SetupState.COUNTERTREND_PULLBACK:
        story.append(
            "The 15-minute structure is countertrend and is being treated "
            "as a developing pullback, not an invalidation."
        )
    else:
        story.append("The 15-minute structural setup is not confirmed.")

    story.append(
        _structural_event_sentence(
            timeframe="5-minute",
            signal_direction=roles.confirmation_direction,
            context_direction=context,
            aligned_text="confirmation",
        )
    )
    story.append(
        _structural_event_sentence(
            timeframe="1-minute",
            signal_direction=roles.trigger_direction,
            context_direction=context,
            aligned_text="trigger",
        )
    )

    return story


def _structural_event_sentence(
    *,
    timeframe: str,
    signal_direction: Direction | None,
    context_direction: Direction | None,
    aligned_text: str,
) -> str:
    if signal_direction is None:
        return (
            f"No close-confirmed {timeframe} BOS or CHoCH is available "
            f"for {aligned_text}."
        )

    if context_direction is not None and signal_direction == context_direction:
        return (
            f"The latest close-confirmed {timeframe} BOS/CHoCH is "
            f"{signal_direction.value} and provides {aligned_text}."
        )

    return (
        f"The latest close-confirmed {timeframe} BOS/CHoCH is "
        f"{signal_direction.value} and does not align with context."
    )
