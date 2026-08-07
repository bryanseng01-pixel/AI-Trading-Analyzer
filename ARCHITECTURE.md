# Architecture

## System overview

The current application is a Streamlit-based, single-process decision-support system. Its authoritative runtime path is:

```text
Market data
    -> Instrument analysis bundle
    -> Timeframe analysis
    -> Timeframe roles
    -> Decision authority
    -> Authority market story
    -> Dashboard
```

The chart selector is deliberately outside the strategy path. It selects only the candles and annotations displayed by the chart and cannot change the recommendation.

## Current runtime pipeline

### 1. Market data

`instruments.py` owns the immutable, extensible instrument registry. NQ maps to `NQ=F` and ES maps to `ES=F`; both compose the existing order-flow `FuturesInstrument` model and currently use a 0.25 tick. Adding another instrument is a registry-entry change rather than an analytical-engine branch.

`data.py` resolves the selected registry key, downloads its Yahoo Finance symbol, and uses the instrument key plus timeframe as the Streamlit cache identity. Yahoo supplies 1H, 15M, 5M, and 1M data directly; the current 4H candles are resampled from 1H data.

Yahoo Finance is temporary and cannot provide true bid/ask order flow. No current component should infer delta, footprint imbalance, absorption, or exhaustion from Yahoo candles.

### 2. Timeframe analysis

`instrument_pipeline.build_instrument_analysis()` creates one immutable `InstrumentAnalysisBundle` for the selected instrument. It owns the strategy-wide timeframe analyses, sessions, authority decision, location results, SetupOverlay, Volume Profile, and Confluence result. Integration boundaries reject mixed instrument provenance.

`analysis_pipeline.analyze_timeframe()` independently analyzes every configured timeframe and returns an immutable, instrument-qualified `TimeframeAnalysis`. Each result contains its own EMA data, swings, HH/HL/LH/LL labels, structure, close-confirmed BOS/CHoCH, FVGs, and equal highs/lows.

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

`app.py` selects an instrument from registry-derived options, loads all five instrument-keyed frames, and renders the completed instrument bundle. `dashboard.py` renders the primary authority summary and setup progress. `tradingview_chart.py` renders the selected timeframe using TradingView Lightweight Charts.

The main page shows authority outputs, the selected chart, authority-gate progress, and 1M execution FVG context. Technical, session, and legacy information is presented as non-authoritative diagnostics.

## Current module responsibilities

