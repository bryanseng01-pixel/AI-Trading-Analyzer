# Architecture

## System overview

The current application is a Streamlit-based, single-process decision-support system. Its authoritative runtime path is:

```text
Market data
    -> Timeframe analysis
    -> Timeframe roles
    -> Decision authority
    -> Authority market story
    -> Dashboard
```

The chart selector is deliberately outside the strategy path. It selects only the candles and annotations displayed by the chart and cannot change the recommendation.

## Current runtime pipeline

### 1. Market data

`data.py` downloads NQ futures data from Yahoo Finance and uses Streamlit caching. Yahoo supplies 1H, 15M, 5M, and 1M data directly; the current 4H candles are resampled from 1H data.

Yahoo Finance is temporary and cannot provide true bid/ask order flow. No current component should infer delta, footprint imbalance, absorption, or exhaustion from Yahoo candles.

### 2. Timeframe analysis

`analysis_pipeline.analyze_timeframe()` independently analyzes every configured timeframe and returns an immutable `TimeframeAnalysis`. Each result contains its own EMA data, swings, HH/HL/LH/LL labels, structure, close-confirmed BOS/CHoCH, FVGs, and equal highs/lows.

The five current analyses are 4H, 1H, 15M, 5M, and 1M. No selected chart timeframe is reused as a substitute for another role.

### 3. Timeframe roles

`timeframe_roles.evaluate_timeframe_roles()` maps the five analyses into approved roles:

- 4H and 1H EMA direction: preliminary higher-timeframe context;
- 15M structural evidence: setup state;
- latest actual 5M BOS/CHoCH: confirmation;
- latest actual 1M BOS/CHoCH: trigger.

When BOS and CHoCH both exist, the latest event by timestamp controls. EMA direction cannot satisfy the 5M confirmation or 1M trigger role.

### 4. Decision authority

`DecisionAuthority` is the sole recommendation authority. It combines timeframe roles, wick-based session sweeps, and a directional active 1M FVG into one `AuthorityDecision`. That result owns:

- `AVOID`, `WAIT`, `WATCH`, or `READY` status;
- bias and authority confidence;
- confirmed and missing conditions;
- next action;
- playbook phase and next event; and
- the active 1M execution FVG set.

The decision also exposes one immutable six-gate snapshot. Existing authority
views, setup-overlay progress, and confluence evaluation consume that snapshot;
they do not recalculate the strategy gates.

No other current dashboard component is permitted to publish an independent recommendation.

### 5. Authority market story

`authority_market_story.py` converts typed authority roles into plain-language context. It labels EMA as preliminary context and uses actual 5M/1M structural events for confirmation and trigger language.

### 6. Dashboard

`app.py` composes the data and authority pipeline. `dashboard.py` renders the primary authority summary and setup progress. `tradingview_chart.py` renders the selected timeframe using TradingView Lightweight Charts.

The main page shows authority outputs, the selected chart, authority-gate progress, and 1M execution FVG context. Technical, session, and legacy information is presented as non-authoritative diagnostics.

## Current module responsibilities

| Module | Responsibility | Authority status |
|---|---|---|
| `app.py` | Streamlit composition, controls, data orchestration, layout, and diagnostic grouping | Active composition root |
| `data.py` | Yahoo download, Streamlit caching, history selection, column normalization, and 4H resampling | Active data boundary |
| `analysis_pipeline.py` | Builds complete independent `TimeframeAnalysis` objects and filters active FVGs | Active analysis boundary |
| `indicators.py` | EMA calculation and EMA-relative trend label | Active; context input only |
| `structure.py` | Swing-high and swing-low detection | Active |
| `market_structure.py` | HH/HL/LH/LL labeling, structure classification, close-confirmed BOS/CHoCH, and a retained legacy summary | Active technical rules; summary is diagnostic |
| `liquidity.py` | Equal-high and equal-low detection using a point tolerance | Active |
| `fair_value_gap.py` | High/low-based bullish and bearish FVG formation and mitigation state | Active |
| `sessions.py` | New York session windows, session highs/lows, and wick-based sweep detection | Active |
| `timeframe_roles.py` | Typed direction/setup states and explicit timeframe-role mapping | Active strategy boundary |
| `decision_authority.py` | Sole status, confidence, gate, next-action, and playbook-phase authority | Authoritative |
| `setup_overlay.py` | Pure projection of authority state into chart-relevant levels, zones, visibility, and authority-gate progress | Active, non-decision projection |
| `confluence.py` | Pure description of satisfied implemented evidence at an authority-approved location; future factors remain non-counting placeholders | Active analysis, non-authoritative |
| `authority_market_story.py` | Visible narrative derived from authority role states | Authoritative narrative |
| `dashboard.py` | Primary authority summary and authority-only gate progress | Active presentation |
| `tradingview_chart.py` | Converts analysis results to Lightweight Charts candles and annotations | Active presentation |
| `order_blocks.py` | Basic order-block detector | Retained, currently unused |
| `ai_market_coach.py` | Earlier scoring, narrative, and game-plan functions | Legacy, non-authoritative |
| `decision_engine.py` | Earlier weighted trade-plan builder | Legacy, non-authoritative |
| `trade_checklist.py` | Earlier readiness checklist and recommendation | Legacy, non-authoritative |
| `ict_playbook.py` | Earlier standalone ICT playbook evaluator | Legacy, non-authoritative |

