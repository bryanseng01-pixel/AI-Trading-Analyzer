# Product Vision

## Product definition

The AI Trading Analyzer is an ICT, volume-profile, and order-flow decision-support platform for discretionary futures traders. Its current focus is selectable intraday analysis of NQ and ES through one shared strategy pipeline. The typed instrument registry is extensible to additional futures without duplicating strategy logic. The product is intended to help a trader follow a repeatable process from higher-timeframe context through setup development, confirmation, and execution location.

The platform is not an automated trade signal, trade-execution system, or guaranteed market-prediction system. A `READY` result means only that the currently approved playbook gates are aligned. It is not an instruction to enter a position. The trader remains responsible for data quality, timing, invalidation, risk, position size, and execution.

## The three core questions

Every primary dashboard element should help answer one of three questions:

1. **What is the market trying to do?**
   Establish preliminary directional context and describe the active structural setup without overstating certainty.
2. **What must happen next?**
   Identify the next incomplete playbook gate, such as a relevant liquidity sweep or close-confirmed structural event.
3. **Where is the execution if the setup completes?**
   Identify a valid execution location only after the required context, liquidity, confirmation, and trigger conditions are present.

## Product principles

### Clarity

The dashboard should present one coherent interpretation. `DecisionAuthority` is the sole recommendation authority; diagnostic calculations must never compete with its status, confidence, confirmed conditions, missing conditions, next action, or playbook phase.

### Discipline

The platform should make incomplete conditions explicit. Its primary value is filtering trades and reinforcing process, not maximizing the number of opportunities shown.

### Location

Directional context is insufficient without an appropriate location. The current temporary execution-location gate is a directionally aligned active 1-minute FVG. Future volume-profile and approved ICT-location models will add context without bypassing existing gates.

### Confirmation

Confirmation must come from the event defined by the playbook. EMA direction may establish preliminary 4H/1H context, but it must never be described as MSS, BOS, CHoCH, or execution confirmation. BOS and CHoCH require candle closes; liquidity sweeps use wicks.

### Risk validation

No setup is complete merely because the market has a directional narrative. Before any trade, the user must independently validate invalidation, position size, risk limits, and expected reward. Entry, stop, target, and sizing logic are not implemented today.

## Decision-support workflow

The intended day-trading workflow is:

```text
Preliminary context
    -> 15M setup development
    -> relevant liquidity sweep
    -> close-confirmed 5M confirmation
    -> close-confirmed 1M trigger
    -> execution location
    -> independent risk validation
```

The current implementation supports this workflow through the ICT Liquidity Sweep Reversal playbook. Additional playbooks must be separately defined and approved before their rules enter `DecisionAuthority`.

## Market-data reality

Yahoo Finance is a temporary OHLCV data source. It is suitable for prototyping candle-based analysis, but it cannot supply true bid/ask order flow. Yahoo data must not be used to infer footprint imbalances, traded-at-bid versus traded-at-ask volume, delta, cumulative delta, absorption, or exhaustion.

True order-flow features require a provider with appropriate futures exchange entitlements, bid/ask classification, reliable timestamps, and documented latency and retention characteristics. Until such a provider is integrated, the product must clearly report order-flow confirmation as unavailable rather than fabricate a substitute from candles.

## Product success criteria

The product succeeds when it helps a trader:

- understand the active context without confusing it with certainty;
- see the next required event immediately;
- avoid trades whose playbook gates are incomplete;
- distinguish context, confirmation, trigger, and location;
- obtain the same recommendation regardless of the displayed chart timeframe;
- review reproducible, testable reasons for every authority state; and
- improve rule adherence and risk discipline rather than chase more signals.
