# Floor Mop — Phase 1 Roadmap: Data Source Survey

**Status:** Draft v0.1
**Date:** 1 October 2026
**Prerequisite:** Phase 0 complete (see `roadmaps/floor_mop_phase0_project_log.md`)
**Blocks:** Record schema, "hit" definition, Phase 2 ingestion

---

## 1. Purpose and framing

Phase 1 decides where Floor Mop's data comes from.

The original roadmap framed this as choosing a primary feed with a fallback. That framing is now superseded: **Floor Mop will use a collection of providers, each serving a different purpose.** The output of this phase is a *portfolio* with documented roles, not a winner.

### Provider roles

A provider may fill one role or several. Each role needs a primary and, where the role is critical, a fallback.

| Role | What it answers | Criticality |
|---|---|---|
| **Detection** | A new token or pool exists, right now | Critical — a miss here means the opportunity never enters the pipeline |
| **Enrichment** | What are this token's facts? (authorities, LP status, holders, deployer) | Critical — drives the filter |
| **Sellability** | Can this position be exited, and at what cost? | **Most critical** — the load-bearing check for the whole thesis |
| **Market data** | Price, liquidity depth, volume, buy/sell composition | High — feeds filter and monitoring |
| **Wallet intelligence** | Deployer history, whale behaviour, holder movement | Medium — improves scoring, not strictly required |
| **Venue coverage** | Which launchpads and AMMs are visible at all | Critical — a venue we cannot see is a venue we cannot trade |

### Why a portfolio rather than one provider

- The fastest detection feed is rarely the richest enrichment source
- Rate limits bind per provider, so spreading load raises effective throughput
- A single provider is a single point of failure during exactly the busy periods that matter
- Cost differs sharply by role: detection may justify a premium tier where market data does not

### Scope boundary

Phase 1 is **research and measurement**, not construction. The only artifact that graduates into `src/` is the adapter interface at the very end. Measurement code is throwaway and lives outside `src/`.

---

## 2. Reference inputs — what to send the architect

Accuracy depends on current facts. The architect's knowledge has a mid-2026 cutoff and this space moves quickly. The following materials materially improve the quality of this phase. Send what is easy; nothing here is blocking on its own.

### Highest value

1. **Provider dashboard screenshots or exports** — current plan tier, included request/credit limits, what is gated above the tier, current usage. Especially for Helius. Redact account identifiers.
2. **Provider documentation links** — endpoint lists, streaming methods (webhook vs WebSocket vs gRPC), commitment-level options, rate limits, pricing pages. Links are enough; the architect can fetch them.
3. **Sample payloads** from any feed already accessible — one real event per feed, keys and account identifiers redacted. This is the single most useful input for designing the normalised event shape.
4. **Venue share data** — which launchpads and AMMs actually carry launch volume *today*. Any recent analytics dashboard or report.

### Useful

5. **`.env` variable names only** — never values. Tells the architect what access already exists.
6. **Terms of service** for anything unofficial or reverse-engineered, especially aggregator APIs.
7. **The Muneo repo's report format** — a sample report file. Determines whether Muneo overlaps with any Phase 1 role.
8. **The salvaged Sylvester Solone scraper's source list** — which providers it already pulls from, and whether any adapter code is reusable.
9. **Prior measurements** — anything the user, the friend, or teammates have already timed.
10. **The existing scanner's event pipeline** — specifically its event schema and the three-timestamp implementation, to confirm or refute the claimed overlap (see Phase 0 log, section 7).

### Context the architect lacks entirely

11. **Where Floor Mop will run** — machine, region, hosting provider. Proximity to validator infrastructure dominates latency and can outweigh provider choice.
12. **Budget ceiling** — monthly, for data infrastructure in total.
13. **Peak event volume expectations** — if known from prior observation.

### Format

Pasted text, file attachments, or links all work. For anything large, a link is better than a paste. **Never send private keys, API keys, seed phrases or wallet addresses holding funds.** Variable names, endpoint shapes and plan tiers carry no secrets; values do.

---

## 3. Requirements to pin down before testing

These four answers determine which candidates are worth testing at all. They are resolved at the start of the phase, in session.

| Requirement | Why it gates the work |
|---|---|
| **Reaction-time target** | Decides whether shred-level and pre-confirmation streams are in scope. See section 9. |
| **Deployment location** | Network distance to validators and to provider endpoints is a first-order latency term. Measuring from a laptop in Seoul and deploying to Frankfurt invalidates the measurements. |
| **Budget ceiling** | Several candidates have premium tiers. Without a ceiling the comparison has no cost axis. |
| **Peak volume expectation** | Determines whether rate limits bind during the periods that matter. |