Legacy modules remain in the repository for compatibility and comparison. The main dashboard does not call them for recommendations. They must not be reintroduced into the visible decision path without explicit review.

## Current domain rules

- EMA may establish preliminary 4H/1H directional context only.
- 4H/1H disagreement produces conflicting context.
- 15M setup state is `ALIGNED_CONTINUATION`, `COUNTERTREND_PULLBACK`, or `UNCONFIRMED`.
- BOS and CHoCH require a candle close through the relevant swing level.
- A wick-only swing break is not BOS or CHoCH.
- Session liquidity sweeps use candle wicks.
- FVG formation uses candle highs and lows.
- The current execution-zone gate requires a directionally aligned active 1M FVG.
- Chart selection is display-only.

## Test architecture

The test suite uses deterministic synthetic OHLC fixtures and covers:

- EMA and one-row analysis behavior;
- swing and market-structure labels;
- close-confirmed versus wick-only BOS/CHoCH;
- FVG formation and filtering;
- equal highs/lows;
- session levels and wick sweeps;
- independent timeframe analysis;
- timeframe-role mapping and event precedence;
- authority status progression and chart independence;
- authority market-story language; and
- Streamlit layout and selector independence.

## Future component boundaries

The following are planned boundaries, not implemented behavior.

### Confluence contributors

Approved location engines may contribute immutable `ConfluenceFactor` results.
The Confluence Engine accepts those results without knowing how they were
calculated. It does not determine direction, status, confidence, phase, or a
recommendation, and it performs no chart or raw-market analysis. IFVG, order
blocks, premium/discount, volume profile, delta, footprint, bid/ask imbalance,
absorption, SMT, and OTE are placeholders only and are excluded from current
implemented-evidence calculations.

`ConfluenceResult.location_notes` is reserved for future descriptive
observations from approved location engines. It remains empty until such an
engine and its rules are approved.

### Volume profile

A volume-profile service should consume a documented futures volume feed and produce typed profile results such as POC, value-area boundaries, and volume nodes. It may provide location context to `DecisionAuthority`; it must not render an independent recommendation.

### IFVG

An imbalance-lifecycle analyzer should distinguish FVG states from future IFVG states. The approved future constraint is that IFVG confirmation requires a candle close through the zone. Detailed lifecycle and invalidation rules still require separate approval.

### Order blocks

Order-block analysis should be integrated through a typed zone contract after its formation, validity, mitigation, and invalidation rules are approved. The current basic detector is not part of the authority path.

### Order-flow provider

An order-flow provider interface should isolate vendor-specific transport and normalize true bid/ask trades, delta, imbalance, and related metadata. It must expose availability and data quality explicitly. Yahoo Finance cannot implement this interface beyond ordinary candle volume.

### Trade planner

A future trade planner should consume a completed authority setup and approved location/risk inputs. It will be responsible for proposed entry, invalidation, targets, risk/reward, and sizing boundaries. Those rules are not implemented today.

### Swing-options engine

The future swing-options engine must be a separate strategy system with separate data, timeframes, playbooks, risk, authority outputs, and evaluation. It must not reuse day-trading confirmation or trigger rules without independent validation.

## Integration principles

- Prefer typed, provider-independent results at module boundaries.
- Keep analysis functions deterministic and testable with synthetic inputs.
- Keep data acquisition separate from strategy interpretation.
- Route every visible recommendation through `DecisionAuthority`.
- Label diagnostics with their source timeframe and authority status.
- Add future evidence as an approved gate or context input, not as a competing score.
- Preserve day-trading and swing-options separation.

## Known constraints

- The production symbol is currently hard-coded to `NQ=F`; ES selection is planned.
- Yahoo availability, history limits, and candle construction can affect results.
- No true bid/ask order flow is available.
- IFVG, volume profile, execution planning, entries, stops, targets, and sizing are not implemented.
- Stronger 15M thesis-invalidation rules remain undefined.
