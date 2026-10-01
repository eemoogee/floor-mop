# Floor Mop — Master Roadmap

**Status:** Draft v0.1
**Date:** 30 September 2026
**Owner:** TBD
**Target readiness window:** Before the meme-season run-up around the spring 2028 Bitcoin halving

---

## 1. Purpose

Floor Mop is a Python data gathering, filtration and monitoring system for newly launched Solana tokens. It detects launch and pool-creation events, enriches each candidate with the on-chain facts needed to judge it, discards garbage, monitors survivors, and emits a stream of structured records.

Floor Mop exists because the hard part of meme-coin sniping is not execution. It is deciding what is worth touching, fast enough to matter. Sylvester Solone already handles execution. Floor Mop handles everything upstream of it.

### Trading thesis this system serves

The target is tokens that offer a 20%+ exit. A token does not need to be legitimate to qualify. Catching a rug early enough to sell into its own spike is an acceptable outcome. Tokens that show signs of sustainable interest may be held longer to maximise the move.

The single most important thing Floor Mop must establish about any candidate is **whether the position can be exited at all**. A honeypot that permits buys and blocks sells defeats the entire thesis, regardless of how the price moves. Sellability is the load-bearing filter.

---

## 2. Scope

### What Floor Mop is

- A stream of enriched, filtered candidate records
- A monitoring layer with adjustable tick speeds
- A logging system that records what it rejected and why, not only what it passed

### What Floor Mop is not

- It holds no wallet, no private key, and no secret of any kind
- It signs nothing and submits nothing to the chain
- It contains no position sizing, no daily loss cap, no kill switch, no risk limits of any kind
- It has no authority over trading decisions

Floor Mop produces data. What consumes that data, and what constraints that consumer operates under, is outside this roadmap.

### Relationship to Sylvester Solone

```
Feeds ──► Floor Mop ──► handoff ──► Hermes ──► MCP server ──► Jupiter ──► Solana
          (detect,                  (brain)    (execution)
           enrich,
           filter,
           monitor)
```

Floor Mop sits alongside the existing data layer (Muneo, the salvaged scraper) as another source of context for Hermes. It does not pass through the MCP server.

---

## 3. Cross-cutting principles

These apply to every phase.

1. **No authority.** Floor Mop never decides to trade. It reports.
2. **No secrets.** No keys, no wallet, no operator credentials. API keys for data providers are supplied by the runtime environment and never committed.
3. **Nothing hardcoded that should be configurable.** Every threshold, every floor, every tick interval, every timeout is a config value. The roadmap deliberately contains no numbers. Values are decided in session against real data.
4. **Sources are swappable.** Every feed sits behind a common adapter interface. Swapping a provider must not touch downstream code.
5. **Log everything, including rejects.** A filter cannot be evaluated without knowing the fate of what it threw away.
6. **Three timestamps on every record.** When the event occurred on chain, when Floor Mop received it, when Floor Mop finished processing it. Latency is measured, not assumed.
7. **Each phase writes records the next phase consumes.** No phase depends on live data that was never persisted.
8. **Measure before optimising.** Assumptions about which feed is fastest are worth nothing until timed.

---

## 4. Phases

Phases are sequential. Each has an exit criterion that must be met before the next begins.

---

### Phase 0 — Foundations

**Objective:** A repository a coding agent can work in without ambiguity.

**Work:**
- GitHub repository created, structure established, Python dependency management chosen
- Configuration architecture: layered config with environment-variable overrides, so no value is ever a literal in source
- Logging and persistence layer, since every subsequent phase writes records
- The **Floor Mop record schema** — the canonical shape of a candidate record as it moves through detection, enrichment, filtration and monitoring. This is the spine of the system and changes to it are expensive later.
- Definition of a **hit**: what outcome counts as success when the system is eventually evaluated

**Deliverables:** Repo skeleton, config loader, logging layer, documented record schema.

**Exit criterion:** A record can be constructed, written, and read back with all three timestamps populated.

