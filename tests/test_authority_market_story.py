from timeframe_roles import Direction, SetupState, TimeframeRoleState

from authority_market_story import build_authority_market_story


def test_story_requires_actual_5m_and_1m_structural_events():
    roles = TimeframeRoleState(
        context_direction=Direction.BULLISH,
        setup_state=SetupState.ALIGNED_CONTINUATION,
        setup_direction=Direction.BULLISH,
        confirmation_direction=None,
        trigger_direction=None,
    )

    story = build_authority_market_story(roles)

    assert any(
        "No close-confirmed 5-minute BOS or CHoCH" in sentence
        for sentence in story
    )
    assert any(
        "No close-confirmed 1-minute BOS or CHoCH" in sentence
        for sentence in story
    )
    assert not any("execution" in sentence.lower() for sentence in story)


def test_story_reports_actual_aligned_confirmation_and_trigger():
    roles = TimeframeRoleState(
        context_direction=Direction.BEARISH,
        setup_state=SetupState.COUNTERTREND_PULLBACK,
        setup_direction=Direction.BULLISH,
        confirmation_direction=Direction.BEARISH,
        trigger_direction=Direction.BEARISH,
    )

    story = build_authority_market_story(roles)

    assert any("developing pullback" in sentence for sentence in story)
    assert any(
        "5-minute BOS/CHoCH is bearish and provides confirmation" in sentence
        for sentence in story
    )
    assert any(
        "1-minute BOS/CHoCH is bearish and provides trigger" in sentence
        for sentence in story
    )


def test_story_reports_conflicting_preliminary_ema_context():
    roles = TimeframeRoleState(
        context_direction=None,
        setup_state=SetupState.UNCONFIRMED,
        setup_direction=Direction.BULLISH,
        confirmation_direction=Direction.BULLISH,
        trigger_direction=Direction.BULLISH,
    )

    story = build_authority_market_story(roles)

    assert story[0] == (
        "The preliminary 4-hour and 1-hour EMA context is conflicting."
    )
    assert any("does not align with context" in sentence for sentence in story)