| Module | Responsibility | Authority status |
|---|---|---|
| `app.py` | Streamlit composition, controls, data orchestration, layout, and diagnostic grouping | Active composition root |
| `instruments.py` | Extensible immutable instrument registry, Yahoo mapping, shared strategy defaults, and qualified location identities | Active instrument boundary |
| `instrument_pipeline.py` | Builds and validates one strategy-wide `InstrumentAnalysisBundle` | Active orchestration boundary |
| `data.py` | Yahoo download, Streamlit caching, history selection, column normalization, and 4H resampling | Active data boundary |
| `analysis_pipeline.py` | Builds complete independent `TimeframeAnalysis` objects and filters active FVGs | Active analysis boundary |
| `indicators.py` | EMA calculation and EMA-relative trend label | Active; context input only |
| `structure.py` | Swing-high and swing-low detection | Active |
| `market_structure.py` | HH/HL/LH/LL labeling, structure classification, close-confirmed BOS/CHoCH, and a retained legacy summary | Active technical rules; summary is diagnostic |
| `liquidity.py` | Equal-high and equal-low detection using a point tolerance | Active |
| `fair_value_gap.py` | High/low-based bullish and bearish FVG formation and mitigation state | Active |
| `fvg_lifecycle.py` | Immutable FVG interaction, fill, close-confirmed inversion, IFVG invalidation, and relevance selection | Active analytical engine; not integrated into authority |
| `ifvg_integration.py` | Adapts completed SetupOverlay IFVG support into one optional, non-required confluence factor | Active non-authoritative adapter |
| `sessions.py` | New York session windows, session highs/lows, and wick-based sweep detection | Active |
| `timeframe_roles.py` | Typed direction/setup states and explicit timeframe-role mapping | Active strategy boundary |
| `decision_authority.py` | Sole status, confidence, gate, next-action, and playbook-phase authority | Authoritative |
| `setup_overlay.py` | Pure projection of authority state into chart-relevant levels, zones, visibility, and authority-gate progress | Active, non-decision projection |
| `confluence.py` | Pure description of satisfied implemented evidence at an authority-approved location; future factors remain non-counting placeholders | Active analysis, non-authoritative |
| `authority_market_story.py` | Visible narrative derived from authority role states | Authoritative narrative |
| `dashboard.py` | Primary authority summary and authority-only gate progress | Active presentation |
| `tradingview_chart.py` | Converts analysis results to Lightweight Charts candles and annotations | Active presentation |
| `order_blocks.py` | Basic order-block detector | Retained, currently unused |
| `order_block_engine.py` | Typed structural Order Block formation, qualified displacement, lifecycle, and deterministic overlap selection | Active analytical engine; non-authoritative |
| `order_block_integration.py` | Adapts completed Order Block overlay support into one optional, non-required confluence factor | Active non-authoritative adapter |
| `order_flow_models.py` | Immutable provider identity, futures contract, provenance, normalized event, execution-location, and analytical metadata contracts | Active architecture boundary; no analysis rules |
| `order_flow_provider.py` | Vendor-neutral historical/live provider protocols, explicit-contract resolution boundary, and OHLCV-only source rejection | Active provider boundary; no vendor selected |
| `order_flow_engines.py` | Typed result models and independent protocols for Delta, Cumulative Delta, Bid/Ask Imbalance, Footprint, Absorption, and Exhaustion | Contract only; analytical rules deferred |
| `order_flow_integration.py` | Adapts a future approved completed order-flow assessment into one optional confluence factor without interpreting data | Active non-authoritative adapter |
| `premium_discount_engine.py` | Builds one latest completed directional 15M swing-leg range and classifies the authority FVG | Active analytical engine; non-authoritative |
| `premium_discount_integration.py` | Adapts completed Premium/Discount classification into one optional, non-required confluence factor | Active non-authoritative adapter |
| `volume_profile_engine.py` | Builds one previous completed New York session bar-distributed volume-at-price approximation and assesses only the authority FVG | Active analytical engine; non-authoritative |
| `volume_profile_integration.py` | Projects completed profile context into SetupOverlay and one optional, non-required confluence factor | Active non-authoritative adapter |
| `ai_market_coach.py` | Earlier scoring, narrative, and game-plan functions | Legacy, non-authoritative |
| `decision_engine.py` | Earlier weighted trade-plan builder | Legacy, non-authoritative |
| `delta_engine.py` | Builds stable authority-FVG observation windows, calculates deterministic location-only Delta, and produces conservative directional assessments | Active analytical engine; synthetic normalized trades only |
| `delta_integration.py` | Adapts a completed Delta location assessment into the optional `delta_confirmation` factor | Active non-authoritative adapter |
| `delta_aggregation.py` | Shared deterministic BUY/SELL/UNKNOWN bucket arithmetic and immutable completed `DeltaBucketSeries` contract | Active order-flow calculation boundary |
| `cumulative_delta_engine.py` | Recomputes zero-based current-session Cumulative Delta from completed buckets and describes authority-interaction context | Active descriptive engine; no confluence or UI integration |
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
recommendation, and it performs no chart or raw-market analysis. Volume
delta, footprint, bid/ask imbalance,
absorption, SMT, and OTE are placeholders only and are excluded from current
implemented-evidence calculations.

IFVG, Order Block, Premium/Discount, and Volume Profile engines now have
optional adapters. Their factors remain non-required and cannot modify
authority state.

### Premium / Discount

`premium_discount_engine.py` uses one definition only: the latest completed
directional 15M swing leg aligned with authority context. Bullish ranges run
from a confirmed swing low to the subsequent swing high; bearish ranges run
from a confirmed swing high to the subsequent swing low. A later confirmed
external swing invalidates the range without fallback to an older range.

The existing authority FVG must be fully contained in the range. Bullish
discount and bearish premium are optional supporting evidence. Wrong-side,
equilibrium-crossing, and outside-range locations are evaluable but
unsatisfied. This engine does not select an execution zone or alter authority.

`ConfluenceResult.location_notes` is reserved for future descriptive
observations from approved location engines. It remains empty until such an
engine and its rules are approved.

### Volume profile

`volume_profile_engine.py` builds one profile definition only: the previous
completed New York session, using fixed 1M OHLCV and the existing 08:30-17:00
America/New_York window. `VolumeProfileRules` centralizes the approved 70%
value area and four ticks per bin. NQ and ES both use a 0.25 tick, producing
one-point price bins. The profile uses a
deterministic uniform distribution of each bar's reported volume across every
intersected price bin.

This is a bar-volume approximation, not a true tick-level volume profile. It
cannot identify traded-at-bid/ask volume, delta, footprint imbalance,
absorption, aggressor side, or intrabar sequencing. Missing bars and the lack
of holiday/early-close calendar handling remain visible limitations.

The engine produces POC, VAH, VAL, and descriptive HVN/LVN nodes. It evaluates
only the existing authority-selected 1M FVG. Bullish location at or below VAL
and bearish location at or above VAH may contribute one optional factor. POC,
HVN, and LVN observations are descriptive and do not independently satisfy
confluence. The profile does not select an execution zone or modify authority.

### IFVG

`fvg_lifecycle.py` now models untouched, entered, partially mitigated,
fully filled, inverted, and invalidated states. Wick extremes control zone
interaction and fill depth. A bullish FVG becomes a bearish IFVG only after a
close below its bottom; a bearish FVG becomes a bullish IFVG only after a close
above its top. Wick-only boundary breaks do not confirm inversion.

