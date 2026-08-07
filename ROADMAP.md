# Product Roadmap

## Roadmap principles

- Deliver small, testable changes that preserve characterized behavior unless a strategy change is explicitly approved.
- Keep `DecisionAuthority` as the sole recommendation authority.
- Make data provenance and unavailable evidence visible.
- Do not infer true order flow from Yahoo Finance OHLCV.
- Add location, confirmation, and risk evidence as approved authority inputs rather than competing scores.
- Keep the day-trading system and future swing-options system separate.

## Version 1: Stable authority dashboard

### Current foundation

Version 1 establishes the current day-trading platform:

- cached Yahoo Finance data for 4H, 1H, 15M, 5M, and 1M;
- independent `TimeframeAnalysis` results;
- EMA context, market structure, close-confirmed BOS/CHoCH, FVGs, equal highs/lows, session levels, and wick sweeps;
- explicit timeframe roles;
- one `DecisionAuthority`;
- authority market story and setup progress;
- display-only chart selection; and
- synthetic rule, authority, story, and Streamlit UI tests.

### Remaining Version 1 work

- Improve empty/partial market-data handling and user-facing errors.
- Centralize symbol, timeframe, threshold, and session configuration.
- Add NQ/ES instrument selection without mixing cached results.
- Improve weekend/holiday session selection.
- Pin and maintain presentation dependencies.
- Continue documentation and operational runbooks.

### Dependencies

- Stable OHLCV schema and timezone handling
- Existing characterization suite
- Versioned authority result contracts

### Risks

- Yahoo outages, throttling, and history restrictions
- Futures session and rollover differences
- Hard-coded assumptions about NQ point tolerances
- UI-library and chart-library compatibility
- Diagnostic terminology drifting away from authority terminology

## Version 1.5: ICT location and imbalance improvements

### Planned scope

- Continue validating the implemented typed FVG lifecycle and its optional overlay/confluence projection.
- Keep close-confirmed IFVG evidence outside authority unless a later, separately approved playbook change defines it as a gate.
- Continue validating the implemented structural Order Block engine and its optional overlay/confluence projection without promoting it to an authority gate.
- Refine liquidity-pool lifecycle and session selection.
- Define stronger 15M thesis-reversal and invalidation rules.
- Improve the relationship among setup structure, liquidity event, and execution location.

### Dependencies

- Typed zone identifiers and lifecycle events
- Timestamped timeframe analyses
- Characterization tests for every new close-versus-wick rule
- Explicit priority when multiple zone types overlap

### Risks

- Ambiguous or vendor-specific ICT terminology
- Retrospective overfitting of zone definitions
- Conflicting FVG, IFVG, and order-block states
- Excessive chart clutter
- Accidentally treating location as confirmation

## Version 2: Volume profile and execution planning

### Planned scope

- Introduce a provider-independent volume-profile service.
- Define session and, if approved, composite profile construction.
- Expose POC, value-area high/low, high-volume nodes, and low-volume nodes.
- Evaluate location, acceptance, and rejection through approved authority inputs.
- Introduce a separate trade-planner boundary.
- Define proposed entry, invalidation, target, risk/reward, and sizing validation only after explicit approval.
- Keep execution manual unless a later product decision authorizes otherwise.

### Dependencies

- Reliable and correctly normalized futures volume
- Trading-session and rollover policies
- Typed profile and location models
- Stable authority gate API
- Approved risk policy and instrument specifications

### Risks

- Different profile-construction methods producing different conclusions
- Incomplete overnight or rollover volume
- Incorrect contract stitching
- False precision in entry and target plans
- Allowing the planner to bypass incomplete authority gates

## Version 2.5: Real order flow

### Planned scope

- Select a futures data provider with required exchange entitlements.
- Implement an order-flow provider interface isolated from strategy logic.
- Normalize traded-at-bid and traded-at-ask volume.
- Add delta, cumulative delta, footprint imbalance, and approved absorption/exhaustion evidence.
- Report unavailable, delayed, or incomplete order-flow state explicitly.
- Integrate approved order-flow confirmation points through `DecisionAuthority`.

