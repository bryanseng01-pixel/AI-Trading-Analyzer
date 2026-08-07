# Playbooks

## Playbook framework

A playbook is a documented, deterministic sequence of market conditions. It exists to make the trader wait for evidence in the correct order, expose missing conditions, and make decisions reproducible in tests and review.

`DecisionAuthority` is the sole recommendation authority. A playbook phase is diagnostic state owned by that authority; it is not a second recommendation. No future playbook may be activated until its context, sequence, confirmation, invalidation, and risk boundaries have been separately approved.

Two event semantics apply throughout the current playbook:

- **BOS and CHoCH require a candle close** through the relevant swing level.
- **Liquidity sweeps use candle wicks** through the relevant session level.

EMA direction is not MSS, BOS, CHoCH, or execution confirmation.

## Current playbook: ICT Liquidity Sweep Reversal

### Purpose

The ICT Liquidity Sweep Reversal playbook identifies a potential directional opportunity after price takes relevant session liquidity and lower-timeframe structure turns toward aligned higher-timeframe context. Its purpose is to filter incomplete setups, not predict every reversal or continuation.

The current playbook stops at a `READY` decision-support state. It does not calculate an entry, stop, target, position size, or order instruction.

### Timeframe roles

| Timeframe | Current role | Accepted evidence |
|---|---|---|
| 4H | Preliminary context | EMA-relative direction |
| 1H | Preliminary context | EMA-relative direction |
| 15M | Setup state | Latest structural event or current market structure |
| 5M | Confirmation | Latest actual close-confirmed BOS/CHoCH |
| 1M | Trigger | Latest actual close-confirmed BOS/CHoCH |
| 1M | Temporary execution-zone gate | Directionally aligned active FVG |

The chart may display any configured timeframe, but chart selection does not change these roles or the authority result.

### Context requirements

Preliminary context comes only from 4H and 1H EMA agreement:

- both bullish: bullish context;
- both bearish: bearish context;
- disagreement or unavailable direction: conflicting context.

Conflicting context produces `AVOID`. EMA agreement establishes only preliminary direction. It does not prove structural continuation or reversal.

### 15M setup states

The 15M analysis is classified as one of three states:

- `ALIGNED_CONTINUATION`: reliable 15M structural evidence aligns with preliminary HTF context;
- `COUNTERTREND_PULLBACK`: reliable 15M structural evidence opposes aligned HTF context and is treated as a developing pullback;
- `UNCONFIRMED`: no reliable directional 15M structural evidence is available.

A `COUNTERTREND_PULLBACK` does not automatically invalidate the HTF thesis. It remains `WAIT` until relevant liquidity is swept and a close-confirmed 5M event shifts back toward HTF direction. Stronger 15M reversal and thesis-invalidation rules have not yet been approved.

When BOS and CHoCH coexist on a timeframe, the latest event by timestamp controls. A CHoCH is the deterministic tie-break if both timestamps are equal.

### Liquidity-sweep gate

The current liquidity gate uses Asia, London, and New York session highs and lows:

- a bullish setup requires at least one relevant session low to be swept;
- a bearish setup requires at least one relevant session high to be swept.

The sweep is detected from the candle wick. A close through the session level is not required. A sweep alone does not confirm a reversal; it only satisfies the liquidity condition.

### 5M confirmation gate

The latest actual 5M BOS or CHoCH must point in the HTF-context direction. The structural event must already meet the close-confirmation rule in `market_structure.py`.

The following do not satisfy this gate:

- bullish or bearish 5M EMA direction;
- a wick-only break of a swing;
- a directionless structure label;
- an older aligned event superseded by a newer opposing event.

For a 15M `COUNTERTREND_PULLBACK`, the relevant sweep and aligned 5M event are required before the setup advances beyond `WAIT`.

### 1M trigger gate

The latest actual 1M BOS or CHoCH must point in the HTF-context direction. It follows the same close-confirmation and event-precedence rules as the 5M gate.

EMA alignment alone cannot satisfy the trigger. The 1M trigger is structural evidence; it is not yet an entry order.

### Directional 1M FVG execution gate

The current temporary execution-location gate requires at least one active 1M FVG in the HTF-context direction. FVG formation uses the first candle's high/low and the third candle's high/low. Existing mitigation and dashboard size/count filtering remain in effect.

This is an availability gate, not a complete execution plan. The current system does not define an entry price, retracement requirement, stop, target, or risk/reward threshold. A close-confirmed active 1M IFVG may appear as optional confluence only when it directionally and geometrically overlaps the authority-selected FVG. It does not satisfy or replace this playbook's authority FVG gate.

A structurally formed, active directional 1M Order Block may also appear as
optional confluence when it strictly overlaps the same authority FVG. It does
not satisfy or replace any playbook gate and cannot change playbook status or
phase.

The authority FVG may also be classified against one active 15M dealing range.
Bullish discount or bearish premium contributes optional evidence only. The
range cannot select or replace the FVG, and equilibrium, crossing, wrong-side,
or outside-range classifications do not change this playbook's status.