The application evaluates this lifecycle from fixed 1M execution data.
`SetupOverlay` may project at most one active directional IFVG when it strictly
overlaps the visible authority-selected 1M FVG. The chart renders that IFVG as
optional confluence, separately from the authority-required FVG. A thin adapter
can replace Confluence Engine's IFVG placeholder with a non-required factor;
Confluence does not inspect candles or calculate inversion.

`DecisionAuthority` does not consume lifecycle or IFVG results. The current
directional active 1M FVG gate, status, confidence, direction, and phase remain
unchanged. IFVG cannot substitute for the authority FVG.

### Order blocks

`order_block_engine.py` requires an existing close-confirmed BOS or CHoCH,
qualified displacement, and a bounded opposing source candle. It uses the full
source-candle range and tracks untouched, touched, partially mitigated, fully
mitigated, and close-invalidated states. Setup Overlay may project at most one
active directional 1M block with strict positive overlap against the visible
authority FVG. Confluence receives only the completed optional factor and does
not calculate blocks from candles.

The earlier `order_blocks.py` color-transition detector remains unchanged for
legacy compatibility and is non-authoritative. Neither detector changes
DecisionAuthority status, confidence, direction, phase, or gates.

### Order-flow provider

The implemented `OrderFlowProvider` protocol isolates vendor transport behind
identical historical and live normalized batches. Every batch identifies the
provider, explicit futures contract, timestamp range, granularity, entitlement,
sequence coverage, data quality, and limitations. Vendor SDK types may not
escape the adapter.

Normalized immutable contracts now exist for trades, quotes, provider price-
level aggregates, gaps, and authority execution-location windows. Analytical
metadata includes `confidence_reasons`, which contains descriptive provenance
reasons only. It is not a score and is excluded from authority, confluence,
overlay, recommendation, and rendering behavior.

Yahoo Finance is explicitly rejected by this boundary because it is an
OHLCV-only source. Candle direction cannot estimate delta or bid/ask volume,
ordinary bar volume is not order flow, and Yahoo candles cannot be expanded
into a synthetic footprint.

Typed result contracts and independent engine protocols exist for Delta,
Cumulative Delta, Bid/Ask Imbalance, Footprint, Absorption, and Exhaustion.
The first deterministic Delta engine is implemented for normalized synthetic
or replayed `TradeEvent` data. It begins at the first in-zone trade after an
authority-visible WATCH/READY snapshot, includes only trades inside the same
stable authority FVG, and calculates ask volume minus bid volume in one-second
buckets anchored to first touch. UNKNOWN volume remains visible and is never
redistributed.

Delta directional interpretation requires aligned raw Delta and at least one
tick of aligned in-zone price progress. Disagreement is mixed/divergent and
does not claim absorption, exhaustion, trapped traders, or formal divergence.
Poor classification coverage, sequence gaps, delayed live data, entitlement
failure, contract mismatch, conflicting duplicates, and unresolved corrections
fail closed for directional confluence. The optional `delta_confirmation`
factor consumes only the completed assessment and cannot modify authority.

Cumulative Delta is also implemented as a separate pure engine. Its sole
normal Version 1 anchor is the current scheduled 08:30 ET New York session
open, initialized to zero. It consumes completed canonical one-second
`DeltaBucketSeries` objects produced through the same shared arithmetic used by
DeltaEngine. Gaps, rollover, entitlement failure, unresolved corrections, and
unexpected provenance fail closed; delayed and low-coverage series remain
degraded diagnostics.

Cumulative location assessment reports only movement before and during an
authority interaction. `supportive` remains `None`, and the
`cumulative_delta_context` Confluence placeholder remains inactive. No price-
alignment or divergence rule exists.

Bid/Ask Imbalance, Footprint, Absorption, and Exhaustion calculations remain
unimplemented and require separate approval. No licensed provider, live
connection, application integration, or order-flow UI exists.

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

- NQ and ES are selectable through one registry-driven strategy pipeline; additional instruments require validated registry metadata and tests.
- Yahoo availability, history limits, and candle construction can affect results.
- No live or historical licensed order-flow provider is configured.
- Delta calculation and assessment rules exist for normalized synthetic data; no licensed feed is configured.
- Cumulative Delta exists as descriptive context only; its Confluence placeholder remains inactive.
- Other order-flow analytical engine rules remain unimplemented.
- IFVG lifecycle, optional overlay, chart, and confluence integration exist; IFVG authority behavior is intentionally not implemented.
- Order Block location evidence is optional and has no authority role.
- Volume Profile approximation and optional location integration are implemented; a true tick-level profile is not.
- Execution planning, entries, stops, targets, and sizing are not implemented.
- Stronger 15M thesis-invalidation rules remain undefined.