**Open questions for session:**
- Storage backend for records (flat files, SQLite, Postgres, something else)
- Whether the record schema is versioned from day one

---

### Phase 1 — Data Source Survey

**Objective:** Choose a primary feed and a fallback on evidence, not reputation.

This phase runs before ingestion is built, and it is the first real work after scaffolding. Helius RPC webhooks are the obvious starting point and are very likely not the best option. Webhook delivery adds latency on top of indexing latency. The survey exists to find out what actually beats it.

**Candidate sources to evaluate:**

| Source | Access modes to test | Notes |
|---|---|---|
| Helius | Webhook, WebSocket, Geyser/gRPC | Each mode has different latency; treat as three separate candidates |
| Raydium | Pool creation events | Primary AMM venue for graduated tokens |
| Pump.fun | Launch and graduation events | Where a large share of launches originate |
| GMGN | API / feed | Aggregated launch and wallet intelligence |
| Jito | Block and bundle data | Primarily execution-side, may offer earlier visibility |
| Birdeye | Market data API | Enrichment more than detection |
| Direct RPC / Geyser plugin | Self-hosted or provider-hosted | Highest potential speed, highest cost and complexity |
| Others identified during survey | — | List is not closed |

**Evaluation axes:**
- **Latency** — time from on-chain event to Floor Mop having the record, measured not quoted
- **Coverage** — what fraction of launches appear, and which venues are missed entirely
- **Cost** — including how cost scales with volume during a busy market
- **Reliability** — uptime, backpressure behaviour, behaviour under load
- **Rate limits** — and whether they bind during a launch surge
- **Data richness** — how much enrichment comes free with detection

**Deliverables:**
- A written comparison document with measured numbers
- A chosen primary feed and at least one fallback
- Thin adapter interface specified, so sources remain swappable

**Exit criterion:** A documented, evidence-backed feed choice.

**Open questions for session:**
- Whether multiple feeds run concurrently for coverage, accepting duplicate events, or one feed is authoritative
- Budget ceiling for data infrastructure

---

### Phase 2 — Ingestion

**Objective:** A raw, unfiltered, persistent stream.

**Work:**
- Connect the chosen feed(s) through the adapter interface
- Persist every event with no filtering whatsoever
- Deduplicate where concurrent feeds overlap
- Handle reconnection, backpressure and gaps explicitly rather than crashing
- Instrument latency across all three timestamps

**Deliverables:** A running ingester and a growing corpus of raw events.

**Exit criterion:** The ingester runs unattended for a sustained period without data loss, and the corpus is large enough to characterise real launch volume and latency.

**Note:** This phase should be allowed to run for a meaningful stretch before Phase 4 begins. The filter is designed against what the stream actually contains, not against what we imagine it contains.

---

### Phase 3 — Enrichment

**Objective:** Attach to each candidate the facts needed to judge it.

**Enrichment targets:**
- **Sellability** — the critical one. Can the token be sold, and at what cost? Transaction simulation against a real route is the likely approach.
- Mint authority and freeze authority status
- LP token status (burned, locked, held)
- Holder distribution and concentration
- Deployer address and its history
- Liquidity depth and composition
- Early volume and buy/sell composition

**Key design output:** which enrichment calls are fast enough to sit in the hot path, and which must run asynchronously after an initial pass. This split determines the system's effective reaction time and cannot be deferred.

**Deliverables:** Enrichment modules, each independently testable, with measured per-call latency.

**Exit criterion:** A candidate record can be fully enriched, and the latency cost of each enrichment is known.

---

### Phase 4 — Filtration

**Objective:** Discard garbage, fast, with a full audit trail.

**Structure:**

1. **Hard rejects** — cheap, decisive, run first. Sellability failure, dangerous authority configuration, liquidity below the configured floor.
2. **Scored filters** — configurable weights over enriched attributes, producing a score rather than a verdict.

Floor Mop emits the score and the supporting facts. It does not convert a score into a trade decision.

