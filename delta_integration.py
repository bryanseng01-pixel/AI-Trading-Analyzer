from confluence import ConfluenceFactor
from delta_engine import DeltaLocationAssessment, DeltaLocationState


def build_delta_confluence_factor(
    assessment: DeltaLocationAssessment,
) -> ConfluenceFactor:
    """Adapt a completed Delta assessment without inspecting trades."""

    active = assessment.state != DeltaLocationState.UNAVAILABLE
    return ConfluenceFactor(
        key="delta_confirmation",
        name="Delta Confirmation",
        implemented=True,
        active=active,
        required=False,
        satisfied=assessment.supportive if active else None,
        importance="secondary",
        source="DeltaEngine",
        explanation=assessment.explanation,
    )