Yahoo Finance cannot provide true bid/ask order flow and will not be used as a substitute for these features.

### Dependencies

- Vendor selection and commercial agreement
- Exchange permissions and credentials
- Timestamp, sequence, and contract normalization
- Storage and replay strategy for granular events
- Latency and data-quality monitoring
- Approved order-flow definitions and tests

### Risks

- Data cost and exchange entitlement restrictions
- Vendor lock-in
- Latency, packet loss, corrections, and feed gaps
- Incorrect aggressor-side classification
- Large storage and replay requirements
- Treating noisy microstructure evidence as certainty

## Version 3: Trade journal, replay, and coaching

### Planned scope

- Persist versioned authority decisions and their input snapshots.
- Record confirmed and missing gates at decision time.
- Support setup replay without future-data leakage.
- Add trader annotations, outcome tags, and process-adherence review.
- Compare planned conditions with actual decisions.
- Build coaching around discipline and rule adherence, not guaranteed prediction.

### Dependencies

- Stable, versioned authority and playbook schemas
- Durable storage and migration strategy
- Historical data retention and replay services
- Privacy and retention policy
- Defined outcome and adherence metrics

### Risks

- Hindsight and survivorship bias
- Data leakage during replay
- Incomplete manual journal data
- Optimizing for outcome rather than process
- Privacy and storage growth

## Version 4: Separate swing-options engine

### Planned scope

Version 4 introduces a separate swing-options decision-support engine. It is not an extension of the intraday trigger chain.

The engine will require its own:

- market and options-chain data providers;
- higher-timeframe context and playbooks;
- implied-volatility, term-structure, and options-liquidity models;
- risk, sizing, spread, assignment, and expiration policies;
- `DecisionAuthority`-equivalent output contract;
- dashboard surface; and
- characterization and replay tests.

No swing-options rule is currently approved. Intraday 5M/1M confirmation and trigger rules must not be reused for swing options without independent research, definition, and validation.

### Dependencies

- Reliable options-chain and underlying data
- Greeks and implied-volatility calculations
- Corporate-action and expiration calendars
- Options-specific risk and liquidity models
- Separate strategy storage and evaluation

### Risks

- Wide spreads and limited liquidity
- Volatility-surface and Greek-model assumptions
- Early assignment and expiration behavior
- Event and overnight gap risk
- Mixing day-trading evidence with swing-options decisions

## Dependency sequence

```text
Stable authority and data contracts
    -> typed ICT zone lifecycles
    -> reliable volume-profile inputs
    -> approved execution planner
    -> real order-flow provider and rules
    -> versioned journal and replay

Separate options data and research
    -> independently approved swing-options engine
```

Volume profile depends on trustworthy volume and session normalization. Execution planning depends on approved location and risk models. Real order flow depends on a true bid/ask-capable feed. Journaling and replay depend on stable, versioned authority outputs.

## Day-trading and swing-options boundary

| Concern | Day-trading platform | Future swing-options engine |
|---|---|---|
| Primary horizon | Intraday | Multi-session swing |
| Current instruments | NQ, future ES selection | Not approved |
| Data | Futures OHLCV; future profile/order flow | Underlying plus options chain |
| Roles | 4H/1H context, 15M setup, 5M confirmation, 1M trigger | To be independently defined |
| Playbooks | ICT Liquidity Sweep Reversal | No approved playbook yet |
| Risk | Manual validation; planner not implemented | Options-specific risk required |
| Authority | Current `DecisionAuthority` | Separate future authority |
| UI and evaluation | Intraday dashboard and tests | Separate future surface and tests |

The two systems may share infrastructure such as logging or provider abstractions, but they must not share strategy conclusions by default.

## Explicitly deferred work

- Automated order execution
- Guaranteed predictions or outcomes
- Unapproved IFVG, order-block, volume-profile, or order-flow rules
- Entry, stop, target, and sizing rules before the trade-planner phase
- Reusing day-trading triggers for swing options
- Defining future playbooks before separate review and approval