---

## 4. Candidate catalogue (desk research)

No code in this step. For each candidate, record:

- Access methods available (and each as a **separate** entry where latency differs — e.g. webhook vs WebSocket vs gRPC are three candidates, not one)
- Roles it could plausibly fill
- Pricing and plan tiers
- Rate limits and how they are counted
- Authentication model
- Terms-of-use risk (official API vs undocumented endpoint)
- Commitment level offered, where applicable

### Candidates named so far

| Candidate | Access methods to catalogue | Likely roles |
|---|---|---|
| Helius | Webhook, WebSocket, gRPC/Geyser | Detection, enrichment |
| Raydium | Pool/program events, API | Detection, market data |
| Pump.fun / PumpSwap | Launch and graduation events | Detection, venue coverage |
| GMGN | API (official status to verify) | Wallet intelligence, market data |
| Jito | Block, bundle, shred-level data | Detection (low latency), execution-adjacent |
| Birdeye | Market data API | Market data, enrichment |
| Direct RPC / self-hosted Geyser | Provider-hosted or self-run | Detection |
| Jupiter | Quote/route APIs | **Sellability** (route simulation) |
| Others | To be identified during research | — |

**The candidate list is open.** New providers may be added at any point during the phase. Section 9 covers how late additions are handled without the phase becoming unbounded.

**Output of this step:** a go/no-go list. Candidates that fail on cost, terms of use, or missing capability are documented and excluded without being measured.

---

## 5. Measurement methodology

### 5.1 Latency: the race test

Block timestamps have one-second resolution and are not a usable ground truth. Instead:

- Run **every detection candidate simultaneously** on **one machine** with a synchronised clock
- Key every event by **transaction signature** (or another stable identifier)
- Record, per event: which feed delivered it first, and each other feed's margin behind the leader
- A single shared timing log, one row per feed per event

This measures relative latency directly and sidesteps the ground-truth problem entirely.

### 5.2 What to report

- **Percentiles: p50, p95, p99.** Never averages. The tail is what loses the trade.
- **Coverage / miss rate:** events feed A saw that feed B did not, both directions. A fast feed that misses a third of launches is worse than a slower complete one.
- **Venue coverage:** which launchpads and AMMs each feed actually surfaces.
- **Phantom rate:** see 5.3.
- **Rate-limit behaviour under load:** what happens during a burst — throttle, drop, queue, disconnect.
- **Reliability:** disconnects, gaps, backpressure behaviour over the full collection window.

### 5.3 Commitment level and phantom events

Earlier is not free. Feeds that deliver at `processed` commitment, or at shred level before confirmation, surface transactions that **may never land**.

This phase must measure, per feed:

- The commitment level at which events arrive
- The **phantom rate**: the proportion of early signals that never reach a confirmed state

**Consequence for the schema:** commitment level belongs on the detection record as a first-class field. A candidate detected at `processed` carries different certainty from one detected at `confirmed`, and downstream logic must be able to tell the difference.

### 5.4 End-to-end budget

Detection latency measured in isolation is misleading. If the sellability check takes several hundred milliseconds, a 50 ms detection advantage is noise.

Therefore measure, for the full path:

```
detection → enrichment calls → sellability check → filter verdict
```

Record the latency contribution of each stage. The result determines:

- Whether premium detection feeds are worth their cost
- Which enrichment calls can sit in the hot path and which must run asynchronously (this carries into Phase 3)
- Whether the reaction-time target from section 3 is achievable at all

### 5.5 Cost measurement

Record actual consumption during the collection window, not list prices: requests or credits consumed per hour at observed volume, extrapolated to peak. A provider that is affordable at rest and ruinous during a surge must be identified now.

---

## 6. Measurement harness

- **Location:** outside `src/`. A directory such as `survey/` or `experiments/`, clearly marked as throwaway.
- **Per candidate:** a thin adapter that connects, receives, and writes timing rows to the shared log. No filtering, no enrichment, no business logic.
- **Shared timing log:** one format across all candidates, so comparison is a matter of reading one file.
- **Analysis script:** computes percentiles, miss rates, phantom rates and cost per candidate.
- **Secrets:** provider keys come from the environment, exactly as in `src/`. The public-repo rule applies to survey code identically — no keys in source, no keys in committed config.
- **Nothing graduates into `src/`** except the adapter interface defined in section 8.

---

## 7. Run and analyse

- **Collection window:** long enough to include both quiet and busy periods, and at least one genuine launch surge. Duration set in session once volume is observed.
- **Unattended operation:** the harness must survive disconnects and log gaps rather than dying silently.
- **Comparison matrix:** candidates on one axis, roles on the other, with measured numbers in the cells.