The same authority FVG may be evaluated against the previous completed New
York session's bar-volume profile approximation. Bullish location at or below
VAL and bearish location at or above VAH may appear as optional evidence.
POC, HVN, and LVN relationships remain descriptive. Volume Profile cannot
replace an authority gate, select another execution zone, or alter status.

## Long sequence

The current long sequence is:

1. 4H and 1H EMA context align bullish.
2. The 15M setup is `ALIGNED_CONTINUATION` or a recognized `COUNTERTREND_PULLBACK` develops.
3. Relevant sell-side session liquidity is swept by a wick through a session low.
4. The latest close-confirmed 5M BOS/CHoCH is bullish.
5. The latest close-confirmed 1M BOS/CHoCH is bullish.
6. A bullish active 1M FVG passes the configured size/count filters.
7. `DecisionAuthority` may report `READY`.
8. The trader must still validate risk before taking any trade.

## Short sequence

The current short sequence is:

1. 4H and 1H EMA context align bearish.
2. The 15M setup is `ALIGNED_CONTINUATION` or a recognized `COUNTERTREND_PULLBACK` develops.
3. Relevant buy-side session liquidity is swept by a wick through a session high.
4. The latest close-confirmed 5M BOS/CHoCH is bearish.
5. The latest close-confirmed 1M BOS/CHoCH is bearish.
6. A bearish active 1M FVG passes the configured size/count filters.
7. `DecisionAuthority` may report `READY`.
8. The trader must still validate risk before taking any trade.

## Status progression

### `AVOID`

The 4H and 1H preliminary EMA context conflicts. Lower-timeframe evidence cannot override this gate in the current playbook.

### `WAIT`

Aligned context exists, but setup development or the relevant liquidity sweep is incomplete. This includes:

- an `UNCONFIRMED` 15M setup;
- an aligned 15M setup without a relevant sweep; and
- a 15M `COUNTERTREND_PULLBACK` that has not yet received an aligned close-confirmed 5M shift after the sweep.

### `WATCH`

Context, the applicable setup condition, and relevant sweep are present, but one or more execution confirmations are missing:

- aligned close-confirmed 5M BOS/CHoCH for an aligned continuation;
- aligned close-confirmed 1M BOS/CHoCH; or
- directional active 1M FVG.

Once a countertrend pullback receives its required aligned 5M shift, it may also progress to `WATCH` while later gates remain incomplete.

### `READY`

All currently approved gates align:

- aligned 4H/1H context;
- accepted 15M setup state;
- relevant wick-based session sweep;
- aligned close-confirmed 5M BOS/CHoCH;
- aligned close-confirmed 1M BOS/CHoCH; and
- directional active 1M FVG.

`READY` is decision support, not an automated trade signal or guarantee.

## Current invalidation concepts

The current authority recognizes conflicting 4H/1H context as an immediate reason to avoid a directional setup. It also prevents readiness when the latest 5M or 1M structural event is missing or points away from context, when relevant liquidity has not been swept, or when the directional 1M FVG gate is unavailable.

These conditions prevent progression; they are not a complete trade-thesis or post-entry invalidation model. In particular:

- one opposing 15M signal is treated as a possible pullback, not automatic invalidation;
- no approved rule yet defines when 15M evidence becomes a true HTF-thesis reversal;
- no entry-zone invalidation, stop placement, or target invalidation is implemented; and
- no volume-profile or order-flow invalidation is currently available.

## Future confirmation points

The following are planned integration points, not current requirements:

### Volume profile

The implemented profile is limited to the previous completed New York session
and uniformly distributes Yahoo bar volume across intersected price bins. It
is optional location evidence only. Future profile variants, acceptance and
rejection rules, composite profiles, and authority gating remain undefined.

### True order flow

Future approved rules may use bid/ask delta, footprint imbalance, absorption, or exhaustion after a suitable provider is integrated. Yahoo Finance cannot provide true bid/ask order flow, and candle direction or ordinary volume must not be presented as a substitute.

The deterministic Delta engine can currently evaluate normalized synthetic or
replayed trade events around the existing authority FVG. Its optional
`delta_confirmation` assessment is not connected to the production dashboard
because no licensed provider is configured. It remains non-required and cannot
change this playbook's status, phase, gates, direction, or recommendation.

Future evidence may enter `DecisionAuthority` only after a separately approved
playbook change. Until then it remains optional, non-authoritative location
evidence and cannot publish an independent recommendation.

## Future playbook placeholders

The following placeholders reserve documentation structure only. Their rules are intentionally undefined and unapproved:

- Playbook 2: To be determined
- Playbook 3: To be determined
- Playbook 4: To be determined

Each future playbook must document purpose, eligible instruments, context, timeframe roles, sequence, confirmation semantics, invalidation, risk boundary, data dependencies, status mapping, and tests before implementation.
