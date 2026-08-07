from dataclasses import dataclass
from enum import Enum

from confluence import ConfluenceFactor
from order_flow_models import OrderFlowAnalysisMetadata


class OrderFlowFactorKey(str, Enum):
    DELTA_CONFIRMATION = "delta_confirmation"
    CUMULATIVE_DELTA_CONTEXT = "cumulative_delta_context"
    BID_ASK_IMBALANCE = "bid_ask_imbalance"
    FOOTPRINT = "footprint"
    ABSORPTION = "absorption"
    EXHAUSTION = "exhaustion"


@dataclass(frozen=True)
class CompletedOrderFlowAssessment:
    """Future approved engines supply this; the adapter adds no rules."""

    key: OrderFlowFactorKey
    name: str
    metadata: OrderFlowAnalysisMetadata
    evaluated: bool
    supportive: bool | None
    explanation: str

    def __post_init__(self) -> None:
        if not self.name or not self.explanation:
            raise ValueError("Completed assessments require name and explanation.")
        if self.evaluated and self.supportive is None:
            raise ValueError("Evaluated assessments require an explicit result.")
        if not self.evaluated and self.supportive is not None:
            raise ValueError("Unevaluated assessments cannot claim support.")


def build_order_flow_confluence_factor(
    assessment: CompletedOrderFlowAssessment,
) -> ConfluenceFactor:
    """Adapt a completed assessment without interpreting order-flow data."""

    return ConfluenceFactor(
        key=assessment.key.value,
        name=assessment.name,
        implemented=True,
        active=assessment.evaluated,
        required=False,
        satisfied=assessment.supportive if assessment.evaluated else None,
        importance="secondary",
        source=assessment.metadata.engine_name,
        explanation=assessment.explanation,
    )
