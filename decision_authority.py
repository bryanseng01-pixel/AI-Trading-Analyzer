from dataclasses import dataclass
from typing import Any, Mapping

from analysis_pipeline import TimeframeAnalysis, select_active_fvgs
from decision_engine import build_trade_plan


@dataclass(frozen=True)
class AuthorityDecision:
    """The one final recommendation exposed by the application."""

    recommendation: str
    strategy_timeframe: str
    analysis: TimeframeAnalysis
    active_fvgs: list[dict[str, Any]]
    trade_plan: dict[str, Any]


class DecisionAuthority:
    """Build the final recommendation from precomputed market analysis."""

    def __init__(self, strategy_timeframe: str = "4 Hour") -> None:
        # Four Hour preserves the dashboard's former default decision basis.
        self.strategy_timeframe = strategy_timeframe

    def evaluate(
        self,
        analyses: Mapping[str, TimeframeAnalysis],
        session_levels: Mapping[str, dict[str, Any]],
        *,
        minimum_fvg_size: float,
        maximum_fvgs: int,
    ) -> AuthorityDecision:
        analysis = analyses[self.strategy_timeframe]
        active_fvgs = select_active_fvgs(
            analysis,
            minimum_size=minimum_fvg_size,
            maximum_count=maximum_fvgs,
        )
        bullish_fvgs = [
            fvg for fvg in active_fvgs if fvg["type"] == "bullish"
        ]
        bearish_fvgs = [
            fvg for fvg in active_fvgs if fvg["type"] == "bearish"
        ]
        trade_plan = build_trade_plan(
            analysis.trend,
            analysis.structure,
            analysis.bos,
            analysis.choch,
            bullish_fvgs,
            bearish_fvgs,
            session_levels,
        )

        return AuthorityDecision(
            recommendation=trade_plan["status"],
            strategy_timeframe=self.strategy_timeframe,
            analysis=analysis,
            active_fvgs=active_fvgs,
            trade_plan=trade_plan,
        )