---

## 8. Outputs

Phase 1 is complete when all five exist:

1. **Provider comparison document** — measured latency percentiles, coverage, phantom rates, cost, reliability, per candidate.
2. **Role assignments** — which provider serves each role from section 1, with fallbacks for the critical ones, and the reasoning recorded.
3. **Adapter interface** — the thin, documented interface that makes providers swappable. The only code from this phase that enters `src/`.
4. **Normalised detection event shape** — the common structure every detection adapter emits. This is effectively the detection record, and it is the direct input to the deferred record schema.
5. **Phase 1 project log** — written in the Phase 0 style, recording what was tested, what was chosen and why, what was excluded and why, and what a fresh context window needs to know.

### Immediately after Phase 1

The **record schema** and the **"hit" definition**, both deferred from Phase 0, are designed next — together with output 4, since the normalised event shape and the schema's detection record are the same object viewed from two sides.

---

## 9. Open questions carried into the phase

**9.1 Reaction-time target — unanswered, and it gates the candidate list.**

- **Tier A — first blocks after launch.** Requires the fastest, most expensive infrastructure; shred-level streaming in scope; competes directly with established operators.
- **Tier B — within a few seconds.** Standard streaming feeds suffice; shred-level out of scope.
- **Tier C — within minutes.** Momentum entry rather than launch sniping (the "token under 10 minutes old" pattern). Dramatically cheaper and simpler; changes Phase 5's role substantially.

The answer determines roughly half the testing effort. It should be settled before section 4 begins.

**9.2 Stop rule for an open-ended survey.**

The provider list is explicitly unbounded, which creates a real risk: there is always one more provider to test, and the phase never ends. The phase needs an agreed gate before Phase 2 can start. Options:

- Time-boxed: a fixed collection period, then decide with what is measured
- Coverage-based: proceed once every role in section 1 has a measured primary and the critical roles have a fallback
- Threshold-based: proceed once the measured end-to-end path meets the section 3 reaction-time target

**Recommendation: coverage-based**, since it ties the gate to the portfolio framing rather than to the clock. The specific gate is the user's decision.

**9.3 Handling late additions.**

Providers discovered after measurement begins: folded in continuously, or batched into a second round after the first decision? Continuous addition risks never closing the phase; batching risks shipping with a known-inferior provider. Recommendation: batch, with the first round closing on the section 9.2 gate and later candidates evaluated as a Phase 1 addendum without blocking Phase 2.

**9.4 Carried over from earlier phases**

- Deployment location, budget ceiling, peak volume (section 3)
- Storage backend — still open, decided alongside the record schema
- Whether the existing scanner's pipeline genuinely overlaps (Phase 0 log, section 7)
- Whether the salvaged scraper contains reusable adapters
- `requires-python` fix, pending the collaborator's Python version

---

## 10. Known unknowns on the architect's side

The following are **assumptions, not facts.** Each must be verified during section 4 research before entering any decision. They are recorded here so they are not quietly treated as settled.

| Assumption | Status | Why it matters |
|---|---|---|
| Pump.fun graduations migrate to PumpSwap rather than Raydium | **Unverified.** Based on mid-2026 recollection. | Determines which venues detection must cover |
| Other launchpads have taken meaningful share | **Unverified.** | Same — a missed venue is invisible inventory |
| GMGN offers only unofficial or undocumented API access | **Unverified.** | Unofficial endpoints carry reliability and terms-of-use risk |
| Helius gRPC/Geyser is gated above entry plan tiers | **Unverified.** | Decides whether the fastest Helius path is reachable at current cost |
| Jito shred-level streaming is impractical for a small operator | **Unverified.** | Decides whether Tier A reaction time is achievable at all |
| Webhook delivery is materially slower than WebSocket or gRPC | **Unverified assumption, central to this phase.** | This assumption is the reason the phase exists; it must be measured, not asserted |

---

## 11. Principles carried from the master roadmap

1. **No authority, no wallet, no keys in Floor Mop.** Applies to survey code as well.
2. **Nothing hardcoded that should be configurable.** No thresholds in this document by design.
3. **Sources are swappable.** The adapter interface is the mechanism, and it is why the portfolio approach is viable.
4. **Measure before optimising.** This phase is that principle applied in full.
5. **Log everything.** Including what was rejected and why — for providers as much as for tokens.
6. **The roadmap is not amended.** Divergence is recorded in the phase project log.

---

*This roadmap describes method and sequence. Thresholds, durations and provider choices are decided in session against measured data.*