**Requirements:**
- Every rejection is logged with the specific reason and the values that triggered it
- Every threshold is configurable and tunable in session
- Filter configuration is versioned, so a change in behaviour can be traced to a change in config

**Deliverables:** Filter pipeline, rejection log, versioned filter config.

**Exit criterion:** The pipeline processes the Phase 2 corpus end to end and produces a reject log rich enough to argue about.

---

### Phase 5 — Monitoring

**Objective:** Track survivors and surface the signals that inform exit timing.

**Work:**
- Adjustable tick speeds, configurable per candidate or per tier, so a hot candidate can be polled aggressively and a cool one cheaply
- Track price, liquidity, volume, buy/sell balance, holder movement, and large-wallet behaviour over time
- Detect decay signals: liquidity withdrawal, deployer movement, buy-side exhaustion
- Define a lifecycle — when a candidate is promoted, demoted, and dropped from monitoring entirely

**Deliverables:** Monitoring service, time-series records per candidate.

**Exit criterion:** A candidate's full life can be replayed from records, from detection to drop.

---

### Phase 6 — Simulation and Validation

**Objective:** Establish whether the filter actually works, before real SOL is committed.

**Scope warning:** This phase carries real scope-creep risk. A full backtesting engine is a project in its own right. Scope must be pinned down explicitly before implementation starts, and the first version should be the smallest thing that answers the question honestly.

**What a credible simulation must model:**
- Fill delay between signal and realistic landing time
- Price impact at the intended size against the pool's actual depth
- Fees, including failed transactions
- Exit slippage, which on a falling token is typically worse than entry slippage

A simulator that ignores these will report results that are optimistic in a way that is hard to detect and expensive to discover later.

**What it must track:**
- Outcomes for accepted candidates
- **Outcomes for rejected candidates.** Without this, a filter that is simply too strict is indistinguishable from a filter that is good.

**Deliverables:** Replay harness over logged data, outcome reports for both sides of the filter.

**Exit criterion:** Scope to be defined at phase start.

---

### Phase 7 — Handoff Interface

**Objective:** Define and implement the contract Floor Mop presents downstream.

**Work:**
- Output record format — the candidate, its enrichment, its score, its monitoring state
- Transport mechanism to Hermes
- Delivery semantics: push versus pull, ordering, replay of missed records

Floor Mop emits a stream. What Hermes does with it, and what constraints govern execution, belongs to the Sylvester roadmap.

**Deliverables:** Documented output contract and a working handoff.

**Exit criterion:** Hermes can consume the stream and act on it.

---

## 5. Decisions deferred to session

The following are deliberately absent from this roadmap and will be set against real data:

- Liquidity floor
- Position size (and therefore the liquidity floor that size implies)
- All filter thresholds and scoring weights
- Tick speed intervals and tiering
- Storage backend
- Number of concurrent feeds
- Phase 6 scope

---

## 6. Known risks

| Risk | Nature |
|---|---|
| Competition | Established Jito-optimised operators have tuned infrastructure. Floor Mop's edge must come from filter quality, not raw speed. |
| Honeypots | The central technical threat to the thesis. Sellability checking is the highest-value component in the system. |
| Feed latency | If no available feed is fast enough, the strategy shifts from launch sniping toward momentum entry. This would change Phase 5's role significantly. |
| Simulation optimism | Paper results that ignore fills, impact and slippage will look good and mean nothing. |
| Cost during surges | Data provider costs and rate limits are most likely to bind exactly when the market is most active. |
| Schema churn | A record schema changed after Phase 2 invalidates the corpus. Worth over-thinking in Phase 0. |

---

## 7. Open questions

1. Does the existing scanner codebase share infrastructure with Floor Mop, or is the overlap superficial? This has been asserted but not verified against the code.
2. Does the salvaged Sylvester Solone Python scraper contain anything reusable here?
3. What is the budget ceiling for data infrastructure?
4. Is Floor Mop a public repository or private? The answer changes how API keys and configuration are handled.
5. Who owns the repository and what is the branching model?

---

*This roadmap describes architecture and sequence. Implementation details are decided in session.*
